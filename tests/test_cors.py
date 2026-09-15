"""
Tests for Strict Exact-Match CORS Middleware.
Verifies rejection of attacker domains and substring origin bypass attempts.
"""

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def test_cors_approved_origin_preflight():
    response = client.options(
        "/api/v1/features",
        headers={
            "Origin": "http://localhost:9471",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.status_code == 204
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:9471"


def test_cors_malicious_substring_origin_rejected():
    # Attack vector: Attacker domain embedding 'localhost'
    malicious_origins = [
        "https://localhost.attacker.com",
        "https://evil-localhost.com",
        "http://127.0.0.1.attacker.org",
        "https://attacker.com/localhost"
    ]
    for origin in malicious_origins:
        response = client.options(
            "/api/v1/features",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET"
            }
        )
        assert response.status_code == 403, f"Failed for origin: {origin}"
        assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_simple_request_unauthorized_origin_has_no_cors_headers():
    response = client.get(
        "/health",
        headers={"Origin": "https://malicious-site.com"}
    )
    # Status code is 200 for health, but Access-Control-Allow-Origin MUST NOT be attached
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
