"""
Tests for Hardcoded Secrets and Sensitive Clipboard Filter.
"""

import os
import glob
from desktop.clipboard.watcher import DesktopClipboard


def test_no_hardcoded_groq_keys_in_source():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_files = glob.glob(f"{base_dir}/**/*.py", recursive=True)
    
    for filepath in py_files:
        if ".venv" in filepath or "__pycache__" in filepath or "/tests/" in filepath:
            continue
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            # Must not contain actual hardcoded active gsk_ key (ignoring comments/tests)
            if "gsk_" in content:
                for line in content.splitlines():
                    if "gsk_" in line and not line.strip().startswith("#") and "your_groq_api_key" not in line and "gsk_[a-zA-Z0-9]" not in line and "gsk_12345678" not in line:
                        assert False, f"Potential hardcoded Groq API key found in {filepath}: {line.strip()}"


def test_sensitive_clipboard_filter_catches_credentials():
    test_secrets = [
        "".join(["AK", "IA", "IOSFODNN7EXAMPLE"]),
        "".join(["gh", "p_", "123456789012345678901234567890123456"]),
        "password: my_super_secret_password_123",
        "postgres://user:secretpass@prod-db.internal:5432/app",
        "-----BEGIN RSA PRIVATE KEY-----"
    ]
    for secret in test_secrets:
        assert DesktopClipboard.is_sensitive(secret) is True, f"Failed to filter secret: {secret}"


def test_safe_interview_text_is_allowed():
    safe_texts = [
        "What is the difference between a process and a thread in operating systems?",
        "Can you explain the CAP theorem and its trade-offs in distributed systems?",
        "Tell me about a time you led a cross-functional team through a challenging project."
    ]
    for text in safe_texts:
        assert DesktopClipboard.is_sensitive(text) is False


def test_desktop_clipboard_windows_extraction(monkeypatch):
    """Verifies Windows clipboard extraction via powershell fallback or Win32 ctypes."""
    import sys
    monkeypatch.setattr(sys, "platform", "win32")

    # Mock subprocess.check_output to simulate PowerShell Get-Clipboard
    from unittest.mock import patch
    with patch("subprocess.check_output", return_value="System design question on Windows"):
        text = DesktopClipboard.read_clipboard()
        assert text == "System design question on Windows"


def test_desktop_clipboard_post_to_daemon_uses_bearer_header(monkeypatch):
    """Confirms clipboard transmission strictly uses Authorization: Bearer and never a URL token."""
    from unittest.mock import patch, MagicMock
    import urllib.request

    captured_requests = []

    def mock_urlopen(req, *args, **kwargs):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    test_token = "win-sec-token-987654"
    with patch.object(urllib.request, "urlopen", side_effect=mock_urlopen):
        success = DesktopClipboard.post_to_daemon(
            text="Explain distributed consensus algorithms.",
            backend_url="http://127.0.0.1:9471",
            auth_token=test_token
        )
        assert success is True
        assert len(captured_requests) == 1
        req = captured_requests[0]

        # Verify URL has NO query params
        assert "?token=" not in req.full_url
        assert "&token=" not in req.full_url
        assert req.full_url == "http://127.0.0.1:9471/solve"

        # Verify Bearer header
        assert req.headers.get("Authorization") == f"Bearer {test_token}"


def test_desktop_clipboard_blocks_sensitive_data_from_daemon():
    """Sensitive credential in clipboard must never be transmitted to daemon."""
    from unittest.mock import patch
    with patch("urllib.request.urlopen") as mock_url:
        result = DesktopClipboard.post_to_daemon(
            text="password = SuperSecretMasterKey123!",
            backend_url="http://127.0.0.1:9471",
            auth_token="token"
        )
        assert result is False
        assert not mock_url.called


def test_desktop_audio_capture_windows_command_generation(monkeypatch):
    """Verifies DesktopAudioCapture constructs DirectShow mic and WASAPI loopback commands on Windows."""
    import sys
    monkeypatch.setattr(sys, "platform", "win32")
    from desktop.audio.capture import DesktopAudioCapture

    cap = DesktopAudioCapture(mic_device="Microphone (Realtek Audio)", speaker_device="default")

    # Microphone capture command
    mic_cmd = cap.get_capture_command("Microphone (Realtek Audio)", 3.0, "out.wav", is_speaker=False)
    assert "-f" in mic_cmd
    dshow_idx = mic_cmd.index("-f") + 1
    assert mic_cmd[dshow_idx] == "dshow"
    assert "audio=Microphone (Realtek Audio)" in mic_cmd

    # Speaker / Loopback capture command
    spk_cmd = cap.get_capture_command("default", 5.0, "out_spk.wav", is_speaker=True)
    assert "-f" in spk_cmd
    wasapi_idx = spk_cmd.index("-f") + 1
    assert spk_cmd[wasapi_idx] == "wasapi"
    assert "default" in spk_cmd
