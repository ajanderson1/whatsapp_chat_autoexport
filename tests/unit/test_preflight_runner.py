"""Tests for the preflight runner."""

from datetime import datetime
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.preflight.report import CheckResult, Status
from whatsapp_chat_autoexport.preflight.runner import (
    DRIVE_HARD_FAIL_BYTES,
    DRIVE_WARN_BYTES,
    ELEVENLABS_HARD_THRESHOLD,
    ELEVENLABS_WARN_THRESHOLD,
    run_preflight,
)


def _ok(provider, name):
    return CheckResult(provider=provider, display_name=name, status=Status.OK, summary="ok")


def _fail(provider, name):
    return CheckResult(
        provider=provider, display_name=name, status=Status.HARD_FAIL, summary="bad"
    )


def _warn(provider, name):
    return CheckResult(
        provider=provider, display_name=name, status=Status.WARN, summary="meh"
    )


class TestRunner:
    def test_constants_exist(self):
        assert ELEVENLABS_WARN_THRESHOLD == 50_000
        assert ELEVENLABS_HARD_THRESHOLD == 0
        assert DRIVE_WARN_BYTES == 5 * 1024**3
        assert DRIVE_HARD_FAIL_BYTES == 500 * 1024**2

    def test_aggregates_three_results(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_ok("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_warn("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive",
            return_value=_ok("drive", "Google Drive"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth",
            return_value=object(),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.side_effect = lambda p: f"key-{p}"

            report = run_preflight()

        assert len(report.results) == 3
        providers = [r.provider for r in report.results]
        assert providers == ["whisper", "elevenlabs", "drive"]
        assert report.has_warning is True
        assert report.has_hard_fail is False
        assert isinstance(report.started_at, datetime)
        assert report.duration_ms >= 0

    def test_skip_drive_omits_probe(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_ok("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_ok("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive"
        ) as drive_mock, patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth"
        ) as build_mock, patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.return_value = "k"

            report = run_preflight(skip_drive=True)

        drive_mock.assert_not_called()
        build_mock.assert_not_called()
        providers = [r.provider for r in report.results]
        assert "drive" not in providers
        assert len(report.results) == 2

    def test_hard_fail_propagates(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_fail("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_ok("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive",
            return_value=_ok("drive", "Google Drive"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth",
            return_value=object(),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.return_value = "k"

            report = run_preflight()

        assert report.has_hard_fail is True
