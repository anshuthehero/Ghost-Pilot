"""
Shared Pydantic Schemas across Ghost Copilot Client and Server.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator


# --- Authentication & User Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    user_id: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: str
    status: str
    plan: str
    created_at: str


# --- Session Schemas ---
class SessionCreate(BaseModel):
    title: Optional[str] = "Interview Session"
    domain: Optional[str] = "general" # technical, consulting, hr, general
    custom_instructions: Optional[str] = None


class SessionOut(BaseModel):
    id: str
    user_id: str
    title: str
    domain: str
    created_at: str
    expires_at: Optional[str] = None
    status: str


class MessageItem(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    timestamp: Optional[float] = None


# --- Copilot Action Schemas ---
class SolveRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000, description="Interview question text")
    session_id: Optional[str] = Field(None, description="Optional active session ID for conversational context")
    duration: Optional[Any] = Field("auto", description="Answer display duration in seconds or 'auto'/'inf'")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Question must contain at least 2 non-whitespace characters.")
        return stripped


class SolveResponse(BaseModel):
    status: str
    gen_id: int
    question: str


class SkipRequest(BaseModel):
    session_id: Optional[str] = None


class ModeRequest(BaseModel):
    mode: Literal["auto", "ptt"]


class DurationRequest(BaseModel):
    duration: Any # 'auto', int, or 'inf'


class SharingRequest(BaseModel):
    mode: Literal["hidden", "visible"]


# --- Feature Flags & Updates ---
class FeatureFlagsResponse(BaseModel):
    enable_auto_vad: bool = True
    enable_speaker_vad: bool = True
    enable_clipboard_solve: bool = True
    max_duration_seconds: int = 60
    custom_system_prompts: bool = True


class VersionCheckResponse(BaseModel):
    current_version: str
    latest_version: str
    min_required_version: str
    update_available: bool
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
