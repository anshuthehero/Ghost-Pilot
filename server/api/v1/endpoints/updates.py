"""
Desktop Application Update & Compatibility API.
Enables backward compatibility negotiation and future auto-update notifications.
"""

from fastapi import APIRouter, Query
from server.config.settings import settings
from shared.schemas import VersionCheckResponse

router = APIRouter(prefix="/updates", tags=["Updates"])


@router.get("/check", response_model=VersionCheckResponse)
def check_desktop_version(client_version: str = Query("1.0.0", description="Installed desktop client version")):
    latest = settings.LATEST_CLIENT_VERSION
    min_required = settings.MIN_REQUIRED_CLIENT_VERSION

    # Simple semver tuple comparison
    def parse_ver(v: str):
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))

    is_outdated = parse_ver(client_version) < parse_ver(latest)

    return VersionCheckResponse(
        current_version=client_version,
        latest_version=latest,
        min_required_version=min_required,
        update_available=is_outdated,
        download_url="https://ghostcopilot.local/download" if is_outdated else None,
        release_notes="Performance enhancements and security updates." if is_outdated else None
    )
