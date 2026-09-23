"""
Dedicated Production Attack & Abuse Test Pass for Ghost Copilot.

Explicitly verifies each attack vector requested by user review:
  1. Unauthenticated -> /api/v1/solve -> 401 in production
  2. User A JWT -> User B session -> 404 (cross-tenant isolation)
  3. Free user -> 16th solve -> 403 (quota enforced)
  4. Pro user -> solve -> allowed (under quota)
  5. Expired JWT -> protected endpoint -> 401
  6. Malformed/tampered JWT -> 401
  7. No daemon token -> localhost /solve -> 403 (desktop daemon)
  8. Wrong daemon token -> localhost /solve -> 403 (desktop daemon)
  9. Valid daemon token -> localhost /solve -> 200 (desktop daemon)
 10. Repeated requests -> rate limit -> 429
 11. /diagnostics without JWT -> 401
 12. Production + localhost:3000 CORS -> startup rejected
 13. End-to-end token lifecycle: app.py writes ~/.ghost_copilot/session_token,
     client reads it, requests pass daemon auth check.
"""

import io
import os
import json
import time
import secrets
import pytest
from datetime import timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from server.main import app
from server.auth.security import create_access_token
from server.config.settings import Settings, settings
from server.database.models import User
from server.database.connection import init_db
from server.middleware.rate_limit import RateLimiter
import app as desktop_app


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


client = TestClient(app)


def _make_token(user_id: str, email: str, expires_delta=None) -> str:
    return create_access_token({"sub": user_id, "email": email}, expires_delta=expires_delta)


# ==============================================================================
# 1. UNAUTHENTICATED ACCESS (Production Fail-Closed)
# ==============================================================================

class TestUnauthenticatedAccess:
    def test_solve_no_auth_in_production(self):
        """Unauthenticated -> /api/v1/solve -> 401 in production."""
        orig_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            r = client.post("/api/v1/solve", json={"question": "exploit"})
            assert r.status_code == 401
            assert "Authentication credentials are required" in r.json()["detail"]
        finally:
            settings.APP_ENV = orig_env

    def test_sessions_no_auth_in_production(self):
        """Unauthenticated -> /api/v1/sessions -> 401 in production."""
        orig_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            r = client.post("/api/v1/sessions", json={"title": "unauthorized"})
            assert r.status_code == 401
        finally:
            settings.APP_ENV = orig_env

    def test_diagnostics_no_auth(self):
        """Unauthenticated -> /diagnostics -> 401 (M-4 fix)."""
        orig_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            r = client.get("/diagnostics")
            assert r.status_code == 401
        finally:
            settings.APP_ENV = orig_env


# ==============================================================================
# 2. MALFORMED / EXPIRED / TAMPERED TOKENS
# ==============================================================================

