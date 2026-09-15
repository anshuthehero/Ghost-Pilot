"""
Tests for Authentication & Token Verification.
"""

from fastapi.testclient import TestClient
from server.main import app
from server.auth.security import create_access_token, decode_access_token
from server.config.settings import settings

client = TestClient(app)


def test_token_creation_and_decoding():
    token = create_access_token({"sub": "user-123", "email": "test@example.com"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"


def test_invalid_token_rejected():
    invalid_token = "invalid.token.structure"
    payload = decode_access_token(invalid_token)
    assert payload is None

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-tampered-token"}
    )
    assert response.status_code == 401


def test_dev_token_accepted_in_dev_mode():
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {settings.DEV_AUTH_TOKEN}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "dev@ghostcopilot.local"
    assert data["plan"] == "development"
