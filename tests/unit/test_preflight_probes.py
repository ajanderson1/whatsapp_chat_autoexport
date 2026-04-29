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

    def test_valid_key_with_org_header(self):
        """When OpenAI-Organization header is present, capture org id + last-4 of key."""
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": []},
                headers={"OpenAI-Organization": "org-abc123"},
            )

        result = check_whisper(
            "sk-test-key-1234",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.OK
        assert result.details["organization_id"] == "org-abc123"
        assert result.details["key_last4"] == "1234"
        assert result.details["quota_introspected"] is False
        # Identity surfaced in the user-visible summary
        assert "1234" in result.summary
        assert "org-abc123" in result.summary
        assert "quota" in result.summary.lower()

    def test_valid_key_without_org_header(self):
        """Legacy / personal keys may not return OpenAI-Organization — render gracefully."""
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})  # no header

        result = check_whisper(
            "sk-old-style-key-9999",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.OK
        assert result.details["organization_id"] is None
        assert result.details["key_last4"] == "9999"
        assert "9999" in result.summary
        assert "org not in response" in result.summary

    def test_full_key_never_leaks_into_summary(self):
        """Defensive: only the last 4 chars of the key may appear in summary."""
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        full_key = "sk-secret-AAAAAAAAAAAAAAAAAAAA-LAST"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": []},
                headers={"OpenAI-Organization": "org-x"},
            )

        result = check_whisper(
            full_key,
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        # The full key must not appear anywhere in summary or stringified details.
        assert full_key not in result.summary
        assert full_key not in str(result.details)
        # Last-4 is fine.
        assert "LAST" in result.summary


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures" / "preflight"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


class TestElevenLabsProbe:
    def test_no_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        result = check_elevenlabs(None)
        assert result.status == Status.SKIPPED
        assert result.provider == "elevenlabs"

    def test_full_quota_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_full.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/user/subscription"
            assert request.headers["xi-api-key"] == "el-test"
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.OK
        assert result.details["character_count"] == 1000
        assert result.details["character_limit"] == 100000
        assert result.details["characters_remaining"] == 99000
        assert result.details["tier"] == "creator"
        assert result.details["next_reset_unix"] == 1746057600

    def test_low_quota_warn(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_low.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.WARN
        assert result.details["characters_remaining"] == 5000

    def test_exhausted_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_exhausted.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.details["characters_remaining"] == 0

    def test_invalid_key_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Unauthorized"})

        result = check_elevenlabs(
            "bad",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.error  # non-empty

    def test_network_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timed out")

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL

    def test_malformed_response_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.error


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

class _FakeAbout:
    """Minimal stand-in for googleapiclient about() resource."""

    def __init__(self, response_or_exc):
        self._response_or_exc = response_or_exc

    def get(self, fields):
        return self  # `.execute()` is the next call

    def execute(self):
        if isinstance(self._response_or_exc, Exception):
            raise self._response_or_exc
        return self._response_or_exc


class _FakeService:
    def __init__(self, response_or_exc):
        self._inner = _FakeAbout(response_or_exc)

    def about(self):
        return self._inner


class _FakeAuth:
    """Stand-in for GoogleDriveAuth used by check_drive."""

    def __init__(self, has_creds: bool, response_or_exc=None):
        self._has = has_creds
        self._response_or_exc = response_or_exc

    def has_credentials(self) -> bool:
        return self._has

    def get_service(self):
        return _FakeService(self._response_or_exc)


class TestDriveProbe:
    def test_no_auth_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        result = check_drive(None)
        assert result.status == Status.HARD_FAIL
        assert result.provider == "drive"

    def test_no_creds_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(has_creds=False)
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL

    def test_token_expired_hard_fail(self):
        from google.auth.exceptions import RefreshError

        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=RefreshError("Token expired"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL
        assert "expired" in result.error.lower() or "revoked" in result.error.lower()

    def test_full_storage_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_full.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.OK
        assert result.details["storage_limit_bytes"] == 16106127360
        assert result.details["storage_used_bytes"] == 3221225472

    def test_low_storage_warn(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_low.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.WARN

    def test_exhausted_storage_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_exhausted.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL

    def test_pooled_no_limit_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_pooled.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.OK
        assert result.details["storage_limit_bytes"] is None
        assert "limit not reported" in result.summary.lower()

    def test_http_error_hard_fail(self):
        from googleapiclient.errors import HttpError

        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        # HttpError requires (resp, content); use a minimal stand-in
        class _FakeResp:
            status = 503
            reason = "Service Unavailable"

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=HttpError(_FakeResp(), b"err"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL
