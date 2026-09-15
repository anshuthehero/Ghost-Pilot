"""
Tests for Health and Readiness Monitoring Probes.
"""

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "ghost_copilot"
    assert "version" in data


def test_readiness_check_endpoint():
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert "ai_configured" in data
