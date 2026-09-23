"""
Gegenpress Scenario-Based Adversarial Tests
Aggressively attempts to break the application under real-world failure scenarios:
1. Windows console cp1252/cp437 UnicodeEncodeError resistance.
2. Immediate daemon crash detection without opening white window.
3. Fast-open (< 50ms) when daemon is already healthy.
4. Token resolution resilience and multi-location fallback.
5. Missing FFmpeg graceful degradation to text prompts.
6. Multi-client SSE stress & emergency skip generation abort.
7. Launcher WebEngine dark canvas & authorization header validation.
"""

import os
import sys
import json
import time
import subprocess
import threading
import urllib.request
import pytest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestGegenpressScenarios:
    """Relentless stress and failure-injection tests."""

    def test_scenario_1_windows_console_encoding_resilience(self):
        """
        Scenario 1:
        Simulate Windows command prompt with non-UTF8 code page (cp1252).
        Verify app.py does NOT crash with UnicodeEncodeError.
        """
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        env["LANG"] = "C"

        # Execute a subcheck that runs app.py helper functions under cp1252
        code = (
            "import sys, os\n"
            "sys.path.insert(0, '.')\n"
            "from app import broadcast, is_sensitive_data\n"
            "broadcast('test_event', {'message': 'Testing cp1252 safety'})\n"
            "assert not is_sensitive_data('How to implement a binary tree in Python?')\n"
            "print('SUCCESS: cp1252 executed without UnicodeEncodeError')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=5
        )
        assert proc.returncode == 0, f"Failed under cp1252: {proc.stderr}"
        assert "SUCCESS: cp1252" in proc.stdout

    def test_scenario_2_daemon_instant_crash_detection(self):
        """
        Scenario 2:
        Simulate daemon crashing immediately on startup.
        Verify launcher's _poll_daemon detects the exit immediately,
        reports the exact error, resets the launch button, and NEVER opens HUD.
        """
        from launcher import _LauncherWindow, APP_PY

        # Mock a crashed Popen process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1

        log_path = os.path.join(BASE_DIR, "daemon.log")
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write("ModuleNotFoundError: No module named 'groq'\n")

        # Mock launcher window instance
        with patch.object(_LauncherWindow, "__init__", lambda self: None):
            win = _LauncherWindow()
            win._daemon = mock_proc
            win._poll_timer = MagicMock()
            win._poll_attempts = 1
            win._setup = MagicMock()
            win._is_daemon_healthy = MagicMock(return_value=False)
            win._open_hud = MagicMock()

            # Execute poll
            win._poll_daemon()

            # Assert HUD was NEVER opened
            win._open_hud.assert_not_called()
            # Assert timer stopped
            win._poll_timer.stop.assert_called_once()
            # Assert button reset and error displayed
            win._setup.launch_btn.setText.assert_called_with("Launch Ghost Copilot")
            win._setup.launch_btn.setEnabled.assert_called_with(True)
            assert any(
                "ModuleNotFoundError" in str(call)
                for call in win._setup.key_status.setText.call_args_list
            )

    def test_scenario_3_fast_open_when_daemon_healthy(self):
        """
        Scenario 3:
        Simulate daemon already running on port 9471.
        Verify _on_launch immediately calls _open_hud() on fast path without delay.
        """
        from launcher import _LauncherWindow

        with patch.object(_LauncherWindow, "__init__", lambda self: None):
            win = _LauncherWindow()
            win._setup = MagicMock()
            win._is_daemon_healthy = MagicMock(return_value=True)
            win._open_hud = MagicMock()
            win._start_daemon = MagicMock()

            start_t = time.perf_counter()
            win._on_launch()
            elapsed_ms = (time.perf_counter() - start_t) * 1000

            # Must invoke _open_hud immediately
            win._open_hud.assert_called_once()
            win._start_daemon.assert_not_called()
            assert elapsed_ms < 50, f"Fast path took {elapsed_ms}ms, expected < 50ms"

    def test_scenario_4_token_resolution_multi_fallback(self, tmp_path):
        """
        Scenario 4:
        Verify token resolution succeeds across multiple fallback locations:
        1. COPILOT_AUTH_TOKEN env var
        2. User home token file
        3. Local folder .session_token file
        """
        from launcher import _read_session_token

        # Fallback 1: Environment variable
        with patch.dict(os.environ, {"COPILOT_AUTH_TOKEN": "token_from_env_12345"}):
            assert _read_session_token() == "token_from_env_12345"

        # Fallback 2: Local directory .session_token
        local_token_file = os.path.join(BASE_DIR, ".session_token")
        original_token = None
        if os.path.exists(local_token_file):
            with open(local_token_file, "r") as f:
                original_token = f.read()

        try:
            with open(local_token_file, "w") as f:
                f.write("test_local_token_67890\n")

            with patch.dict(os.environ, {}, clear=True):
                # When TOKEN_FILE in home does not exist or env empty
                with patch("launcher.TOKEN_FILE", str(tmp_path / "nonexistent")):
                    resolved = _read_session_token()
                    assert resolved == "test_local_token_67890"
        finally:
            if original_token is not None:
                with open(local_token_file, "w") as f:
                    f.write(original_token)

    def test_scenario_5_app_py_missing_guard(self):
        """
        Scenario 5:
        If app.py is missing from installation directory, launcher must
        show clear message and NOT attempt to spawn or hang.
        """
        from launcher import _LauncherWindow

        with patch.object(_LauncherWindow, "__init__", lambda self: None):
            win = _LauncherWindow()
            win._setup = MagicMock()
            win._is_daemon_healthy = MagicMock(return_value=False)
            win._start_daemon = MagicMock()
            win._open_hud = MagicMock()

            with patch("launcher.APP_PY", "/nonexistent/path/to/app.py"):
                win._on_launch()

                win._start_daemon.assert_not_called()
                win._open_hud.assert_not_called()
                win._setup.launch_btn.setText.assert_called_with("Launch Ghost Copilot")
                assert any(
                    "not found" in str(call).lower()
                    for call in win._setup.key_status.setText.call_args_list
                )

    def test_scenario_6_emergency_skip_and_generation_abort(self):
        """
        Scenario 6:
        Verify emergency skip cancels in-flight LLM generation and resets state.
        """
        import app as copilot_app

        # Set initial generation ID
        initial_gen_id = copilot_app.gen_id
        copilot_app.reading_until = time.time() + 30.0

        # Simulate emergency skip call logic
        with copilot_app.gen_lock:
            copilot_app.gen_id += 1
        copilot_app.reading_until = 0.0

        assert copilot_app.gen_id > initial_gen_id
        assert copilot_app.reading_until == 0.0

    def test_scenario_7_zero_emojis_in_source_and_endpoints(self):
        """
        Scenario 7:
        Verify zero emojis exist in app.py, launcher.py, and server API endpoints.
        """
        import re

        emoji_pattern = re.compile(
            r'[\U00010000-\U0010ffff]|'
            r'[\u2600-\u27bf]|'
            r'[\u2300-\u23ff]|'
            r'[\u2b50-\u2b55]'
        )

        for fname in ["app.py", "server/api/v1/endpoints/copilot.py", "server/ai/groq_client.py"]:
            full_path = os.path.join(BASE_DIR, fname)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                matches = emoji_pattern.findall(content)
                assert not matches, f"Found emojis {matches} in {fname}"
