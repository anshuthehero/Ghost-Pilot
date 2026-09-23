"""
Ghost Copilot Server — Server-Ready FastAPI Application.
Supports both modern /api/v1 endpoints and backward-compatible localhost:9471 desktop HUD routes.
"""

import os
import time
import json
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from server.config.settings import settings
from server.database.connection import init_db, SessionLocal
from server.database.models import User
from server.middleware.cors import StrictCORSMiddleware
from server.middleware.logging import SafeAuditLoggingMiddleware
from server.api.v1.router import api_v1_router
from server.sessions.manager import session_manager
from server.auth.dependencies import get_current_user
from shared.schemas import SolveRequest


# Shared state for local desktop controls (backward compatibility bridge)
desktop_state = {
    "sharing_mode": "hidden",
    "mode": "ptt",
    "duration": "auto",
    "manual_recording": False
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    try:
        init_db()
    except Exception as e:
        print(f"[⚠️ Database Init] {e}")
    yield
    # Shutdown: clean up if needed


app = FastAPI(
    title="Ghost Copilot Backend",
    version=settings.LATEST_CLIENT_VERSION,
    lifespan=lifespan
)

# Attach Security Middlewares
app.add_middleware(StrictCORSMiddleware, allowed_origins=settings.ALLOWED_ORIGINS)
app.add_middleware(SafeAuditLoggingMiddleware)

# Mount Versioned API v1 Router
app.include_router(api_v1_router)


# --- Monitoring & Health Probes ---
@app.get("/health", tags=["Monitoring"])
def health_check():
    """Liveness probe for infrastructure and container monitoring."""
    return {
        "status": "ok",
        "app": "ghost_copilot",
        "version": settings.LATEST_CLIENT_VERSION,
        "environment": settings.APP_ENV
    }


@app.get("/ready", tags=["Monitoring"])
def readiness_check():
    """Readiness probe checking database connectivity and AI configuration."""
    from sqlalchemy import text
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        db_ok = False

    is_ready = db_ok
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "database": "connected" if db_ok else "disconnected",
            "ai_configured": bool(settings.GROQ_API_KEY)
        }
    )


@app.get("/diagnostics", tags=["Monitoring"])
@app.get("/api/v1/diagnostics", tags=["Monitoring"])
def get_diagnostics(user: User = Depends(get_current_user)):
    """Client & system diagnostics endpoint for preflight audits and setup assistance.
    Requires authentication — exposes OS/device details only to authenticated users (M-4 fix)."""
    from client.diagnostics.preflight import PreflightChecker
    checker = PreflightChecker()
    return checker.run_full_audit()


@app.get("/", response_class=HTMLResponse, tags=["Compatibility"])
@app.get("/index.html", response_class=HTMLResponse, tags=["Compatibility"])
def get_desktop_hud():
    """Serves the desktop HUD directly to the embedded WebKit / QWebEngine view."""
    from app import HUD  # Import existing rich HUD UI template
    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        ),
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "no-referrer",
    }
    return HTMLResponse(content=HUD, headers=headers)


@app.get("/sharing_mode", tags=["Compatibility"])
def get_sharing_mode(user: User = Depends(get_current_user)):
    """Polled every 600ms by ghost_copilot.m Cocoa wrapper to update NSWindowSharingType."""
    return {"mode": desktop_state["sharing_mode"]}


@app.post("/set_sharing", tags=["Compatibility"])
async def set_sharing_mode(
    req: Request,
    user: User = Depends(get_current_user)
):
    body = await req.json()
    desktop_state["sharing_mode"] = body.get("mode", "hidden")
    return {"sharing": desktop_state["sharing_mode"]}


@app.post("/set_mode", tags=["Compatibility"])
async def set_mode(
    req: Request,
    user: User = Depends(get_current_user)
):
    body = await req.json()
    m = body.get("mode", "ptt")
    desktop_state["mode"] = m
    return {"auto": (m == "auto")}


@app.post("/set_duration", tags=["Compatibility"])
async def set_duration(
    req: Request,
    user: User = Depends(get_current_user)
):
    body = await req.json()
    desktop_state["duration"] = body.get("duration", "auto")
    return {"duration": desktop_state["duration"]}


@app.post("/solve", tags=["Compatibility"])
async def compat_solve(
    req: Request,
    user: User = Depends(get_current_user)
):
    """Compatibility endpoint mapping to session-isolated solve."""
    from server.api.v1.endpoints.copilot import solve_question
    body = await req.json()
    q = body.get("question", "")
    solve_req = SolveRequest(question=q, session_id="default")
    db = SessionLocal()
    try:
        res = await solve_question(req=solve_req, request=req, user=user, db=db)
        return {"status": "ok", "gen_id": res.gen_id}
    finally:
        db.close()


@app.post("/skip_question", tags=["Compatibility"])
async def compat_skip(
    req: Request,
    user: User = Depends(get_current_user)
):
    """Compatibility endpoint mapping to session-isolated skip."""
    from server.api.v1.endpoints.copilot import skip_question
    from shared.schemas import SkipRequest
    return await skip_question(req=SkipRequest(session_id="default"), user=user)


@app.get("/stream", tags=["Compatibility"])
async def compat_stream(
    request: Request,
    user: User = Depends(get_current_user)
):
    """Compatibility endpoint mapping /stream to session-isolated SSE stream."""
    from server.api.v1.endpoints.copilot import sse_event_stream
    return await sse_event_stream(session_id="default", user=user)
