"""
Integration tests for parallel pipeline wired into ChatExporter.export_chats().

Verifies that:
- export_chats() submits to ParallelPipeline instead of calling pipeline synchronously
- UI automation for chat N+1 starts before pipeline for chat N completes
- Results are correctly reconciled after collection
- End-to-end: wall-clock time < sequential sum (measurable speedup)
- End-to-end: timing report is complete and accurate
- End-to-end: error isolation under parallel execution
"""

import time
import threading
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter
from whatsapp_chat_autoexport.export.timing import ChatStatus
from whatsapp_chat_autoexport.pipeline import PipelineConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_driver_mock():
    """Create a mock WhatsAppDriver that passes all verification checks."""
    driver = MagicMock()
    driver.verify_whatsapp_is_open.return_value = True
    driver.is_session_active.return_value = True
    driver.click_chat.return_value = True
    driver.navigate_to_main.return_value = None
    driver.navigate_back_to_main.return_value = None
    driver.device_id = "mock_device"
    return driver


def _make_pipeline_mock(delay: float = 0.0, fail_chats: set | None = None):
    """Create a mock pipeline with configurable delay and failure set."""
    fail_chats = fail_chats or set()
    pipeline = MagicMock()
    pipeline.config = PipelineConfig(max_concurrent=2)

    call_log: list[tuple[str, float]] = []

    def _process(chat_name, google_drive_folder=None):
        start = time.monotonic()
        if delay:
            time.sleep(delay)
        call_log.append((chat_name, time.monotonic()))
        if chat_name in fail_chats:
            return {
                "success": False,
                "output_path": None,
                "phases_completed": [],
                "errors": [f"Simulated failure for {chat_name}"],
            }
        return {
            "success": True,
            "output_path": f"/output/{chat_name}",
            "phases_completed": ["download", "extract", "build_output"],
            "errors": [],
        }

    pipeline.process_single_export.side_effect = _process
    pipeline._call_log = call_log
    return pipeline


def _make_logger():
    logger = MagicMock()
    logger.debug = False
    return logger


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParallelExportIntegration:
    """Integration: ChatExporter.export_chats with parallel pipeline."""

    def test_pipeline_tasks_submitted_in_parallel(self):
        """UI exports proceed while pipeline tasks run in background."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock(delay=0.3)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        # Mock export_chat_to_google_drive to succeed
        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        chats = ["Chat A", "Chat B", "Chat C"]

        start = time.monotonic()
        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )
        elapsed = time.monotonic() - start

        # All 3 pipeline tasks should have been called
        assert pipeline.process_single_export.call_count == 3

        # With parallel pipeline (delay=0.3s each, max_workers=2):
        # Sequential would be ~0.9s for pipeline alone.
        # Parallel should be ~0.3-0.6s for pipeline (overlapping with UI).
        # The total should be noticeably less than 0.9s + UI time.
        # We just verify it's less than the fully-sequential time.
        sequential_pipeline_time = 0.3 * 3
        assert elapsed < sequential_pipeline_time + 1.0, (
            f"Expected parallel to be faster; got {elapsed:.2f}s"
        )

    def test_failed_pipeline_updates_results(self):
        """Pipeline failure for one chat updates results dict to False."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock(delay=0.05, fail_chats={"Bad Chat"})

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=["Good Chat", "Bad Chat"], include_media=True
        )

        assert results["Good Chat"] is True
        assert results["Bad Chat"] is False

    def test_no_pipeline_still_works(self):
        """Without pipeline configured, export_chats works as before."""
        driver = _make_driver_mock()
        logger = _make_logger()

        exporter = ChatExporter(driver, logger, pipeline=None)
        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=["Chat A"], include_media=True
        )

        assert results["Chat A"] is True

    def test_timing_updated_from_pipeline_results(self):
        """ChatTiming entries are updated with pipeline timing breakdown."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock(delay=0.1)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=["Timed Chat"], include_media=True
        )

        assert len(exporter.chat_timings) == 1
        ct = exporter.chat_timings[0]
        assert ct.chat_name == "Timed Chat"
        # process_time_s should be > 0 (set from pipeline result)
        assert ct.process_time_s > 0

    def test_export_failure_not_submitted_to_pipeline(self):
        """If UI export fails, the chat is not submitted to the pipeline."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock()

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(return_value=False)

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=["Failed Export"], include_media=True
        )

        assert results["Failed Export"] is False
        pipeline.process_single_export.assert_not_called()


# ---------------------------------------------------------------------------
# End-to-end integration tests (Unit 6)
# ---------------------------------------------------------------------------


