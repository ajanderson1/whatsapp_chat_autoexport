"""
Per-chat timing instrumentation for export operations.

Provides a ChatTiming dataclass to capture timing breakdowns per chat,
a PhaseTimer context-manager helper, and a summary formatter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..utils.logger import Logger


class ChatStatus(str, Enum):
    """Outcome status for a single chat export."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ChatTiming:
    """Timing breakdown for a single chat export.

    Each phase records elapsed wall-clock seconds.  Phases that were
    not reached (e.g. because the chat was skipped or failed early)
    remain at their default of ``0.0``.
    """

    chat_name: str
    ui_time_s: float = 0.0
    poll_time_s: float = 0.0
    download_time_s: float = 0.0
    process_time_s: float = 0.0
    total_time_s: float = 0.0
    status: ChatStatus = ChatStatus.SUCCESS

    def compute_total(self) -> None:
        """Set *total_time_s* to the sum of all phase times."""
        self.total_time_s = (
            self.ui_time_s
            + self.poll_time_s
            + self.download_time_s
            + self.process_time_s
        )


class PhaseTimer:
    """Simple start/stop timer that can also be used as a context manager.

    Usage::

        timer = PhaseTimer()
        timer.start()
        # ... do work ...
        elapsed = timer.stop()

    Or as a context manager::

        with PhaseTimer() as timer:
            # ... do work ...
        elapsed = timer.elapsed
    """

    def __init__(self) -> None:
        self._start: Optional[float] = None
        self._elapsed: float = 0.0

    def start(self) -> "PhaseTimer":
        """Record the start timestamp and return *self* for chaining."""
        self._start = time.monotonic()
        return self

    def stop(self) -> float:
        """Record the stop timestamp, compute elapsed, and return it."""
        if self._start is not None:
            self._elapsed = time.monotonic() - self._start
            self._start = None
        return self._elapsed

    @property
    def elapsed(self) -> float:
        """Elapsed seconds (available after :meth:`stop` or context exit)."""
        return self._elapsed

    # Context-manager protocol
    def __enter__(self) -> "PhaseTimer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.stop()


def format_duration(seconds: float) -> str:
    """Format *seconds* into a compact human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs:.1f}s"


def print_timing_summary(timings: List[ChatTiming], logger: "Logger") -> None:
    """Print a timing summary table to *logger*.

    The table contains one row per chat plus a totals row.
    """
    if not timings:
        return

    logger.info("")
    logger.info("=" * 80)
    logger.info("Per-Chat Timing Breakdown")
    logger.info("=" * 80)

    # Header
    header = (
        f"{'Chat':<30}  {'UI':>7}  {'Poll':>7}  {'DL':>7}  "
        f"{'Proc':>7}  {'Total':>7}  {'Status':<8}"
    )
    logger.info(header)
    logger.info("-" * 80)

    # Per-chat rows
    total_ui = 0.0
    total_poll = 0.0
    total_dl = 0.0
    total_proc = 0.0
    total_all = 0.0

    for ct in timings:
        name = ct.chat_name[:28] + ".." if len(ct.chat_name) > 30 else ct.chat_name
        row = (
            f"{name:<30}  "
            f"{format_duration(ct.ui_time_s):>7}  "
            f"{format_duration(ct.poll_time_s):>7}  "
            f"{format_duration(ct.download_time_s):>7}  "
            f"{format_duration(ct.process_time_s):>7}  "
            f"{format_duration(ct.total_time_s):>7}  "
            f"{ct.status.value:<8}"
        )
        logger.info(row)

        total_ui += ct.ui_time_s
        total_poll += ct.poll_time_s
        total_dl += ct.download_time_s
        total_proc += ct.process_time_s
        total_all += ct.total_time_s

    # Totals row
    logger.info("-" * 80)
    totals_row = (
        f"{'TOTAL':<30}  "
        f"{format_duration(total_ui):>7}  "
        f"{format_duration(total_poll):>7}  "
        f"{format_duration(total_dl):>7}  "
        f"{format_duration(total_proc):>7}  "
        f"{format_duration(total_all):>7}"
    )
    logger.info(totals_row)
    logger.info("=" * 80)

    # Quick stats
    success_count = sum(1 for t in timings if t.status == ChatStatus.SUCCESS)
    failed_count = sum(1 for t in timings if t.status == ChatStatus.FAILED)
    skipped_count = sum(1 for t in timings if t.status == ChatStatus.SKIPPED)
    logger.info(
        f"Success: {success_count}  |  Failed: {failed_count}  |  "
        f"Skipped: {skipped_count}  |  Total wall time: {format_duration(total_all)}"
    )
    logger.info("")
