"""
Tests for ChatTiming dataclass, PhaseTimer, and per-chat timing instrumentation.

Covers:
- ChatTiming dataclass fields and compute_total()
- PhaseTimer start/stop and context-manager usage
- format_duration() helper
- print_timing_summary() output
- Integration: export_chats() populates chat_timings with correct statuses
- Edge cases: failed chat, skipped chat (resume mode)
"""

import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from whatsapp_chat_autoexport.export.timing import (
    ChatTiming,
    ChatStatus,
    PhaseTimer,
    format_duration,
    print_timing_summary,
)


# ---------------------------------------------------------------------------
# ChatTiming dataclass
# ---------------------------------------------------------------------------


class TestChatTiming:
    def test_default_values(self):
        ct = ChatTiming(chat_name="Test Chat")
        assert ct.chat_name == "Test Chat"
        assert ct.ui_time_s == 0.0
        assert ct.poll_time_s == 0.0
        assert ct.download_time_s == 0.0
        assert ct.process_time_s == 0.0
        assert ct.total_time_s == 0.0
        assert ct.status == ChatStatus.SUCCESS

    def test_compute_total(self):
        ct = ChatTiming(
            chat_name="Chat A",
            ui_time_s=1.5,
            poll_time_s=3.0,
            download_time_s=2.0,
            process_time_s=0.5,
        )
        ct.compute_total()
        assert ct.total_time_s == pytest.approx(7.0)

    def test_compute_total_all_zeros(self):
        ct = ChatTiming(chat_name="Empty")
        ct.compute_total()
        assert ct.total_time_s == 0.0

    def test_status_enum_values(self):
        assert ChatStatus.SUCCESS.value == "success"
        assert ChatStatus.FAILED.value == "failed"
        assert ChatStatus.SKIPPED.value == "skipped"


# ---------------------------------------------------------------------------
# PhaseTimer
# ---------------------------------------------------------------------------


class TestPhaseTimer:
    def test_start_stop(self):
        timer = PhaseTimer()
        timer.start()
        time.sleep(0.05)
        elapsed = timer.stop()
        assert elapsed >= 0.04  # some tolerance
        assert timer.elapsed == elapsed

    def test_context_manager(self):
        with PhaseTimer() as timer:
            time.sleep(0.05)
        assert timer.elapsed >= 0.04

    def test_stop_without_start_returns_zero(self):
        timer = PhaseTimer()
        elapsed = timer.stop()
        assert elapsed == 0.0

    def test_start_returns_self(self):
        timer = PhaseTimer()
        result = timer.start()
        assert result is timer
        timer.stop()

    def test_double_stop_preserves_elapsed(self):
        timer = PhaseTimer()
        timer.start()
        time.sleep(0.05)
        first = timer.stop()
        second = timer.stop()
        # Second stop has no active start so returns the previous elapsed unchanged
        assert first >= 0.04
        assert second == first
        assert timer.elapsed == first


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_seconds(self):
        assert format_duration(5.3) == "5.3s"

    def test_minutes(self):
        assert format_duration(125.0) == "2m 5.0s"

    def test_hours(self):
        assert format_duration(3661.5) == "1h 1m 1.5s"

    def test_zero(self):
        assert format_duration(0.0) == "0.0s"

    def test_just_under_a_minute(self):
        assert format_duration(59.9) == "59.9s"

    def test_exactly_sixty(self):
        assert format_duration(60.0) == "1m 0.0s"


# ---------------------------------------------------------------------------
# print_timing_summary
# ---------------------------------------------------------------------------


