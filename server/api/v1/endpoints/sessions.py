"""
Session Management API Endpoints.
Provides isolated session creation and history tracking per user.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from server.database.connection import get_db
from server.database.models import User
from server.database.repository import SessionRepository
from server.auth.dependencies import get_current_user
from shared.schemas import SessionCreate, SessionOut

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("", response_model=SessionOut)
def create_session(
    req: SessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    repo = SessionRepository(db)
    sess = repo.create_session(
        user_id=user.id,
        title=req.title or "Interview Session",
        domain=req.domain or "general",
        custom_instructions=req.custom_instructions
    )
    return SessionOut(
        id=sess.id,
        user_id=sess.user_id,
        title=sess.title,
        domain=sess.domain,
        created_at=str(sess.created_at),
        status=sess.status
    )


@router.get("", response_model=List[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    repo = SessionRepository(db)
    sessions = repo.list_user_sessions(user_id=user.id)
    return [
        SessionOut(
            id=s.id,
            user_id=s.user_id,
            title=s.title,
            domain=s.domain,
            created_at=str(s.created_at),
            status=s.status
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    repo = SessionRepository(db)
    sess = repo.get_session(session_id=session_id, user_id=user.id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied."
        )
    return SessionOut(
        id=sess.id,
        user_id=sess.user_id,
        title=sess.title,
        domain=sess.domain,
        created_at=str(sess.created_at),
        status=sess.status
    )
