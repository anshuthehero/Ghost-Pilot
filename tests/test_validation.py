"""
Tests for Request Validation & Oversized Payload Protection.
"""

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def test_empty_question_rejected():
    res = client.post(
        "/api/v1/solve",
        json={"question": "   ", "session_id": "default"}
    )
    assert res.status_code == 422


def test_oversized_question_rejected():
    # 5,000 characters exceeds 4,000 character maximum
    huge_question = "A" * 5000
    res = client.post(
        "/api/v1/solve",
        json={"question": huge_question, "session_id": "default"}
    )
    assert res.status_code == 422
