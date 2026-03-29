"""
Parallel pipeline for overlapping Drive polling + processing with UI automation.

Wraps ``ThreadPoolExecutor`` so the UI thread can submit pipeline tasks
(poll + download + extract + process) and continue exporting the next chat
without blocking.  Results are collected after all chats have been exported.
"""

from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipeline import WhatsAppPipeline
    from ..utils.logger import Logger


@dataclass
class PipelineTaskResult:
    """Result of a single background pipeline task."""

    chat_name: str
    success: bool = False
    output_path: Optional[str] = None
    phases_completed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    # Timing breakdown (set by the task wrapper)
    poll_time_s: float = 0.0
    download_time_s: float = 0.0
    process_time_s: float = 0.0


class ParallelPipeline:
    """Run pipeline tasks in background threads while UI automation continues.

    Usage::

        pp = ParallelPipeline(pipeline=my_pipeline, logger=logger, max_workers=2)
        pp.submit("Family Group")
        pp.submit("Work Chat")
        # ... UI automation continues ...
        results = pp.collect_results()
        pp.shutdown()

    Each submitted task calls ``pipeline.process_single_export(chat_name)``
    in a worker thread.  Exceptions are captured internally so the UI thread
    never sees uncaught errors from the pool (R8).
    """

    def __init__(
        self,
        pipeline: "WhatsAppPipeline",
        logger: "Logger",
        max_workers: int = 2,
    ) -> None:
        self._pipeline = pipeline
        self._logger = logger
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, Future[PipelineTaskResult]] = {}
        self._lock = RLock()
        self._shutdown = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        chat_name: str,
        google_drive_folder: Optional[str] = None,
    ) -> None:
        """Submit a pipeline task for *chat_name*.

        The task runs in a background thread and does not block the caller.
        Call :meth:`collect_results` after all submissions to gather outcomes.

        Args:
            chat_name: The chat whose export should be polled/downloaded/processed.
            google_drive_folder: Optional Drive folder override.
        """
        with self._lock:
            if self._shutdown:
                self._logger.warning(
                    f"ParallelPipeline already shut down; ignoring submit for '{chat_name}'"
                )
                return
            future = self._executor.submit(
                self._run_task, chat_name, google_drive_folder
            )
            self._futures[chat_name] = future
            self._logger.debug_msg(
                f"Submitted pipeline task for '{chat_name}' "
                f"({len(self._futures)} task(s) queued)"
            )

    def collect_results(self, timeout: Optional[float] = None) -> List[PipelineTaskResult]:
        """Wait for all submitted tasks and return their results.

        Args:
            timeout: Maximum seconds to wait for *all* futures.  ``None``
                     means wait indefinitely.

        Returns:
            List of :class:`PipelineTaskResult`, one per submitted chat.
        """
        results: List[PipelineTaskResult] = []

        with self._lock:
            futures_snapshot = dict(self._futures)

        for future in as_completed(futures_snapshot.values(), timeout=timeout):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                # Should never happen because _run_task catches everything,
                # but guard against truly unexpected issues.
                chat_name = self._chat_name_for_future(future, futures_snapshot)
                self._logger.error(
                    f"Unexpected error collecting result for '{chat_name}': {exc}"
                )
                results.append(
                    PipelineTaskResult(
                        chat_name=chat_name,
                        success=False,
                        errors=[f"Unexpected collection error: {exc}"],
                    )
                )

        return results

    def shutdown(self, wait: bool = True, cancel_pending: bool = False) -> List[PipelineTaskResult]:
        """Shut down the executor and optionally collect completed results.

        Args:
            wait: If ``True`` (default), block until in-flight tasks finish.
            cancel_pending: If ``True``, attempt to cancel tasks that have
                            not started yet.

        Returns:
            List of :class:`PipelineTaskResult` for tasks that completed
            (including errored ones).  Cancelled tasks are not included.
        """
        with self._lock:
            self._shutdown = True

        if cancel_pending:
            with self._lock:
                for chat_name, future in self._futures.items():
                    if not future.done():
                        cancelled = future.cancel()
                        if cancelled:
                            self._logger.debug_msg(
                                f"Cancelled pending pipeline task for '{chat_name}'"
                            )

        # Shut down the executor first (waits for in-flight tasks if wait=True)
        self._executor.shutdown(wait=wait)

        # Now collect results from completed futures
        completed_results: List[PipelineTaskResult] = []
        with self._lock:
            for chat_name, future in self._futures.items():
                if future.done() and not future.cancelled():
                    try:
                        completed_results.append(future.result(timeout=0))
                    except Exception as exc:
                        completed_results.append(
                            PipelineTaskResult(
                                chat_name=chat_name,
                                success=False,
                                errors=[f"Error on shutdown: {exc}"],
                            )
                        )

        return completed_results

    @property
    def pending_count(self) -> int:
        """Number of tasks that have not yet completed."""
        with self._lock:
            return sum(1 for f in self._futures.values() if not f.done())

    @property
    def total_submitted(self) -> int:
        """Total number of tasks submitted so far."""
        with self._lock:
            return len(self._futures)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_task(
        self,
        chat_name: str,
        google_drive_folder: Optional[str],
    ) -> PipelineTaskResult:
        """Execute the pipeline for a single chat.  Captures all exceptions.

        This method runs in a worker thread.
        """
        result = PipelineTaskResult(chat_name=chat_name)
        start = time.monotonic()

        try:
            self._logger.info(
                f"[pipeline-bg] Starting background processing for '{chat_name}'"
            )
            pipeline_result = self._pipeline.process_single_export(
                chat_name=chat_name,
                google_drive_folder=google_drive_folder,
            )

            result.success = pipeline_result.get("success", False)
            result.output_path = pipeline_result.get("output_path")
            result.phases_completed = pipeline_result.get("phases_completed", [])
            result.errors = pipeline_result.get("errors", [])

            if result.success:
                self._logger.info(
                    f"[pipeline-bg] Completed '{chat_name}' successfully"
                )
            else:
                self._logger.warning(
                    f"[pipeline-bg] '{chat_name}' finished with errors: "
                    f"{result.errors}"
                )

        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            self._logger.error(
                f"[pipeline-bg] Exception processing '{chat_name}': {exc}"
            )
            self._logger.debug_msg(traceback.format_exc())

        result.elapsed_s = time.monotonic() - start
        # For now the full elapsed is recorded as process_time_s.
        # When process_single_export is instrumented to return phase
        # breakdowns, those can be unpacked here.
        result.process_time_s = result.elapsed_s
        return result

    @staticmethod
    def _chat_name_for_future(
        target: Future, mapping: Dict[str, Future]
    ) -> str:
        """Reverse-lookup the chat name for a future from the mapping."""
        for name, fut in mapping.items():
            if fut is target:
                return name
        return "<unknown>"
