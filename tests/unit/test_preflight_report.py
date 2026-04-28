"""Tests for preflight data model: Status, CheckResult, PreflightReport."""

from datetime import datetime

import pytest

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)


class TestStatus:
    def test_status_string_values(self):
        assert Status.OK.value == "ok"
        assert Status.WARN.value == "warn"
        assert Status.HARD_FAIL.value == "hard_fail"
        assert Status.SKIPPED.value == "skipped"

    def test_status_is_str_enum(self):
        # Must be comparable to plain strings (str subclass)
        assert Status.OK == "ok"


class TestCheckResult:
    def test_minimal_construction(self):
        r = CheckResult(
            provider="whisper",
            display_name="OpenAI (Whisper)",
            status=Status.OK,
            summary="Key valid",
        )
        assert r.provider == "whisper"
        assert r.display_name == "OpenAI (Whisper)"
        assert r.status == Status.OK
        assert r.summary == "Key valid"
        assert r.details == {}
        assert r.error is None

    def test_with_details_and_error(self):
        r = CheckResult(
            provider="elevenlabs",
            display_name="ElevenLabs",
            status=Status.HARD_FAIL,
            summary="Invalid key",
            details={"tier": "creator"},
            error="401 Unauthorized",
        )
        assert r.details == {"tier": "creator"}
        assert r.error == "401 Unauthorized"


class TestPreflightReport:
    def _make(self, statuses: list[Status]) -> PreflightReport:
        results = [
            CheckResult(
                provider=f"p{i}",
                display_name=f"P{i}",
                status=s,
                summary="x",
            )
            for i, s in enumerate(statuses)
        ]
        return PreflightReport(
            results=results,
            started_at=datetime(2026, 1, 1),
            duration_ms=123,
        )

    def test_has_hard_fail_true(self):
        report = self._make([Status.OK, Status.HARD_FAIL, Status.OK])
        assert report.has_hard_fail is True

    def test_has_hard_fail_false(self):
        report = self._make([Status.OK, Status.WARN, Status.SKIPPED])
        assert report.has_hard_fail is False

    def test_has_warning_true(self):
        report = self._make([Status.OK, Status.WARN])
        assert report.has_warning is True

    def test_has_warning_false_when_only_ok(self):
        report = self._make([Status.OK, Status.OK])
        assert report.has_warning is False

    def test_empty_results(self):
        report = PreflightReport(results=[], started_at=datetime.now(), duration_ms=0)
        assert report.has_hard_fail is False
        assert report.has_warning is False