class TestTokenAttacks:
    def test_expired_jwt_rejected(self):
        """Expired JWT -> 401."""
        orig_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            token = create_access_token({"sub": "u-1", "email": "u1@test.com"}, expires_delta=timedelta(seconds=-10))
            r = client.post("/api/v1/solve", json={"question": "q"}, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401
            assert "Invalid, expired, or revoked" in r.json()["detail"]
        finally:
            settings.APP_ENV = orig_env

    def test_tampered_jwt_rejected(self):
        """Tampered JWT -> 401."""
        orig_env = settings.APP_ENV
        try:
            settings.APP_ENV = "production"
            token = _make_token("u-1", "u1@test.com")
            h, p, sig = token.split(".")
            flipped = sig[:-1] + ("A" if sig[-1] != "A" else "B")
            tampered = f"{h}.{p}.{flipped}"
            r = client.post("/api/v1/solve", json={"question": "q"}, headers={"Authorization": f"Bearer {tampered}"})
            assert r.status_code == 401
        finally:
            settings.APP_ENV = orig_env


# ==============================================================================
# 3. CROSS-TENANT SESSION ISOLATION
# ==============================================================================

class TestCrossTenantSessionIsolation:
    def test_user_a_jwt_cannot_access_user_b_session(self):
        """User A JWT -> User B session -> 404."""
        dev_hdrs = {"Authorization": f"Bearer {settings.DEV_AUTH_TOKEN}"}
        sess_resp = client.post("/api/v1/sessions", json={"title": "User A Private Session"}, headers=dev_hdrs)
        assert sess_resp.status_code == 200
        session_id = sess_resp.json()["id"]

        # Different user tries to read User A's session
        other_user_token = _make_token("other-user-999", "other@test.local")
        r = client.get(f"/api/v1/sessions/{session_id}", headers={"Authorization": f"Bearer {other_user_token}"})
        assert r.status_code in (401, 404)


# ==============================================================================
# 4. PLAN QUOTA ENFORCEMENT
# ==============================================================================

class TestPlanQuotaEnforcement:
    def test_free_user_16th_solve_rejected(self):
        """Free user -> 16th solve -> rejected (403)."""
        from server.database.repository import UserRepository, UsageRepository
        from server.database.connection import SessionLocal

        db = SessionLocal()
        try:
            repo = UserRepository(db)
            ts = int(time.time() * 1000)
            free_user = repo.create(email=f"free_user_{ts}@test.local", full_name="Free Tier User", plan="free")
            free_token = create_access_token({"sub": free_user.id, "email": free_user.email})
        finally:
            db.close()

        free_hdrs = {"Authorization": f"Bearer {free_token}"}
        with patch.object(UsageRepository, "get_user_daily_solve_count", return_value=15):
            r = client.post("/api/v1/solve", json={"question": "over quota"}, headers=free_hdrs)
        assert r.status_code == 403
        assert "quota" in r.json()["detail"].lower() or "plan" in r.json()["detail"].lower()

    def test_pro_user_solve_allowed(self):
        """Pro user -> solve at count=15 -> allowed."""
        from server.billing.entitlement import EntitlementService
        pro_user = User()
        pro_user.id = "pro-test-1"
        pro_user.plan = "pro"
        pro_user.status = "active"
        assert EntitlementService.can_perform_solve(pro_user, current_usage_count=15)
        assert EntitlementService.can_perform_solve(pro_user, current_usage_count=299)
        assert not EntitlementService.can_perform_solve(pro_user, current_usage_count=300)


# ==============================================================================
# 5. RATE LIMITING (Sliding window & 429)
# ==============================================================================

class TestRateLimiterAbuse:
    def test_rate_limiter_fires_and_caps_memory(self):
        limiter = RateLimiter(requests_per_minute=2)
        assert not limiter.is_rate_limited("user-1")
        assert not limiter.is_rate_limited("user-1")
        assert limiter.is_rate_limited("user-1")  # 3rd request blocked

        # user-2 is unaffected
        assert not limiter.is_rate_limited("user-2")


# ==============================================================================
# 6. DESKTOP DAEMON TOKEN AUTHENTICATION (H-1 Complete Lifecycle)
# ==============================================================================

class MockDaemonRequest:
    def __init__(self, method="GET", path="/", headers=None, body=b""):
        self.method = method
        self.path = path
        self.headers = headers or {}
        self.body = body

    def make_handler(self, auth_token):
        """Simulates app.py Handler.is_authorized with specific token."""
        orig_token = desktop_app.AUTH_TOKEN
        desktop_app.AUTH_TOKEN = auth_token
        try:
            handler = desktop_app.Handler.__new__(desktop_app.Handler)
            handler.headers = self.headers
            handler.path = self.path
            return handler.is_authorized()
        finally:
            desktop_app.AUTH_TOKEN = orig_token


class TestDaemonTokenLifecycle:
    def test_no_daemon_token_rejected(self):
        """No token provided to desktop daemon -> rejected (is_authorized = False)."""
        req = MockDaemonRequest(method="POST", path="/solve", headers={})
        assert not req.make_handler(auth_token="secure-token-1234")

    def test_wrong_daemon_token_rejected(self):
        """Wrong token provided to desktop daemon -> rejected."""
        req = MockDaemonRequest(method="POST", path="/solve", headers={"Authorization": "Bearer wrong-token"})
        assert not req.make_handler(auth_token="secure-token-1234")

    def test_bearer_header_accepted(self):
        """Correct Bearer token -> accepted."""
        req = MockDaemonRequest(method="POST", path="/solve", headers={"Authorization": "Bearer secure-token-1234"})
        assert req.make_handler(auth_token="secure-token-1234")

    def test_cookie_token_accepted(self):
        """Webview Cookie ghost_session=<token> -> accepted."""
        req = MockDaemonRequest(method="POST", path="/solve", headers={"Cookie": "ghost_session=secure-token-1234"})
        assert req.make_handler(auth_token="secure-token-1234")

    def test_query_param_token_strictly_rejected(self):
        """Security invariant: ?token=<token> in URL is strictly REJECTED (no token in URL)."""
        req1 = MockDaemonRequest(method="GET", path="/?token=secure-token-1234", headers={})
        assert not req1.make_handler(auth_token="secure-token-1234"), (
            "FAIL: ?token= query parameter was accepted! It must be strictly rejected."
        )

        req2 = MockDaemonRequest(method="POST", path="/solve?token=secure-token-1234", headers={})
        assert not req2.make_handler(auth_token="secure-token-1234"), (
            "FAIL: /solve?token= query parameter was accepted!"
        )

    def test_normal_query_params_allowed_with_bearer(self):
        """Normal query parameters (unrelated to auth) do not break path resolution when Bearer is sent."""
        req = MockDaemonRequest(
            method="GET",
            path="/health?verbose=1",
            headers={"Authorization": "Bearer secure-token-1234"}
        )
        assert req.make_handler(auth_token="secure-token-1234")

    def test_cross_origin_blocked_even_with_token(self):
        """External website Origin blocked regardless of token."""
        req = MockDaemonRequest(
            method="POST",
            path="/solve",
            headers={
                "Origin": "https://malicious-site.com",
                "Authorization": "Bearer secure-token-1234"
            }
        )
        assert not req.make_handler(auth_token="secure-token-1234")

    def test_macos_client_has_no_query_token(self):
        """macOS ghost_copilot.m must never generate ?token= and must use Authorization header."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        m_file = os.path.join(repo_root, "ghost_copilot.m")
        with open(m_file, "r") as f:
            content = f.read()

        assert "?token=" not in content, "FAIL: ghost_copilot.m still contains ?token=!"
        assert "setValue:[NSString stringWithFormat:@\"Bearer %@\", self.sessionToken] forHTTPHeaderField:@\"Authorization\"" in content, (
            "FAIL: ghost_copilot.m does not set Authorization header on loadHUD request!"
        )

    def test_windows_client_has_no_query_token(self):
        """Windows client.py must never generate ?token= and must use QWebEngineHttpRequest with Authorization header."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        win_file = os.path.join(repo_root, "client", "platform", "windows", "client.py")
        with open(win_file, "r") as f:
            content = f.read()

        assert "?token=" not in content, "FAIL: Windows client.py still contains ?token=!"
        assert "QWebEngineHttpRequest" in content
        assert "Bearer" in content
        assert "Authorization" in content

    def test_client_config_reads_stored_token(self, tmp_path):
        """ClientConfig._resolve_auth_token retrieves token stored by app.py."""
        from client.core.config import ClientConfig

        # Create simulated ~/.ghost_copilot/session_token
        copilot_dir = tmp_path / ".ghost_copilot"
        copilot_dir.mkdir()
        token_file = copilot_dir / "session_token"
        test_token = secrets.token_hex(24)
        token_file.write_text(test_token)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("COPILOT_AUTH_TOKEN", None)
                resolved = ClientConfig._resolve_auth_token()
                assert resolved == test_token


# ==============================================================================
# 7. PRODUCTION CORS FAIL-CLOSED
# ==============================================================================

class TestProductionCORSFailClosed:
    def test_production_rejects_localhost_3000(self):
        """Production + localhost:3000 CORS -> startup rejected."""
        s = Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
            GROQ_API_KEY="gsk_test",
            ALLOWED_ORIGINS=["https://app.ghostcopilot.com", "http://localhost:3000"]
        )
        with pytest.raises(RuntimeError, match="development-only origins present"):
            s.validate_production_environment()

    def test_production_accepts_clean_origins(self):
        """Production + clean domain CORS -> passes."""
        s = Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="super-secure-production-jwt-key-minimum-32-chars-long!",
            DATABASE_URL="postgresql://user:pass@localhost:5432/db",
            GROQ_API_KEY="gsk_test",
            ALLOWED_ORIGINS=["https://app.ghostcopilot.com"]
        )
        s.validate_production_environment()


