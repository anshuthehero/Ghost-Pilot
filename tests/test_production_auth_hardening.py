"""
Automated Security Regression Tests for Production Auth Hardening.
Verifies that root/legacy compatibility routes (/solve, /stream, /skip_question, etc.)
strictly fail closed with 401 in production, while preserving seamless developer
desktop compatibility in development mode.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from server.config.settings import settings
from server.main import app
from server.database.connection import SessionLocal, init_db
from server.database.models import User, Session as UserSession, Usage
from server.database.repository import UserRepository, SessionRepository
from server.auth.security import create_access_token
from server.sessions.manager import session_manager


@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)


@pytest.fixture
def auth_tokens():
    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        ts = int(time.time() * 1000)
        u1 = user_repo.create(email=f"prod_u1_{ts}@test.local", full_name="User A")
        u2 = user_repo.create(email=f"prod_u2_{ts}@test.local", full_name="User B")
        
        valid_u1 = create_access_token({"sub": u1.id, "email": u1.email})
        valid_u2 = create_access_token({"sub": u2.id, "email": u2.email})
        
        expired = create_access_token(
            {"sub": u1.id, "email": u1.email},
            expires_delta=timedelta(seconds=-3600)
        )
        
        orig_key = settings.JWT_SECRET_KEY
        try:
            settings.JWT_SECRET_KEY = "tampered-secret-key-12345678901234567890"
            tampered = create_access_token({"sub": u1.id, "email": u1.email})
        finally:
            settings.JWT_SECRET_KEY = orig_key
            
        return {
            "u1": u1,
            "u2": u2,
            "token_u1": valid_u1,
            "token_u2": valid_u2,
            "expired": expired,
            "tampered": tampered,
        }
    finally:
        db.close()


# ==============================================================================
# 1. PRODUCTION FAIL-CLOSED TESTS
# ==============================================================================

def test_production_solve_no_auth_fails_closed(client):
    """POST /solve without authentication in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.post("/solve", json={"question": "Exploit question?"})
        assert resp.status_code == 401
        assert "Authentication credentials are required" in resp.json()["detail"]
    finally:
        settings.APP_ENV = orig_env


def test_production_solve_malformed_auth_fails_closed(client):
    """POST /solve with malformed header in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.post(
            "/solve",
            json={"question": "Exploit question?"},
            headers={"Authorization": "Bearer malformed.token.here"}
        )
        assert resp.status_code == 401
    finally:
        settings.APP_ENV = orig_env


def test_production_solve_expired_auth_fails_closed(client, auth_tokens):
    """POST /solve with expired token in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.post(
            "/solve",
            json={"question": "Exploit question?"},
            headers={"Authorization": f"Bearer {auth_tokens['expired']}"}
        )
        assert resp.status_code == 401
        assert "Invalid, expired, or revoked" in resp.json()["detail"]
    finally:
        settings.APP_ENV = orig_env


def test_production_solve_tampered_auth_fails_closed(client, auth_tokens):
    """POST /solve with tampered token in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.post(
            "/solve",
            json={"question": "Exploit question?"},
            headers={"Authorization": f"Bearer {auth_tokens['tampered']}"}
        )
        assert resp.status_code == 401
        assert "Invalid, expired, or revoked" in resp.json()["detail"]
    finally:
        settings.APP_ENV = orig_env


def test_production_stream_no_auth_fails_closed(client):
    """GET /stream without authentication in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.get("/stream")
        assert resp.status_code == 401
        assert "Authentication credentials are required" in resp.json()["detail"]
    finally:
        settings.APP_ENV = orig_env


def test_production_stream_malformed_auth_fails_closed(client):
    """GET /stream with malformed header in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.get("/stream", headers={"Authorization": "Bearer malformed-token"})
        assert resp.status_code == 401
    finally:
        settings.APP_ENV = orig_env


def test_production_stream_expired_auth_fails_closed(client, auth_tokens):
    """GET /stream with expired token in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.get("/stream", headers={"Authorization": f"Bearer {auth_tokens['expired']}"})
        assert resp.status_code == 401
    finally:
        settings.APP_ENV = orig_env


def test_production_stream_tampered_auth_fails_closed(client, auth_tokens):
    """GET /stream with tampered token in production must return 401."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        resp = client.get("/stream", headers={"Authorization": f"Bearer {auth_tokens['tampered']}"})
        assert resp.status_code == 401
    finally:
        settings.APP_ENV = orig_env


def test_production_state_endpoints_fail_closed(client):
    """State-changing compatibility endpoints must fail closed in production without auth."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        assert client.post("/set_mode", json={"mode": "auto"}).status_code == 401
        assert client.post("/set_sharing", json={"mode": "visible"}).status_code == 401
        assert client.post("/set_duration", json={"duration": 30}).status_code == 401
        assert client.post("/skip_question").status_code == 401
        assert client.get("/sharing_mode").status_code == 401
    finally:
        settings.APP_ENV = orig_env


