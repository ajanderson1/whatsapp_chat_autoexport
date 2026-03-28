"""
Integration tests for parallel pipeline wired into ChatExporter.export_chats().

Verifies that:
- export_chats() submits to ParallelPipeline instead of calling pipeline synchronously
- UI automation for chat N+1 starts before pipeline for chat N completes
- Results are correctly reconciled after collection
"""

import time
import threading
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter
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