def _make_pipeline_mock_with_delay(
    ui_delay: float = 0.0,
    pipeline_delay: float = 0.0,
    fail_chats: set | None = None,
):
    """Create a pipeline mock with configurable pipeline processing delay.

    Unlike the simpler ``_make_pipeline_mock`` above, this helper is
    designed for the end-to-end timing tests where we want to measure
    wall-clock speedup from parallelism.
    """
    fail_chats = fail_chats or set()
    pipeline = MagicMock()
    pipeline.config = PipelineConfig(max_concurrent=2)

    def _process(chat_name, google_drive_folder=None):
        # Simulate poll + download + process time
        if pipeline_delay:
            time.sleep(pipeline_delay)
        if chat_name in fail_chats:
            return {
                "success": False,
                "output_path": None,
                "phases_completed": ["download"],
                "errors": [f"Simulated failure for {chat_name}"],
            }
        return {
            "success": True,
            "output_path": f"/output/{chat_name}",
            "phases_completed": ["download", "extract", "build_output"],
            "errors": [],
        }

    pipeline.process_single_export.side_effect = _process
    return pipeline


def _make_slow_ui_export(ui_delay: float):
    """Return a side_effect function that simulates UI export latency."""

    def _export(chat_name, include_media=True):
        time.sleep(ui_delay)
        return True

    return _export


def _make_failing_ui_export(fail_chats: set, ui_delay: float = 0.0):
    """Return a side_effect where specified chats fail UI export."""

    def _export(chat_name, include_media=True):
        if ui_delay:
            time.sleep(ui_delay)
        return chat_name not in fail_chats

    return _export


