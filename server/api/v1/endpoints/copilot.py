"""
Copilot AI Inference & Streaming Endpoints.
Guarantees multi-tenant session isolation and rate limiting.
"""

import time
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from server.database.connection import get_db
from server.database.models import User
from server.database.repository import SessionRepository, UsageRepository
from server.auth.dependencies import get_current_user
from server.sessions.manager import session_manager, SessionContext
from server.billing.entitlement import EntitlementService
from server.ai.groq_client import ai_client
from server.middleware.rate_limit import check_rate_limit, solve_limiter
from shared.schemas import SolveRequest, SolveResponse, SkipRequest

router = APIRouter(prefix="", tags=["Copilot"])


@router.post("/solve", response_model=SolveResponse)
async def solve_question(
    req: SolveRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Check rate limit
    await check_rate_limit(request, solve_limiter)

    # 2. Check entitlement quota — fetch real daily usage from DB (M-2 fix)
    usage_repo = UsageRepository(db)
    today_count = usage_repo.get_user_daily_solve_count(user.id)
    if not EntitlementService.can_perform_solve(user, current_usage_count=today_count):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usage quota exceeded for current plan. Please upgrade your subscription."
        )

    # 3. Resolve session
    session_repo = SessionRepository(db)
    sess_id = req.session_id or "default"
    if req.session_id and req.session_id != "default":
        sess = session_repo.get_session(session_id=req.session_id, user_id=user.id)
        if not sess:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    ctx: SessionContext = await session_manager.get_or_create_context(session_id=sess_id, user_id=user.id)
    
    # 4. Advance generation ID
    ctx.active_gen_id += 1
    gid = ctx.active_gen_id
    q_text = req.question.strip()

    # 5. Broadcast status to this session's subscribers
    await ctx.broadcast("status", {"state": "generating", "question": q_text})

    # 6. Launch streaming worker task in background
    async def _stream_worker(current_gid: int, question: str):
        full_answer = ""
        token_count = 0
        start_t = time.time()
        
        async for token in ai_client.stream_chat_completion(
            question=question,
            history=list(ctx.history)
        ):
            if ctx.active_gen_id != current_gid:
                # Aborted by user skip
                return
            full_answer += token
            token_count += 1
            await ctx.broadcast("token", {"token": token})

        if full_answer and ctx.active_gen_id == current_gid:
            # Update conversational history
            ctx.history.append({"role": "user", "content": question})
            ctx.history.append({"role": "assistant", "content": full_answer})
            
            # Calculate reading cooldown
            words = len(full_answer.split())
            cooldown = min(30, max(5, round(words / 180 * 60) + 3))
            ctx.reading_until = time.time() + cooldown
            
            await ctx.broadcast("status", {"state": "done"})
            await ctx.broadcast("cooldown", {"seconds": cooldown, "words": words, "mode": "auto"})

            # Record safe usage metadata (no full question/answer logged)
            duration_ms = int((time.time() - start_t) * 1000)
            usage_repo.record_usage(
                user_id=user.id,
                session_id=sess_id if sess_id != "default" else None,
                operation="solve",
                tokens_used=token_count,
                duration_ms=duration_ms,
                metadata_json=json.dumps({"word_count": words, "status": "success"})
            )

    asyncio.create_task(_stream_worker(gid, q_text))

    return SolveResponse(status="generating", gen_id=gid, question=q_text)


@router.post("/skip")
async def skip_question(
    req: SkipRequest,
    user: User = Depends(get_current_user)
):
    sess_id = req.session_id or "default"
    ctx = await session_manager.get_or_create_context(session_id=sess_id, user_id=user.id)
    ctx.abort_current_generation()
    await ctx.broadcast("status", {"state": "ready"})
    await ctx.broadcast("vadstate", {"state": "listening", "label": "👂 Auto-Listening (speak anytime)..."})
    return {"status": "skipped", "session_id": sess_id}


@router.get("/stream")
async def sse_event_stream(
    session_id: Optional[str] = "default",
    user: User = Depends(get_current_user)
):
    """
    Session-isolated Server-Sent Events (SSE) stream.
    Only delivers tokens and state changes belonging to the authenticated user's session.
    """
    sess_id = session_id or "default"
    ctx = await session_manager.get_or_create_context(session_id=sess_id, user_id=user.id)
    queue = ctx.add_subscriber()

    async def event_generator():
        try:
            # Send initial connected event — do NOT include user_id (L-4 fix: avoids leaking DB UUID)
            yield f"event: connected\ndata: {json.dumps({'session_id': sess_id, 'status': 'connected'})}\n\n"
            while True:
                item = await queue.get()
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            ctx.remove_subscriber(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
