"""
FastAPI Authentication & Authorization Dependencies.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session
from server.config.settings import settings
from server.database.connection import get_db
from server.database.models import User
from server.database.repository import UserRepository
from server.auth.security import decode_access_token


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticates the incoming request.
    Extracts Bearer token and resolves user identity.
    In development mode, allows local developer bypass or dev token.
    In production mode, strictly enforces valid signed JWT.
    Also sets request.state.user_id so rate limiters can key on user identity (M-3 fix).
    """
    repo = UserRepository(db)

    # 1. Check for Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        
        # Check for development test token
        if settings.APP_ENV == "development" and token == settings.DEV_AUTH_TOKEN:
            user = repo.get_or_create_dev_user()
            request.state.user_id = user.id  # M-3: expose id for rate limiter
            return user
            
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            user = repo.get_by_id(payload["sub"])
            if user and user.status == "active":
                request.state.user_id = user.id  # M-3: expose id for rate limiter
                return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked authentication credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 2. Local development fallback (Allows single-click local running on developer workstation)
    if settings.APP_ENV == "development":
        user = repo.get_or_create_dev_user()
        request.state.user_id = user.id  # M-3: expose id for rate limiter
        return user

    # 3. Production rejection (NEVER allow anonymous access in production)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials are required to access this resource",
        headers={"WWW-Authenticate": "Bearer"}
    )
