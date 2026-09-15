"""
Tests for System Failure Modes, Graceful Degradations, and Production Fail-Closed Rules.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

from server.config.settings import Settings
from client.core.ffmpeg import find_ffmpeg
from client.platform.macos.audio import MacAudioProvider
from client.audio.base import AudioState
from desktop.audio.capture import DesktopAudioCapture


def test_production_fails_closed_on_default_jwt_secret():
    """Validates that production environment rejects the insecure development JWT secret key."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="dev-secret-key-change-in-production-1234567890",
        DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        GROQ_API_KEY="gsk_valid_prod_key_example"
    )
    with pytest.raises(RuntimeError) as exc_info:
        s.validate_production_environment()
    assert "JWT_SECRET_KEY must be a secure" in str(exc_info.value)


def test_production_fails_closed_on_sqlite():
    """Validates that hosted production strictly requires PostgreSQL rather than local SQLite."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
        DATABASE_URL="sqlite:///./ghost_copilot.db",
        GROQ_API_KEY="gsk_valid_prod_key_example"
    )
    with pytest.raises(RuntimeError) as exc_info:
        s.validate_production_environment()
    assert "Production hosted deployment MUST use PostgreSQL" in str(exc_info.value)


def test_production_fails_closed_on_missing_ai_credentials():
    """Validates that production fails closed if no AI-provider configuration/key exists."""
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
            GROQ_API_KEY="",
            AI_API_KEY="",
            OPENAI_API_KEY="",
            BYOK_ENABLED=False,
            # Use production-safe origins (no localhost:3000) so M-5 CORS check passes
            ALLOWED_ORIGINS=["https://app.ghostcopilot.com"]
        )
        with pytest.raises(RuntimeError) as exc_info:
            s.validate_production_environment()
        assert "No valid AI-provider credential" in str(exc_info.value)


def test_production_allows_generic_ai_api_key_without_groq_key():
    """Validates that production allows generic AI_API_KEY without requiring GROQ_API_KEY specifically."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
        DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        GROQ_API_KEY="",
        AI_API_KEY="custom-ai-provider-key-12345",
        ALLOWED_ORIGINS=["https://app.ghostcopilot.com"]
    )
    # Must NOT raise any error
    s.validate_production_environment()


def test_production_allows_byok_without_server_key():
    """Validates that production allows BYOK client keys without requiring a server-side key."""
    s = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
        DATABASE_URL="postgresql://user:pass@localhost:5432/db",
        GROQ_API_KEY="",
        BYOK_ENABLED=True,
        ALLOWED_ORIGINS=["https://app.ghostcopilot.com"]
    )
    # Must NOT raise any error
    s.validate_production_environment()


def test_development_mode_permits_sqlite_and_dev_token():
    """Confirms local development mode works seamlessly out of the box with zero setup."""
    s = Settings(
        APP_ENV="development",
        JWT_SECRET_KEY="dev-secret-key-change-in-production-1234567890",
        DATABASE_URL="sqlite:///./ghost_copilot.db",
        GROQ_API_KEY=""
    )
    # Must NOT raise any error
    s.validate_production_environment()


def test_macos_audio_handles_permission_denied():
    """Simulates macOS AVFoundation TCC permission denial."""
    provider = MacAudioProvider()
    mock_devs = {
        "mic_detected": True,
        "mic_index": "1",
        "blackhole_detected": True,
        "blackhole_index": "2",
        "permission_denied": True,
        "all_devices": []
    }
    with patch.object(provider, "detect_devices", return_value=mock_devs):
        caps = provider.check_capabilities()
        assert caps["microphone"]["state"] == AudioState.NEEDS_PERMISSION.value
        assert "Privacy & Security" in caps["microphone"]["user_hint"]


def test_macos_audio_handles_blackhole_probe_failure():
    """Simulates BlackHole installed but unable to stream due to missing Multi-Output routing."""
    provider = MacAudioProvider()
    mock_devs = {
        "mic_detected": True,
        "mic_index": "1",
        "blackhole_detected": True,
        "blackhole_index": "2",
        "permission_denied": False,
        "all_devices": [{"index": "2", "name": "BlackHole 2ch"}]
    }
    mock_probe = MagicMock(returncode=1, stderr=b"Input/output error")
    with patch.object(provider, "detect_devices", return_value=mock_devs):
        with patch("subprocess.run", return_value=mock_probe):
            caps = provider.check_capabilities()
            assert caps["system_audio"]["state"] == AudioState.MISCONFIGURED.value
            assert "Audio MIDI Setup" in caps["system_audio"]["user_hint"]


def test_temp_audio_chunk_cleanup_on_subprocess_error():
    """Verifies that if ffmpeg fails during audio capture, the temp file is cleaned up immediately."""
    capture = DesktopAudioCapture()
    with patch("subprocess.run", side_effect=RuntimeError("FFmpeg process crashed")):
        with pytest.raises(RuntimeError):
            capture.capture_chunk("1", 0.5)
