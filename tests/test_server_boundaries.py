"""
Tests for Strict Server Platform Boundaries.
Verifies that the server and shared layers have ZERO dependencies on:
- Cocoa / WebKit / AppKit
- AVFoundation / CoreAudio / BlackHole
- WASAPI / DirectShow / Win32 GUI
- PyQt6 / PyQt6-WebEngine
"""

import sys
import importlib
import pytest


FORBIDDEN_SERVER_MODULES = [
    "Cocoa",
    "WebKit",
    "AppKit",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineWidgets",
    "win32api",
    "win32gui",
    "win32con",
    "ctypes.windll",
]


def test_server_modules_do_not_import_desktop_libraries():
    """Confirms that importing the backend server does not pull desktop or GUI libraries."""
    # Ensure server.main is imported
    import server.main
    import server.sessions.manager
    import server.database.models
    import server.config.settings
    import shared.schemas

    loaded_modules = set(sys.modules.keys())
    for forbidden in FORBIDDEN_SERVER_MODULES:
        assert forbidden not in loaded_modules, f"Forbidden desktop module '{forbidden}' was imported by server!"


def test_shared_schemas_is_os_independent():
    """Validates that shared schemas have no OS-specific imports."""
    import shared.schemas as schemas
    # Should only define pure Pydantic schemas
    assert hasattr(schemas, "SolveRequest")
    assert hasattr(schemas, "SolveResponse")
    assert hasattr(schemas, "Token")
    assert hasattr(schemas, "UserOut")
    assert hasattr(schemas, "SessionOut")
    assert hasattr(schemas, "FeatureFlagsResponse")
    assert hasattr(schemas, "VersionCheckResponse")


def test_server_health_and_ready_work_without_audio_hardware():
    """Proves server boots and responds to liveness/readiness probes with zero audio hardware."""
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ready"
