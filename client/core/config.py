"""
Client Configuration and Environment Resolution.
Supports local development, custom backend URLs, and platform detection.
"""

import os
import sys
from typing import Optional


class ClientConfig:
    def __init__(
        self,
        backend_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        session_id: Optional[str] = "default"
    ):
        self.backend_url = backend_url or os.environ.get("COPILOT_BACKEND_URL", "http://127.0.0.1:9471").rstrip("/")
        self.auth_token = auth_token or self._resolve_auth_token()
        self.session_id = session_id or os.environ.get("COPILOT_SESSION_ID", "default")
        self.client_version = "3.0.0"

    @staticmethod
    def _resolve_auth_token() -> str:
        """
        Resolves the session auth token in priority order:
        1. COPILOT_AUTH_TOKEN environment variable (explicit override)
        2. ~/.ghost_copilot/session_token file (written by daemon on first start)
        3. Empty string — unauthenticated (daemon will reject requests)

        This ensures the client and daemon always use the same token,
        even when the daemon auto-generates one at startup.
        """
        # 1. Explicit env override
        env_token = os.environ.get("COPILOT_AUTH_TOKEN", "").strip()
        if env_token:
            return env_token

        # 2. Token file written by app.py daemon
        token_file = os.path.join(os.path.expanduser("~"), ".ghost_copilot", "session_token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    token = f.read().strip()
                if token:
                    return token
            except OSError:
                pass

        # 3. Local directory fallback for portable/restricted Windows environments
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_token_file = os.path.join(repo_root, ".session_token")
        if os.path.exists(local_token_file):
            try:
                with open(local_token_file, "r") as f:
                    token = f.read().strip()
                if token:
                    return token
            except OSError:
                pass

        # 4. No token found — requests will be rejected by the daemon
        return ""

    @property
    def platform(self) -> str:
        if sys.platform == "darwin":
            return "macos"
        elif sys.platform.startswith("win"):
            return "windows"
        return "linux"

    @property
    def is_macos(self) -> bool:
        return self.platform == "macos"

    @property
    def is_windows(self) -> bool:
        return self.platform == "windows"


def get_resource_path(relative_path: str) -> str:
    """
    Resolves path to a bundled resource across dev environments,
    macOS .app bundles, and PyInstaller onedir/onefile distributions.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle (_MEIPASS or executable directory)
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        # Development mode: resolve relative to project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.normpath(os.path.join(base_dir, relative_path))