def test_production_unauth_does_not_mutate_db_or_queues(client):
    """Verify that unauthenticated production attempts do not write to DB or spawn SSE queues."""
    orig_env = settings.APP_ENV
    db = SessionLocal()
    try:
        settings.APP_ENV = "production"
        initial_usage_count = db.query(Usage).count()
        initial_session_count = db.query(UserSession).count()
        
        # Attack attempts
        client.post("/solve", json={"question": "Unauth attack question"})
        client.post("/solve", json={"question": "Another attack"}, headers={"Authorization": "Bearer bad"})
        client.get("/stream")
        
        # Verify no usage record was written
        assert db.query(Usage).count() == initial_usage_count
        # Verify no new session was created
        assert db.query(UserSession).count() == initial_session_count
    finally:
        db.close()
        settings.APP_ENV = orig_env


# ==============================================================================
# 2. DEVELOPMENT COMPATIBILITY PRESERVATION
# ==============================================================================

def test_development_compatibility_routes_succeed(client):
    """Verify desktop app routes continue to work seamlessly in development mode."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "development"
        
        # Mode switch
        r_mode = client.post("/set_mode", json={"mode": "auto"})
        assert r_mode.status_code == 200
        assert r_mode.json()["auto"] is True
        
        # Sharing switch
        r_sharing = client.post("/set_sharing", json={"mode": "hidden"})
        assert r_sharing.status_code == 200
        assert r_sharing.json()["sharing"] == "hidden"
        
        # Sharing mode poll
        r_poll = client.get("/sharing_mode")
        assert r_poll.status_code == 200
        assert r_poll.json()["mode"] == "hidden"
        
        # Duration switch
        r_dur = client.post("/set_duration", json={"duration": "auto"})
        assert r_dur.status_code == 200
        assert r_dur.json()["duration"] == "auto"
        
        # Skip question
        r_skip = client.post("/skip_question")
        assert r_skip.status_code == 200
        assert r_skip.json()["status"] == "skipped"
        
        # Solve
        r_solve = client.post("/solve", json={"question": "What is Python?"})
        assert r_solve.status_code == 200
        assert r_solve.json()["status"] == "ok"
    finally:
        settings.APP_ENV = orig_env


# ==============================================================================
# 3. AUTHENTICATED MULTI-TENANT & IDOR PRESERVATION
# ==============================================================================

def test_authenticated_user_access_and_cross_tenant_isolation(client, auth_tokens):
    """Verify authenticated User A works, while User B cannot access User A's resources."""
    orig_env = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        headers_a = {"Authorization": f"Bearer {auth_tokens['token_u1']}"}
        headers_b = {"Authorization": f"Bearer {auth_tokens['token_u2']}"}
        
        # User A creates a session
        r_sess_a = client.post("/api/v1/sessions", json={"title": "Private Session A"}, headers=headers_a)
        assert r_sess_a.status_code == 200
        sess_a_id = r_sess_a.json()["id"]
        
        # User A can access own session
        r_get_a = client.get(f"/api/v1/sessions/{sess_a_id}", headers=headers_a)
        assert r_get_a.status_code == 200
        assert r_get_a.json()["id"] == sess_a_id
        
        # User B CANNOT access User A's session
        r_get_b = client.get(f"/api/v1/sessions/{sess_a_id}", headers=headers_b)
        assert r_get_b.status_code == 404
        
        # User B CANNOT solve against User A's session
        r_solve_b = client.post(
            "/api/v1/solve",
            json={"question": "Intrusion", "session_id": sess_a_id},
            headers=headers_b
        )
        assert r_solve_b.status_code == 404
        
        # User B CANNOT read history of User A's session
        r_hist_b = client.get(f"/api/v1/history/{sess_a_id}", headers=headers_b)
        assert r_hist_b.status_code == 404
        
        # User A can solve via compat route using User A's JWT
        r_compat_solve_a = client.post("/solve", json={"question": "Legitimate question"}, headers=headers_a)
        assert r_compat_solve_a.status_code == 200
        assert r_compat_solve_a.json()["status"] == "ok"
    finally:
        settings.APP_ENV = orig_env