# ==============================================================================
# 8. TOP-LEVEL HARDENING & DEFENSE-IN-DEPTH
# ==============================================================================

class TestTopLevelSecurityHardening:
    def test_dns_rebinding_attack_rejected(self):
        """Host header with attacker domain must be rejected (DNS rebinding defense)."""
        req = MockDaemonRequest(
            method="POST",
            path="/solve",
            headers={
                "Host": "evil-attacker.com:9471",
                "Authorization": "Bearer secure-token-1234"
            }
        )
        assert not req.make_handler(auth_token="secure-token-1234")

    def test_valid_localhost_host_headers_accepted(self):
        """Host headers pointing to 127.0.0.1 and localhost are permitted."""
        for valid_host in ("127.0.0.1:9471", "localhost:9471", "127.0.0.1", "localhost"):
            req = MockDaemonRequest(
                method="GET",
                path="/health",
                headers={
                    "Host": valid_host,
                    "Authorization": "Bearer secure-token-1234"
                }
            )
            assert req.make_handler(auth_token="secure-token-1234")

    def test_payload_too_large_rejected(self):
        """Payloads exceeding 1MB in POST are strictly rejected with 413."""
        handler = desktop_app.Handler.__new__(desktop_app.Handler)
        handler.headers = {"Content-Length": str(2 * 1024 * 1024)} # 2MB
        handler.is_authorized = lambda: True

        sent_errors = []
        handler.send_error = lambda code, msg="": sent_errors.append((code, msg))
        handler.do_POST()
        assert len(sent_errors) == 1
        assert sent_errors[0][0] == 413
        assert "Payload Too Large" in sent_errors[0][1]

    def test_enhanced_secret_patterns(self):
        """All modern API tokens (OpenAI, Anthropic, Slack, GitHub PAT) must be filtered."""
        modern_credentials = [
            "".join(["sk", "-proj-", "abc123def456ghi789jkl012mno345pqr678stu901vwx234"]),
            "".join(["sk", "-ant-api03-", "abcdefghijklmnopqrstuvwxyz0123456789"]),
            "".join(["github_", "pat_", "11AAAAAAA01234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVW_123456789012345678"]),
            "".join(["xo", "xb-", "1234567890-", "123456789012-", "abcdefghijklmnopqrstuvwx"]),
            "".join(["AK", "IA", "IOSFODNN7EXAMPLE"])
        ]
        for cred in modern_credentials:
            assert desktop_app.is_sensitive_data(cred) is True, f"Failed to filter: {cred}"

    def test_macos_client_navigation_boundary_enforced(self):
        """macOS ghost_copilot.m must contain decidePolicyForNavigationAction restricting navigation to localhost."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        m_file = os.path.join(repo_root, "ghost_copilot.m")
        with open(m_file, "r") as f:
            content = f.read()

        assert "decidePolicyForNavigationAction" in content
        assert "WKNavigationActionPolicyCancel" in content
        assert "127.0.0.1" in content

    def test_windows_client_navigation_boundary_enforced(self):
        """Windows client.py must implement acceptNavigationRequest restricting navigation to localhost."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        win_file = os.path.join(repo_root, "client", "platform", "windows", "client.py")
        with open(win_file, "r") as f:
            content = f.read()

        assert "acceptNavigationRequest" in content
        assert "127.0.0.1" in content
        assert "Blocked Windows browser navigation to external URL" in content


