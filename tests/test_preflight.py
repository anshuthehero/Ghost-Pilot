"""
Tests for Preflight Diagnostic & Readiness Audits.
"""

import pytest
from client.diagnostics.preflight import PreflightChecker
from client.core.config import ClientConfig


def test_preflight_audit_structure():
    checker = PreflightChecker()
    audit = checker.run_full_audit()

    assert "platform" in audit
    assert "python_version" in audit
    assert "client_version" in audit
    assert "overall_status" in audit
    assert "can_start_application" in audit
    assert audit["can_start_application"] is True
    assert "components" in audit
    assert "ffmpeg" in audit["components"]
    assert "audio" in audit["components"]
    assert "backend" in audit["components"]
    assert "recommendation" in audit


def test_preflight_ffmpeg_detection():
    checker = PreflightChecker()
    ffmpeg_result = checker.check_ffmpeg()

    assert "status" in ffmpeg_result
    assert ffmpeg_result["status"] in ["READY", "MISSING"]
    if ffmpeg_result["status"] == "READY":
        assert ffmpeg_result["path"] is not None
    else:
        assert "user_hint" in ffmpeg_result


def test_preflight_non_blocking_policy():
    """Confirms preflight never blocks client launch even under degraded audio/backend conditions."""
    config = ClientConfig(backend_url="http://invalid.nonexistent:9999")
    checker = PreflightChecker(config)
    audit = checker.run_full_audit()

    assert audit["can_start_application"] is True
    assert audit["components"]["backend"]["status"] == "UNAVAILABLE"
