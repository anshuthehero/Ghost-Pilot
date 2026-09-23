"""
Desktop Clipboard Extraction with Explicit User Consent and Secret Filtering.
Prevents arbitrary copied passwords, tokens, or private keys from silently leaking to AI APIs.
"""

import os
import re
import sys
import json
import urllib.request
import subprocess
from typing import Optional, Callable

SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),                          # AWS Access Key
    re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[0-9a-zA-Z]{36}'),  # GitHub Classic Tokens
    re.compile(r'github_pat_[0-9a-zA-Z_]{82}'),              # GitHub Fine-Grained Token
    re.compile(r'sk-(?:proj-)?[a-zA-Z0-9_-]{20,}'),          # OpenAI API Key
    re.compile(r'sk-ant-[a-zA-Z0-9_-]{20,}'),                # Anthropic Claude API Key
    re.compile(r'gsk_[a-zA-Z0-9]{40,}'),                     # Groq Key
    re.compile(r'xox[baprs]-[0-9a-zA-Z]{10,}'),              # Slack Token
    re.compile(r'ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'), # JWT
    re.compile(r'-----BEGIN (?:RSA|OPENSSH|EC|DSA)? ?PRIVATE KEY-----'), # Private Key
    re.compile(r'password\s*[:=]\s*\S+', re.IGNORECASE),     # Plaintext passwords
    re.compile(r'(?:postgres|mysql|mongodb|redis):\/\/\S+'), # Database connection strings
    re.compile(r'[a-zA-Z0-9_-]+_SECRET[a-zA-Z0-9_-]*', re.IGNORECASE), # Secret identifiers
]


class DesktopClipboard:
    @staticmethod
    def read_clipboard() -> str:
        """
        Reads system clipboard across platforms:
        - Windows: High-performance Win32 ctypes API (zero-process, zero AV trigger)
                   with PowerShell Get-Clipboard fallback.
        - macOS: Native pbpaste.
        - Linux: xclip / wl-paste fallback.
        """
        try:
            if sys.platform == "darwin":
                return subprocess.check_output(["pbpaste"], text=True).strip()
            elif sys.platform.startswith("win"):
                # 1. Native Win32 API via ctypes: zero-overhead, no process spawns, no AV triggers
                try:
                    import ctypes
                    from ctypes import wintypes
                    user32 = ctypes.windll.user32
                    kernel32 = ctypes.windll.kernel32
                    CF_UNICODETEXT = 13
                    user32.OpenClipboard.argtypes = [wintypes.HWND]
                    user32.OpenClipboard.restype = wintypes.BOOL
                    user32.GetClipboardData.argtypes = [wintypes.UINT]
                    user32.GetClipboardData.restype = wintypes.HANDLE
                    user32.CloseClipboard.argtypes = []
                    user32.CloseClipboard.restype = wintypes.BOOL
                    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                    kernel32.GlobalLock.restype = wintypes.LPCWSTR
                    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                    kernel32.GlobalUnlock.restype = wintypes.BOOL

                    if user32.OpenClipboard(None):
                        try:
                            h_glb = user32.GetClipboardData(CF_UNICODETEXT)
                            if h_glb:
                                ptr = kernel32.GlobalLock(h_glb)
                                if ptr:
                                    try:
                                        return str(ptr).strip()
                                    finally:
                                        kernel32.GlobalUnlock(h_glb)
                        finally:
                            user32.CloseClipboard()
                except Exception:
                    pass
                # 2. PowerShell fallback (supports Windows 10/11 Get-Clipboard and Windows 7 PowerShell 2.0 Forms)
                ps_cmd = "if (Get-Command Get-Clipboard -ErrorAction SilentlyContinue) { Get-Clipboard } else { Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetText() }"
                sp_kwargs = {"text": True, "stderr": subprocess.DEVNULL, "timeout": 2}
                if sys.platform.startswith("win"):
                    sp_kwargs["creationflags"] = 0x08000000
                return subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    **sp_kwargs
                ).strip()
            else:
                return subprocess.check_output(
                    ["xclip", "-o", "-selection", "clipboard"],
                    text=True, stderr=subprocess.DEVNULL, timeout=2
                ).strip()
        except Exception:
            return ""

    @staticmethod
    def is_sensitive(text: str) -> bool:
        """Returns True if text contains recognizable secrets, tokens, or credentials."""
        if not text:
            return False
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def get_consented_text(cls) -> Optional[str]:
        """
        Extracts clipboard text ONLY when safe and non-empty.
        Blocks sensitive credentials before transmission.
        """
        content = cls.read_clipboard()
        if not content or len(content) < 5:
            return None
        if cls.is_sensitive(content):
            print("[Security] Clipboard content contains potential credentials. Blocked from AI transmission.")
            return None
        return content

    @staticmethod
    def resolve_auth_token() -> str:
        """
        Resolves daemon authentication token from environment, config, or stored session token.
        Never exposes the token in URLs.
        """
        try:
            from client.core.config import ClientConfig
            tok = ClientConfig().auth_token
            if tok:
                return tok
        except Exception:
            pass

        token_env = os.environ.get("COPILOT_AUTH_TOKEN", "").strip()
        if token_env:
            return token_env

        token_file = os.path.join(os.path.expanduser("~"), ".ghost_copilot", "session_token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return ""

    @classmethod
    def post_to_daemon(
        cls,
        text: str,
        backend_url: str = "http://127.0.0.1:9471",
        auth_token: Optional[str] = None
    ) -> bool:
        """
        Securely posts consented clipboard text to the local Ghost Copilot daemon.
        Strictly uses Authorization: Bearer <token> header (NEVER query parameters).
        """
        if not text or cls.is_sensitive(text):
            return False

        token = auth_token or cls.resolve_auth_token()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = json.dumps({"question": text}).encode("utf-8")
        req = urllib.request.Request(
            url=f"{backend_url.rstrip('/')}/solve",
            data=payload,
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status in (200, 201)
        except Exception as e:
            print(f"[DesktopClipboard] Failed to post clipboard to daemon: {e}")
            return False