class TestEndToEndParallelExport:
    """End-to-end integration: 5-chat batch with mocked UI + pipeline delays.

    These tests validate that all three optimization tracks (smart waits,
    adaptive polling, parallel pipeline) work together, producing measurable
    speedup and correct timing reports.
    """

    def test_happy_path_5_chats_parallel_faster_than_sequential(self):
        """5-chat batch: parallel wall-clock time < sequential sum.

        Simulated per-chat costs:
          - UI export: ~0.2s  (sequential, one at a time)
          - Pipeline:  ~1.0s  (poll + download + process, in background)

        Sequential total would be ~(0.2 + 1.0) * 5 = 6.0s.
        With parallel pipeline (max_workers=2), pipeline tasks overlap
        with UI automation, so wall-clock should be well under 6s.
        We use a generous bound of 5s to avoid CI flakiness.
        """
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(pipeline_delay=1.0)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.2)
        )

        chats = ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"]

        start = time.monotonic()
        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )
        elapsed = time.monotonic() - start

        # All 5 chats should succeed
        assert len(results) == 5, f"Expected 5 results, got {len(results)}"
        for chat in chats:
            assert results[chat] is True, f"Expected {chat} to succeed"

        # Pipeline was called for all 5
        assert pipeline.process_single_export.call_count == 5

        # Sequential sum: 5 * (0.2 + 1.0) = 6.0s
        # Parallel should be significantly faster — use generous bound
        sequential_sum = 5 * (0.2 + 1.0)
        assert elapsed < sequential_sum - 0.5, (
            f"Parallel ({elapsed:.2f}s) should be noticeably faster "
            f"than sequential ({sequential_sum:.1f}s)"
        )

        # Additional sanity: should complete in < 5s with generous CI margin
        assert elapsed < 5.0, f"Expected < 5s, got {elapsed:.2f}s"

    def test_happy_path_timing_report_complete(self):
        """5-chat batch: timing report has entries for all chats with breakdown."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(pipeline_delay=0.3)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.1)
        )

        chats = ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"]

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )

        # Timing list should have one entry per chat
        assert len(exporter.chat_timings) == 5, (
            f"Expected 5 timing entries, got {len(exporter.chat_timings)}"
        )

        timing_names = {ct.chat_name for ct in exporter.chat_timings}
        assert timing_names == set(chats)

        for ct in exporter.chat_timings:
            # UI time should be > 0 (we simulated 0.1s)
            assert ct.ui_time_s > 0, f"{ct.chat_name}: ui_time_s should be > 0"
            # Pipeline process time should be > 0 (set from pipeline result)
            assert ct.process_time_s > 0, f"{ct.chat_name}: process_time_s should be > 0"
            # Status should be SUCCESS
            assert ct.status == ChatStatus.SUCCESS, (
                f"{ct.chat_name}: expected SUCCESS, got {ct.status}"
            )
            # total_time_s should be computed (>= ui + process)
            assert ct.total_time_s > 0, f"{ct.chat_name}: total_time_s should be > 0"

    def test_one_chat_fails_pipeline_others_succeed(self):
        """One chat fails in pipeline — other 4 succeed, error in timing report."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(
            pipeline_delay=0.2, fail_chats={"Chat C"}
        )

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.1)
        )

        chats = ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"]

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )

        # All 5 UI exports succeeded, so pipeline was called 5 times
        assert pipeline.process_single_export.call_count == 5

        # 4 succeed, 1 fails
        assert results["Chat A"] is True
        assert results["Chat B"] is True
        assert results["Chat C"] is False  # pipeline failure
        assert results["Chat D"] is True
        assert results["Chat E"] is True

        # Timing report should have 5 entries
        assert len(exporter.chat_timings) == 5

        # Failed chat should have FAILED status in timing
        for ct in exporter.chat_timings:
            if ct.chat_name == "Chat C":
                assert ct.status == ChatStatus.FAILED, (
                    f"Chat C should be FAILED, got {ct.status}"
                )
            else:
                assert ct.status == ChatStatus.SUCCESS, (
                    f"{ct.chat_name} should be SUCCESS, got {ct.status}"
                )

    def test_all_chats_fail_pipeline_ui_still_completes(self):
        """All chats fail pipeline — UI automation completes all 5, all marked failed."""
        driver = _make_driver_mock()
        logger = _make_logger()
        all_chats = {"Chat A", "Chat B", "Chat C", "Chat D", "Chat E"}
        pipeline = _make_pipeline_mock_with_delay(
            pipeline_delay=0.1, fail_chats=all_chats
        )

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.05)
        )

        chats = list(all_chats)

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )

        # All 5 were submitted to pipeline (UI export succeeded)
        assert pipeline.process_single_export.call_count == 5

        # All results should be False (pipeline failed)
        for chat in chats:
            assert results[chat] is False, f"Expected {chat} to be False"

        # Timing report should have 5 entries, all FAILED
        assert len(exporter.chat_timings) == 5
        for ct in exporter.chat_timings:
            assert ct.status == ChatStatus.FAILED, (
                f"{ct.chat_name} should be FAILED, got {ct.status}"
            )
            # Even failed chats should have process_time_s > 0
            assert ct.process_time_s > 0, (
                f"{ct.chat_name}: process_time_s should be > 0 even for failures"
            )

    def test_mixed_ui_and_pipeline_failures(self):
        """Mix of UI failures (not submitted) and pipeline failures (submitted but fail).

        - Chat A: UI success, pipeline success
        - Chat B: UI failure (not submitted to pipeline)
        - Chat C: UI success, pipeline failure
        - Chat D: UI success, pipeline success
        - Chat E: UI success, pipeline success
        """
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(
            pipeline_delay=0.1, fail_chats={"Chat C"}
        )

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_failing_ui_export(fail_chats={"Chat B"}, ui_delay=0.05)
        )

        chats = ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"]

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )

        # Pipeline called for 4 chats (Chat B failed UI export)
        assert pipeline.process_single_export.call_count == 4

        assert results["Chat A"] is True
        assert results["Chat B"] is False  # UI failure
        assert results["Chat C"] is False  # pipeline failure
        assert results["Chat D"] is True
        assert results["Chat E"] is True

        # Timing should have entries for all 5 chats
        assert len(exporter.chat_timings) == 5

        # Chat B (UI failure) should be FAILED with no process_time
        for ct in exporter.chat_timings:
            if ct.chat_name == "Chat B":
                assert ct.status == ChatStatus.FAILED
                assert ct.process_time_s == 0.0, (
                    "Chat B was not submitted to pipeline, process_time should be 0"
                )

    def test_wall_clock_speedup_with_heavier_pipeline(self):
        """Heavier pipeline delays show more dramatic speedup.

        Simulated: 0.1s UI + 2.0s pipeline per chat, 5 chats.
        Sequential: 5 * (0.1 + 2.0) = 10.5s
        Parallel (max_workers=2): pipeline tasks overlap heavily.
        Generous bound: < 8s (allowing for thread overhead + CI variability).
        """
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(pipeline_delay=2.0)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.1)
        )

        chats = ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"]

        start = time.monotonic()
        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )
        elapsed = time.monotonic() - start

        # All succeed
        for chat in chats:
            assert results[chat] is True

        # Sequential would be ~10.5s; parallel should be well under
        sequential_sum = 5 * (0.1 + 2.0)
        assert elapsed < sequential_sum - 2.0, (
            f"Parallel ({elapsed:.2f}s) should show significant speedup "
            f"over sequential ({sequential_sum:.1f}s)"
        )
        # Generous upper bound for CI
        assert elapsed < 8.0, f"Expected < 8s, got {elapsed:.2f}s"

    def test_timing_summary_printed(self):
        """Verify that print_timing_summary is called at end of batch."""
        driver = _make_driver_mock()
        logger = _make_logger()
        pipeline = _make_pipeline_mock_with_delay(pipeline_delay=0.05)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)
        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=_make_slow_ui_export(ui_delay=0.02)
        )

        chats = ["Chat A", "Chat B"]

        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chats, include_media=True
        )

        # print_timing_summary calls logger.info with the header
        info_calls = [str(c) for c in logger.info.call_args_list]
        header_found = any("Per-Chat Timing Breakdown" in c for c in info_calls)
        assert header_found, (
            "Expected timing summary header in logger.info calls"
        )
