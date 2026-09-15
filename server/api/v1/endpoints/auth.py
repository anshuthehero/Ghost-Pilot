"""
Authentication & User API Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from server.database.connection import get_db
from server.database.models import User
from server.database.repository import UserRepository
from server.auth.security import verify_password, get_password_hash, create_access_token
from server.auth.dependencies import get_current_user
from shared.schemas import UserLogin, UserCreate, UserOut, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut)
def register_user(req: UserCreate, db: Session = Depends(get_db)):
    repo = UserRepository(db)
    if repo.get_by_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )
    user = repo.create(
        email=req.email,
        password_hash=get_password_hash(req.password),
        full_name=req.full_name,
        plan="free"
    )
    return UserOut(
        id=user.id,
        email=user.email,
        status=user.status,
        plan=user.plan,
        created_at=str(user.created_at)
    )


@router.post("/login", response_model=Token)
def login_user(req: UserLogin, db: Session = Depends(get_db)):
    repo = UserRepository(db)
    user = repo.get_by_email(req.email)
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    token = create_access_token(data={"sub": user.id, "email": user.email})
    return Token(access_token=token, token_type="bearer", expires_in=86400)


@router.get("/me", response_model=UserOut)
def get_user_profile(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        status=user.status,
        plan=user.plan,
        created_at=str(user.created_at)
    )
