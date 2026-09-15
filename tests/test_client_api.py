"""
Tests for Cross-Platform CopilotApiClient.
Tests request formatting, auth headers, error handling, and payload schemas.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO
from urllib.error import HTTPError, URLError

from client.core.config import ClientConfig
from client.core.errors import BackendConnectionError
from client.api.client import CopilotApiClient


def test_client_headers_generation():
    config = ClientConfig(auth_token="test-jwt-token-xyz")
    client = CopilotApiClient(config)
    headers = client.headers

    assert headers["Content-Type"] == "application/json"
    assert "GhostCopilot-Client" in headers["User-Agent"]
    assert headers["Authorization"] == "Bearer test-jwt-token-xyz"


def test_client_check_health_success():
    client = CopilotApiClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"status": "ok", "app": "ghost_copilot"}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.check_health()
        assert res["status"] == "ok"
        assert res["app"] == "ghost_copilot"


def test_client_check_health_connection_error():
    client = CopilotApiClient()

    with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
        with pytest.raises(BackendConnectionError) as exc_info:
            client.check_health()
        assert "Backend is unreachable" in str(exc_info.value)


def test_client_solve_request_formatting():
    client = CopilotApiClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"status": "processing", "session_id": "test-session"}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = client.solve(question="Explain Dijkstra algorithm", session_id="test-session")
        assert res["status"] == "processing"

        # Verify outgoing request payload
        req_arg = mock_urlopen.call_args[0][0]
        payload = json.loads(req_arg.data.decode())
        assert payload["question"] == "Explain Dijkstra algorithm"
        assert payload["session_id"] == "test-session"


def test_client_skip_question():
    client = CopilotApiClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"status": "ok", "action": "skipped"}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.skip_question(session_id="test-session")
        assert res["status"] == "ok"
        assert res["action"] == "skipped"
