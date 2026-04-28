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


from datetime import datetime as _dt

from whatsapp_chat_autoexport.preflight.report import CheckResult, PreflightReport, Status
from whatsapp_chat_autoexport.preflight.runner import format_report_for_stderr


def _report(*statuses_and_summaries):
    results = []
    for provider, name, status, summary in statuses_and_summaries:
        results.append(
            CheckResult(
                provider=provider,
                display_name=name,
                status=status,
                summary=summary,
            )
        )
    return PreflightReport(results=results, started_at=_dt(2026, 1, 1), duration_ms=370)


class TestFormatReport:
    def test_all_ok(self):
        report = _report(
            ("whisper", "OpenAI (Whisper)", Status.OK, "Key valid"),
            ("elevenlabs", "ElevenLabs", Status.OK, "99,000/100,000 chars left (creator)"),
            ("drive", "Google Drive", Status.OK, "12.4 GB free of 15.0 GB"),
        )
        lines = format_report_for_stderr(report).splitlines()

        # One row per provider plus one summary line
        assert len(lines) == 4
        assert "[preflight] OpenAI (Whisper)" in lines[0]
        assert " OK " in lines[0]
        assert "Key valid" in lines[0]
        assert "0 warnings, 0 hard failures" in lines[3]
        assert "proceeding" in lines[3]
        assert "370 ms" in lines[3]

    def test_warn_displays_warn_token(self):
        report = _report(
            ("elevenlabs", "ElevenLabs", Status.WARN, "8,420 chars left"),
        )
        out = format_report_for_stderr(report)
        assert " WARN " in out
        assert "1 warning" in out

    def test_hard_fail_displays_fail_and_aborts(self):
        report = _report(
            ("elevenlabs", "ElevenLabs", Status.HARD_FAIL, "Quota exhausted"),
        )
        out = format_report_for_stderr(report)
        assert " FAIL " in out
        assert "Aborting" in out
        assert "--skip-preflight" in out

    def test_skipped_displays_skip(self):
        report = _report(
            ("whisper", "OpenAI (Whisper)", Status.SKIPPED, "No key configured"),
        )
        out = format_report_for_stderr(report)
        assert " SKIP " in out