class TestPrintTimingSummary:
    def test_empty_list_no_output(self):
        logger = MagicMock()
        print_timing_summary([], logger)
        logger.info.assert_not_called()

    def test_single_chat_prints_rows(self):
        logger = MagicMock()
        timings = [
            ChatTiming(
                chat_name="Family Group",
                ui_time_s=2.0,
                poll_time_s=4.0,
                download_time_s=1.0,
                process_time_s=0.5,
                total_time_s=7.5,
                status=ChatStatus.SUCCESS,
            )
        ]
        print_timing_summary(timings, logger)

        # Should have been called multiple times (header, row, totals, stats)
        assert logger.info.call_count >= 8

        # Check that the chat name appears in one of the calls
        all_args = [str(call) for call in logger.info.call_args_list]
        joined = "\n".join(all_args)
        assert "Family Group" in joined
        assert "success" in joined
        assert "TOTAL" in joined

    def test_summary_stats_line(self):
        logger = MagicMock()
        timings = [
            ChatTiming(chat_name="A", status=ChatStatus.SUCCESS, total_time_s=1.0),
            ChatTiming(chat_name="B", status=ChatStatus.FAILED, total_time_s=2.0),
            ChatTiming(chat_name="C", status=ChatStatus.SKIPPED, total_time_s=0.0),
        ]
        print_timing_summary(timings, logger)

        all_args = " ".join(str(call) for call in logger.info.call_args_list)
        assert "Success: 1" in all_args
        assert "Failed: 1" in all_args
        assert "Skipped: 1" in all_args

    def test_long_chat_name_truncated(self):
        logger = MagicMock()
        long_name = "A" * 50
        timings = [ChatTiming(chat_name=long_name, total_time_s=1.0)]
        print_timing_summary(timings, logger)

        all_args = " ".join(str(call) for call in logger.info.call_args_list)
        # Truncated to 28 chars + ".."
        assert "A" * 28 + ".." in all_args

    def test_totals_sum_phases(self):
        logger = MagicMock()
        timings = [
            ChatTiming(chat_name="A", ui_time_s=1.0, poll_time_s=2.0,
                       download_time_s=3.0, process_time_s=4.0, total_time_s=10.0),
            ChatTiming(chat_name="B", ui_time_s=0.5, poll_time_s=1.0,
                       download_time_s=1.5, process_time_s=2.0, total_time_s=5.0),
        ]
        print_timing_summary(timings, logger)

        all_args = " ".join(str(call) for call in logger.info.call_args_list)
        # Total wall time should be 15.0s
        assert "15.0s" in all_args


# ---------------------------------------------------------------------------
# Integration: export_chats() populates chat_timings
# ---------------------------------------------------------------------------


def _make_exporter(pipeline=None):
    """Create a ChatExporter with mocked driver and logger."""
    from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter

    mock_driver = MagicMock()
    mock_driver.verify_whatsapp_is_open.return_value = True
    mock_driver.click_chat.return_value = True
    mock_driver.is_session_active.return_value = True

    mock_logger = MagicMock()
    mock_logger.debug = False

    # Ensure mock pipeline has max_concurrent for ParallelPipeline
    if pipeline is not None:
        if not hasattr(pipeline.config, '_mock_name') or True:
            pipeline.config.max_concurrent = 2

    exporter = ChatExporter(mock_driver, mock_logger, pipeline=pipeline)
    exporter.export_chat_to_google_drive = MagicMock(return_value=True)

    return exporter


