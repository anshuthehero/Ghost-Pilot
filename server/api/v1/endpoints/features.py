"""
Server-Side Feature Flags API.
Allows remote feature toggles without shipping new desktop binaries.
"""

from fastapi import APIRouter, Depends
from server.database.models import User
from server.auth.dependencies import get_current_user
from shared.schemas import FeatureFlagsResponse

router = APIRouter(prefix="/features", tags=["Feature Flags"])


@router.get("", response_model=FeatureFlagsResponse)
def get_feature_flags(user: User = Depends(get_current_user)):
    # Can vary flags based on user tier or subscription
    is_pro = user.plan in ("pro", "enterprise", "development")
    return FeatureFlagsResponse(
        enable_auto_vad=True,
        enable_speaker_vad=True,
        enable_clipboard_solve=True,
        max_duration_seconds=60 if not is_pro else 120,
        custom_system_prompts=is_pro
    )
