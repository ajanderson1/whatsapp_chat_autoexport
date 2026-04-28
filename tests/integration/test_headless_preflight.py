"""End-to-end-ish tests for preflight integration in headless modes."""

import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)


def _build_args(**overrides) -> Namespace:
    """Argparse Namespace shaped like the headless path expects."""
    base = dict(
        output="/tmp/preflight-test",
        headless=True,
        pipeline_only=False,
        source=None,
        pipeline_output=None,
        auto_select=True,
        no_transcribe=False,
        transcription_provider="whisper",
        skip_preflight=False,
        debug=False,
        wireless_adb=None,
        skip_appium=True,  # we don't actually want Appium in this test
        resume=None,
        without_media=False,
        no_output_media=False,
        delete_from_drive=False,
        keep_drive_duplicates=False,
        force_transcribe=False,
        skip_opus_conversion=False,
        google_drive_folder=None,
        poll_interval=8,
        poll_timeout=300,
        transcription_language=None,
        limit=None,
    )
    base.update(overrides)
    return Namespace(**base)


@pytest.fixture
def mock_passing_api_key():
    """Skip the API-key validation pre-step."""
    with patch(
        "whatsapp_chat_autoexport.headless._validate_api_key",
        return_value=True,
    ) as m:
        yield m


def _hard_fail_report() -> PreflightReport:
    from datetime import datetime

    return PreflightReport(
        results=[
            CheckResult(
                provider="elevenlabs",
                display_name="ElevenLabs",
                status=Status.HARD_FAIL,
                summary="Quota exhausted",
                error="0 chars left",
            ),
        ],
        started_at=datetime.now(),
        duration_ms=120,
    )


def _ok_report() -> PreflightReport:
    from datetime import datetime

    return PreflightReport(
        results=[
            CheckResult(
                provider="whisper",
                display_name="OpenAI (Whisper)",
                status=Status.OK,
                summary="Key valid",
            )
        ],
        started_at=datetime.now(),
        duration_ms=120,
    )


class TestHeadlessPreflightGate:
    def test_hard_fail_returns_exit_code_2(
        self, mock_passing_api_key, capsys
    ):
        from whatsapp_chat_autoexport.headless import run_headless

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=_hard_fail_report(),
        ):
            exit_code = run_headless(_build_args())

        assert exit_code == 2
        err = capsys.readouterr().err
        assert "[preflight]" in err
        assert "FAIL" in err

    def test_skip_preflight_bypasses_gate(self, mock_passing_api_key):
        from whatsapp_chat_autoexport.headless import run_headless

        # If the gate ran, run_preflight would be called; assert it isn't.
        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight"
        ) as preflight_mock, patch(
            "whatsapp_chat_autoexport.export.appium_manager.AppiumManager"
        ), patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver"
        ) as driver_cls:
            # Force device check to fail so we exit early after the gate
            driver_cls.return_value.check_device_connection.return_value = False

            run_headless(_build_args(skip_preflight=True))

        preflight_mock.assert_not_called()

    def test_warn_does_not_block(self, mock_passing_api_key, capsys):
        """A WARN-only report must not abort; execution continues until
        the next early-exit (no device)."""
        from datetime import datetime

        warn_report = PreflightReport(
            results=[
                CheckResult(
                    provider="elevenlabs",
                    display_name="ElevenLabs",
                    status=Status.WARN,
                    summary="Low quota",
                )
            ],
            started_at=datetime.now(),
            duration_ms=30,
        )

        from whatsapp_chat_autoexport.headless import run_headless

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=warn_report,
        ), patch(
            "whatsapp_chat_autoexport.export.appium_manager.AppiumManager"
        ), patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver"
        ) as driver_cls:
            driver_cls.return_value.check_device_connection.return_value = False

            exit_code = run_headless(_build_args())

        # Device check fails → exit code 2, but the preflight gate didn't
        # cause it. Stderr should still show the warn line.
        err = capsys.readouterr().err
        assert "[preflight]" in err
        assert "WARN" in err
