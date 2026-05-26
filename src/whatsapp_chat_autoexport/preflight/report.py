"""Data model for preflight results.

`Status` is the canonical health enum. `CheckResult` represents one probe's
output. `PreflightReport` aggregates the per-probe results so callers can
ask `has_hard_fail` / `has_warning` without inspecting individual rows.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Status(str, Enum):
    OK = "ok"
    WARN = "warn"
    HARD_FAIL = "hard_fail"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    provider: str
    display_name: str
    status: Status
    summary: str
    details: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PreflightReport:
    results: list[CheckResult]
    started_at: datetime
    duration_ms: int

    @property
    def has_hard_fail(self) -> bool:
        return any(r.status == Status.HARD_FAIL for r in self.results)

    @property
    def has_warning(self) -> bool:
        return any(r.status == Status.WARN for r in self.results)
