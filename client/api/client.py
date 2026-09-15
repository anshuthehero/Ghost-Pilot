"""
Unified Cross-Platform API Client for Ghost Copilot.
Used identically by macOS and Windows client frontends.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Callable
from client.core.config import ClientConfig
from client.core.errors import BackendConnectionError


class CopilotApiClient:
    def __init__(self, config: Optional[ClientConfig] = None):
        self.config = config or ClientConfig()

    @property
    def headers(self) -> Dict[str, str]:
        hdrs = {
            "Content-Type": "application/json",
            "User-Agent": f"GhostCopilot-Client/{self.config.client_version} ({self.config.platform})"
        }
        if self.config.auth_token:
            hdrs["Authorization"] = f"Bearer {self.config.auth_token}"
        return hdrs

    def check_health(self) -> Dict[str, Any]:
        """Queries the server /health liveness probe."""
        url = f"{self.config.backend_url}/health"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            raise BackendConnectionError(f"Backend is unreachable at {self.config.backend_url}: {e}")

    def check_readiness(self) -> Dict[str, Any]:
        """Queries the server /ready probe."""
        url = f"{self.config.backend_url}/ready"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"status": "not_ready", "error": str(e)}

    def solve(self, question: str, session_id: Optional[str] = None, duration: Any = "auto") -> Dict[str, Any]:
        """Sends an interview question to the backend for streaming resolution."""
        url = f"{self.config.backend_url}/api/v1/solve"
        payload = {
            "question": question,
            "session_id": session_id or self.config.session_id,
            "duration": duration
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode()
            try: err_json = json.loads(err_msg).get("detail", err_msg)
            except Exception: err_json = err_msg
            raise BackendConnectionError(f"Server error: {err_json}")
        except Exception as e:
            raise BackendConnectionError(f"Failed to submit question: {e}")

    def skip_question(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Aborts active generation for the session and resets cooldown."""
        url = f"{self.config.backend_url}/api/v1/skip"
        payload = {"session_id": session_id or self.config.session_id}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_features(self) -> Dict[str, Any]:
        """Retrieves server-side feature flags."""
        url = f"{self.config.backend_url}/api/v1/features"
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return {"enable_auto_vad": True, "enable_speaker_vad": True}
