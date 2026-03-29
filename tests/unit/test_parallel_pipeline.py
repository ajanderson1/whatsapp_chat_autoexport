"""
Unit tests for ParallelPipeline.

Covers:
- Happy path: multiple chats submitted, all succeed
- Happy path: concurrent execution is faster than sequential
- Happy path: max_workers enforced
- Edge case: task failure captured, others unaffected
- Edge case: submit faster than processing, tasks queue
- Error path: download fails for one chat
- Error path: exception captured by Future, not propagated
- Error path: shutdown while tasks in-flight
- Error path: early abort with cancel_pending
"""

import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from whatsapp_chat_autoexport.export.parallel_pipeline import (
    ParallelPipeline,
    PipelineTaskResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline_mock(
    side_effect=None,
    delay: float = 0.0,
    success: bool = True,
    errors: list | None = None,
):
    """Return a mock pipeline whose process_single_export behaves as configured."""
    pipeline = MagicMock()
    pipeline.config = MagicMock()
    pipeline.config.max_concurrent = 2

    def _process(chat_name, google_drive_folder=None):
        if delay:
            time.sleep(delay)
        if side_effect and chat_name in side_effect:
            raise side_effect[chat_name]
        return {
            "success": success,
            "output_path": f"/output/{chat_name}" if success else None,
            "phases_completed": ["download", "extract", "build_output"] if success else [],
            "errors": errors or [],
        }

    pipeline.process_single_export.side_effect = _process
    return pipeline


def _make_logger():
    logger = MagicMock()
    logger.debug = False
    return logger


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestParallelPipelineHappyPath:
    """Tests for normal successful operation."""

    def test_three_chats_all_succeed(self):
        """3 chats submitted, all complete successfully."""
        pipeline = _make_pipeline_mock(success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("Chat A")
        pp.submit("Chat B")
        pp.submit("Chat C")

        results = pp.collect_results()
        pp.shutdown()

        assert len(results) == 3
        names = {r.chat_name for r in results}
        assert names == {"Chat A", "Chat B", "Chat C"}
        assert all(r.success for r in results)
        assert all(r.output_path is not None for r in results)

    def test_concurrent_faster_than_sequential(self):
        """Pipeline tasks run concurrently; wall-clock < sequential sum."""
        per_task_delay = 0.3  # 300ms each
        num_tasks = 3
        sequential_min = per_task_delay * num_tasks  # 0.9s

        pipeline = _make_pipeline_mock(delay=per_task_delay, success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=3)

        start = time.monotonic()
        for i in range(num_tasks):
            pp.submit(f"Chat {i}")
        results = pp.collect_results()
        elapsed = time.monotonic() - start
        pp.shutdown()

        assert len(results) == num_tasks
        # With 3 workers, all tasks run in parallel => ~0.3s, not ~0.9s
        assert elapsed < sequential_min, (
            f"Expected < {sequential_min:.2f}s, got {elapsed:.2f}s"
        )

    def test_max_workers_enforced(self):
        """With max_workers=2, only 2 tasks run simultaneously out of 3 submitted."""
        concurrency_log: list[int] = []
        concurrency_lock = threading.Lock()
        active = {"count": 0}

        original_mock = _make_pipeline_mock(delay=0, success=True)

        def _tracking_process(chat_name, google_drive_folder=None):
            with concurrency_lock:
                active["count"] += 1
                concurrency_log.append(active["count"])
            time.sleep(0.2)
            with concurrency_lock:
                active["count"] -= 1
            return {
                "success": True,
                "output_path": f"/out/{chat_name}",
                "phases_completed": [],
                "errors": [],
            }

        original_mock.process_single_export.side_effect = _tracking_process
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=original_mock, logger=logger, max_workers=2)

        pp.submit("A")
        pp.submit("B")
        pp.submit("C")

        results = pp.collect_results()
        pp.shutdown()

        assert len(results) == 3
        # At no point should more than 2 tasks have been active
        assert max(concurrency_log) <= 2, (
            f"Max concurrency was {max(concurrency_log)}, expected <= 2"
        )

    def test_total_submitted_and_pending_count(self):
        """Properties reflect submission and completion state."""
        pipeline = _make_pipeline_mock(delay=0.2, success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=1)

        assert pp.total_submitted == 0
        assert pp.pending_count == 0

        pp.submit("Chat A")
        assert pp.total_submitted == 1

        pp.collect_results()
        pp.shutdown()
        assert pp.pending_count == 0


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestParallelPipelineEdgeCases:
    """Edge cases: failures isolated, queuing, etc."""

    def test_task_failure_isolated(self):
        """One task fails; others succeed unaffected."""
        pipeline = _make_pipeline_mock(
            side_effect={"Bad Chat": RuntimeError("Drive timeout")},
            success=True,
        )
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("Good Chat 1")
        pp.submit("Bad Chat")
        pp.submit("Good Chat 2")

        results = pp.collect_results()
        pp.shutdown()

        by_name = {r.chat_name: r for r in results}
        assert by_name["Good Chat 1"].success is True
        assert by_name["Good Chat 2"].success is True
        assert by_name["Bad Chat"].success is False
        assert len(by_name["Bad Chat"].errors) > 0

    def test_pipeline_returns_failure(self):
        """Pipeline returns success=False for one chat (not an exception)."""
        pipeline = MagicMock()
        pipeline.config = MagicMock()
        pipeline.config.max_concurrent = 2
        call_count = {"n": 0}

        def _process(chat_name, google_drive_folder=None):
            call_count["n"] += 1
            if chat_name == "Fail Chat":
                return {
                    "success": False,
                    "output_path": None,
                    "phases_completed": ["download"],
                    "errors": ["Extract failed"],
                }
            return {
                "success": True,
                "output_path": f"/out/{chat_name}",
                "phases_completed": ["download", "extract"],
                "errors": [],
            }

        pipeline.process_single_export.side_effect = _process
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("OK Chat")
        pp.submit("Fail Chat")

        results = pp.collect_results()
        pp.shutdown()

        by_name = {r.chat_name: r for r in results}
        assert by_name["OK Chat"].success is True
        assert by_name["Fail Chat"].success is False
        assert "Extract failed" in by_name["Fail Chat"].errors

    def test_submit_faster_than_processing(self):
        """Tasks queue up when submitted faster than they complete."""
        pipeline = _make_pipeline_mock(delay=0.15, success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=1)

        # Submit 4 tasks quickly (worker=1, so they queue)
        for i in range(4):
            pp.submit(f"Chat {i}")

        assert pp.total_submitted == 4
        results = pp.collect_results()
        pp.shutdown()

        assert len(results) == 4
        assert all(r.success for r in results)

    def test_submit_after_shutdown_ignored(self):
        """Submitting after shutdown logs a warning but does not error."""
        pipeline = _make_pipeline_mock(success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)
        pp.shutdown()

        pp.submit("Late Chat")  # Should not raise
        logger.warning.assert_called()
        assert pp.total_submitted == 0


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


class TestParallelPipelineErrors:
    """Error isolation and shutdown behavior."""

    def test_exception_captured_not_propagated(self):
        """Exception in processing captured by Future, not propagated to caller."""
        pipeline = _make_pipeline_mock(
            side_effect={"Boom": ValueError("kaboom")},
            success=True,
        )
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("Boom")
        pp.submit("Fine")

        # Should NOT raise
        results = pp.collect_results()
        pp.shutdown()

        by_name = {r.chat_name: r for r in results}
        assert by_name["Boom"].success is False
        assert "kaboom" in by_name["Boom"].errors[0]
        assert by_name["Fine"].success is True

    def test_shutdown_with_tasks_in_flight(self):
        """shutdown(wait=True) blocks until in-flight tasks complete."""
        pipeline = _make_pipeline_mock(delay=0.3, success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("Slow Chat")
        # Don't collect_results — go straight to shutdown
        completed = pp.shutdown(wait=True)

        # The task should have completed
        assert len(completed) == 1
        assert completed[0].chat_name == "Slow Chat"
        assert completed[0].success is True

    def test_early_abort_cancel_pending(self):
        """shutdown(cancel_pending=True) cancels queued tasks, collects completed."""
        pipeline = _make_pipeline_mock(delay=0.5, success=True)
        logger = _make_logger()
        # 1 worker: first task blocks, rest queued
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=1)

        pp.submit("Running")
        pp.submit("Queued 1")
        pp.submit("Queued 2")

        # Give the first task a moment to start
        time.sleep(0.05)

        completed = pp.shutdown(wait=True, cancel_pending=True)

        # At minimum the running task should complete; queued ones may be cancelled
        completed_names = {r.chat_name for r in completed}
        assert "Running" in completed_names
        # Total completed should be <= 3 (some may have been cancelled)
        assert len(completed) <= 3

    def test_result_has_elapsed_time(self):
        """PipelineTaskResult records elapsed time."""
        pipeline = _make_pipeline_mock(delay=0.1, success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        pp.submit("Timed Chat")
        results = pp.collect_results()
        pp.shutdown()

        assert len(results) == 1
        assert results[0].elapsed_s >= 0.05  # At least some time passed
        assert results[0].process_time_s > 0

    def test_collect_results_empty_when_nothing_submitted(self):
        """collect_results returns empty list when nothing was submitted."""
        pipeline = _make_pipeline_mock(success=True)
        logger = _make_logger()
        pp = ParallelPipeline(pipeline=pipeline, logger=logger, max_workers=2)

        results = pp.collect_results()
        pp.shutdown()

        assert results == []