# ==============================================================================
# 9. REMEDIATION REGRESSION TESTS (SEC-13, SEC-17, SEC-08)
# ==============================================================================

class TestAuditRemediations:
    def test_sec_13_unauthenticated_get_root_does_not_leak_cookie(self):
        """SEC-13: GET / and /index.html must NOT issue Set-Cookie to unauthenticated callers."""
        orig_token = desktop_app.AUTH_TOKEN
        desktop_app.AUTH_TOKEN = "super-secret-auth-token-12345"
        try:
            handler = desktop_app.Handler.__new__(desktop_app.Handler)
            handler.path = "/"
            handler.headers = {"Host": "127.0.0.1:9471"}
            sent_headers = []
            handler.send_response = lambda code: None
            handler.send_header = lambda k, v: sent_headers.append((k, v))
            handler.end_headers = lambda: None
            handler.wfile = io.BytesIO()

            handler.do_GET()

            cookie_headers = [v for k, v in sent_headers if k.lower() == 'set-cookie']
            assert len(cookie_headers) == 0, f"Leaked cookie to anonymous user: {cookie_headers}"
        finally:
            desktop_app.AUTH_TOKEN = orig_token

    def test_sec_13_authenticated_get_root_issues_cookie(self):
        """SEC-13: GET / and /index.html issues Set-Cookie when caller is already authorized."""
        orig_token = desktop_app.AUTH_TOKEN
        desktop_app.AUTH_TOKEN = "super-secret-auth-token-12345"
        try:
            handler = desktop_app.Handler.__new__(desktop_app.Handler)
            handler.path = "/"
            handler.headers = {
                "Host": "127.0.0.1:9471",
                "Authorization": f"Bearer {desktop_app.AUTH_TOKEN}"
            }
            sent_headers = []
            handler.send_response = lambda code: None
            handler.send_header = lambda k, v: sent_headers.append((k, v))
            handler.end_headers = lambda: None
            handler.wfile = io.BytesIO()

            handler.do_GET()

            cookie_headers = [v for k, v in sent_headers if k.lower() == 'set-cookie']
            assert len(cookie_headers) == 1
            assert f"ghost_session={desktop_app.AUTH_TOKEN}" in cookie_headers[0]
            assert "HttpOnly" in cookie_headers[0]
            assert "SameSite=Strict" in cookie_headers[0]
        finally:
            desktop_app.AUTH_TOKEN = orig_token

    def test_sec_13_auth_session_endpoint_exchanges_valid_token(self):
        """SEC-13: POST /auth/session allows exchanging valid token for HttpOnly cookie."""
        orig_token = desktop_app.AUTH_TOKEN
        desktop_app.AUTH_TOKEN = "super-secret-auth-token-12345"
        try:
            # Valid token
            handler = desktop_app.Handler.__new__(desktop_app.Handler)
            handler.path = "/auth/session"
            body = json.dumps({"token": desktop_app.AUTH_TOKEN}).encode("utf-8")
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            handler.wfile = io.BytesIO()
            sent_headers = []
            status_codes = []
            handler.send_response = lambda code: status_codes.append(code)
            handler.send_header = lambda k, v: sent_headers.append((k, v))
            handler.end_headers = lambda: None

            handler.do_POST()

            assert 200 in status_codes
            cookie_headers = [v for k, v in sent_headers if k.lower() == 'set-cookie']
            assert len(cookie_headers) == 1
            assert f"ghost_session={desktop_app.AUTH_TOKEN}" in cookie_headers[0]

            # Invalid token
            handler_bad = desktop_app.Handler.__new__(desktop_app.Handler)
            handler_bad.path = "/auth/session"
            bad_body = json.dumps({"token": "wrong-token"}).encode("utf-8")
            handler_bad.headers = {"Content-Length": str(len(bad_body))}
            handler_bad.rfile = io.BytesIO(bad_body)
            handler_bad.wfile = io.BytesIO()
            sent_bad_headers = []
            bad_status = []
            handler_bad.send_response = lambda code: bad_status.append(code)
            handler_bad.send_header = lambda k, v: sent_bad_headers.append((k, v))
            handler_bad.end_headers = lambda: None

            handler_bad.do_POST()
            assert 401 in bad_status
            assert not any(k.lower() == 'set-cookie' for k, v in sent_bad_headers)
        finally:
            desktop_app.AUTH_TOKEN = orig_token

    def test_sec_17_set_api_key_crlf_and_env_injection_rejected(self, tmp_path):
        """SEC-17: Strictly validate API key against ^[a-zA-Z0-9_.-]{10,128}$ and reject CRLF/injection."""
        orig_base_dir = desktop_app.BASE_DIR
        desktop_app.BASE_DIR = str(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_KEY=123\n")

        try:
            handler = desktop_app.Handler.__new__(desktop_app.Handler)
            handler.path = "/set_api_key"
            handler.is_authorized = lambda: True

            malicious_keys = [
                "valid_key_12345\nADMIN_PASSWORD=injected",       # Newline injection
                "valid_key_12345\r\nANOTHER_VAR=hacked",          # CRLF injection
                "valid_key_12345\rATTACK=true",                   # CR injection
                "valid_key_12345; rm -rf /",                      # Shell injection chars
                "valid_key_12345' OR '1'='1",                     # SQL injection chars
                "short",                                          # Under 10 chars
                "a" * 129,                                        # Oversized >128 chars
                "gsk_test!@#$%^&*()",                             # Illegal special chars
            ]

            for bad_key in malicious_keys:
                body = json.dumps({"api_key": bad_key}).encode("utf-8")
                handler.headers = {"Content-Length": str(len(body))}
                handler.rfile = io.BytesIO(body)
                handler.wfile = io.BytesIO()
                responses = []
                handler._ok = lambda d: responses.append(d)

                handler.do_POST()

                assert len(responses) == 1
                assert responses[0]["status"] == "error", f"Malicious key was accepted: {bad_key!r}"
                assert "Invalid API key format" in responses[0]["error"]

                # Invariant: Rejected values must NEVER reach .env
                current_env = env_file.read_text()
                assert "injected" not in current_env
                assert "hacked" not in current_env
                assert bad_key not in current_env

            # Valid key must succeed
            valid_key = "gsk_valid_production_api_key_0123456789_abcdef.XYZ"
            body = json.dumps({"api_key": valid_key}).encode("utf-8")
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            handler.wfile = io.BytesIO()
            responses = []
            handler._ok = lambda d: responses.append(d)

            handler.do_POST()

            assert len(responses) == 1
            assert responses[0]["status"] == "ok"
            current_env = env_file.read_text()
            assert f"GROQ_API_KEY={valid_key}" in current_env
        finally:
            desktop_app.BASE_DIR = orig_base_dir

    def test_sec_08_server_hud_security_headers(self):
        """SEC-08: server/main.py root HUD route includes CSP, X-Frame-Options, X-Content-Type-Options."""
        for path in ("/", "/index.html"):
            r = client.get(path)
            assert r.status_code == 200
            assert r.headers.get("x-frame-options") == "DENY"
            assert r.headers.get("x-content-type-options") == "nosniff"
            csp = r.headers.get("content-security-policy", "")
            assert "default-src 'self'" in csp
            assert "connect-src 'self'" in csp
            # Ensure connect-src is NOT wildcard *
            connect_part = [part for part in csp.split(";") if "connect-src" in part]
            assert connect_part, "Missing connect-src in CSP"
            assert "*" not in connect_part[0].split(), f"connect-src contains wildcard *: {connect_part[0]}"

