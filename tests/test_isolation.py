"""
Tests for Multi-Tenant Session & User State Isolation.
Verifies that User A cannot access User B's sessions or conversations.
"""

import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.auth.security import create_access_token
from server.database.connection import SessionLocal
from server.database.repository import UserRepository

client = TestClient(app)


def test_session_isolation_between_users():
    db = SessionLocal()
    repo = UserRepository(db)
    user_a = repo.get_or_create_dev_user()
    
    # Create User B
    user_b = repo.get_by_email("user_b@example.com")
    if not user_b:
        user_b = repo.create(email="user_b@example.com", full_name="User B", plan="free")
    
    token_a = create_access_token({"sub": user_a.id, "email": user_a.email})
    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    db.close()

    # User A creates a session
    res_a = client.post(
        "/api/v1/sessions",
        json={"title": "Confidential Interview A", "domain": "technical"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_a.status_code == 200
    session_a_id = res_a.json()["id"]

    # User B attempts to access User A's session
    res_b = client.get(
        f"/api/v1/sessions/{session_a_id}",
        headers={"Authorization": f"Bearer {token_b}"}
    )
    # MUST be 404 / access denied
    assert res_b.status_code == 404