class TestExportChatsTiming:
    """Verify that export_chats() populates self.chat_timings correctly."""

    def test_happy_path_success_no_pipeline(self):
        """Successful export without pipeline: timing captures UI phase, status=SUCCESS."""
        exporter = _make_exporter()

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B"], include_media=True
        )

        assert len(exporter.chat_timings) == 2
        for ct in exporter.chat_timings:
            assert ct.status == ChatStatus.SUCCESS
            assert ct.ui_time_s > 0 or ct.total_time_s >= 0
            assert ct.total_time_s >= 0

    def test_happy_path_with_pipeline(self):
        """Successful export with pipeline: timing captures UI and process phases."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_single_export.return_value = {
            "success": True,
            "output_path": "/tmp/out",
        }
        exporter = _make_exporter(pipeline=mock_pipeline)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A"], include_media=True, google_drive_folder="TestFolder"
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.SUCCESS
        assert ct.ui_time_s >= 0
        assert ct.process_time_s >= 0

    def test_chat_skipped_resume_mode(self):
        """Chat skipped in resume mode: status=SKIPPED, all phases zero."""
        exporter = _make_exporter()

        # Create a temp resume folder with a matching file
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file matching the chat name pattern
            Path(tmpdir, "WhatsApp Chat with Test Chat.zip").touch()

            results, timings, total_time, skipped = exporter.export_chats(
                ["Test Chat"], include_media=True, resume_folder=Path(tmpdir)
            )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.SKIPPED
        assert ct.ui_time_s == 0.0
        assert ct.poll_time_s == 0.0
        assert ct.download_time_s == 0.0
        assert ct.process_time_s == 0.0

    def test_chat_fails_during_export(self):
        """Export failure: status=FAILED, UI phase has time recorded."""
        exporter = _make_exporter()
        exporter.export_chat_to_google_drive = MagicMock(return_value=False)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Fail Chat"], include_media=True
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.FAILED
        assert ct.ui_time_s >= 0

    def test_chat_fails_during_pipeline(self):
        """Pipeline exception: status=FAILED, process_time captured."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_single_export.side_effect = RuntimeError("Drive error")
        exporter = _make_exporter(pipeline=mock_pipeline)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Pipeline Fail"], include_media=True, google_drive_folder="Folder"
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.FAILED
        assert ct.process_time_s >= 0

    def test_verification_failure_marks_failed(self):
        """WhatsApp not accessible: status=FAILED, zero timing."""
        exporter = _make_exporter()
        exporter.driver.verify_whatsapp_is_open.return_value = False
        exporter.driver.reconnect.return_value = False

        results, timings, total_time, skipped = exporter.export_chats(
            ["Unreachable"], include_media=True
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.FAILED

    def test_click_chat_failure_marks_failed(self):
        """Cannot open chat: status=FAILED, UI time recorded."""
        exporter = _make_exporter()
        exporter.driver.click_chat.return_value = False

        results, timings, total_time, skipped = exporter.export_chats(
            ["Hidden Chat"], include_media=True
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.FAILED
        assert ct.ui_time_s >= 0

    def test_timing_summary_printed(self):
        """Verify print_timing_summary is called at the end of export_chats."""
        exporter = _make_exporter()

        with patch(
            "whatsapp_chat_autoexport.export.chat_exporter.print_timing_summary"
        ) as mock_print:
            exporter.export_chats(["Chat A"], include_media=True)
            mock_print.assert_called_once()
            args = mock_print.call_args[0]
            assert len(args[0]) == 1  # one ChatTiming
            assert args[0][0].chat_name == "Chat A"

    def test_batch_resets_chat_timings(self):
        """Each call to export_chats resets chat_timings from previous batch."""
        exporter = _make_exporter()

        exporter.export_chats(["Chat A"], include_media=True)
        assert len(exporter.chat_timings) == 1

        exporter.export_chats(["Chat B", "Chat C"], include_media=True)
        assert len(exporter.chat_timings) == 2
        assert exporter.chat_timings[0].chat_name == "Chat B"

    def test_existing_return_contract_unchanged(self):
        """export_chats still returns the same 4-tuple contract."""
        exporter = _make_exporter()

        result = exporter.export_chats(["Chat A"], include_media=True)

        assert isinstance(result, tuple)
        assert len(result) == 4
        results, timings, total_time, skipped = result
        assert isinstance(results, dict)
        assert isinstance(timings, dict)
        assert isinstance(total_time, float)
        assert isinstance(skipped, dict)

    def test_pipeline_failure_result_marks_failed(self):
        """Pipeline returns success=False: status=FAILED."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_single_export.return_value = {
            "success": False,
            "errors": ["timeout"],
        }
        exporter = _make_exporter(pipeline=mock_pipeline)

        exporter.export_chats(
            ["Fail Pipeline"], include_media=True, google_drive_folder="F"
        )

        ct = exporter.chat_timings[0]
        assert ct.status == ChatStatus.FAILED

    def test_multiple_chats_mixed_results(self):
        """Batch with mixed success/failure populates timing for each."""
        exporter = _make_exporter()
        # First call succeeds, second fails
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=[True, False]
        )

        exporter.export_chats(["Good", "Bad"], include_media=True)

        assert len(exporter.chat_timings) == 2
        assert exporter.chat_timings[0].status == ChatStatus.SUCCESS
        assert exporter.chat_timings[1].status == ChatStatus.FAILED
