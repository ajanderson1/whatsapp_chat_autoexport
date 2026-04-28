"""Tests for preflight probes (whisper, elevenlabs, drive)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from whatsapp_chat_autoexport.preflight.report import Status


# ---------------------------------------------------------------------------
# Helpers — build a mocked httpx.Client transport that the probes can use
# ---------------------------------------------------------------------------

def _mock_transport(response_factory):
    """Return an httpx.MockTransport that serves the given factory."""
    return httpx.MockTransport(response_factory)


# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------

class TestWhisperProbe:
    def test_no_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        result = check_whisper(None)
        assert result.status == Status.SKIPPED
        assert result.provider == "whisper"
        assert result.display_name == "OpenAI (Whisper)"

    def test_empty_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        result = check_whisper("")
        assert result.status == Status.SKIPPED

    def test_valid_key_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/models"
            assert request.headers["authorization"] == "Bearer sk-test"
            return httpx.Response(200, json={"data": []})

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.OK
        assert "Key valid" in result.summary
        assert result.details["key_valid"] is True
        assert result.details["models_endpoint_ok"] is True

    def test_invalid_key_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid"}})

        result = check_whisper("sk-bad", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL
        assert "Invalid OpenAI API key" in result.error

    def test_server_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL

    def test_network_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL
        assert result.error  # non-empty
