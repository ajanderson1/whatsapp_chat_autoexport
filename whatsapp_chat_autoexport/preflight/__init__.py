"""API credential preflight package.

Exports:
    run_preflight   — entry point used by headless and TUI modes
    PreflightReport — aggregate of all CheckResults
    CheckResult     — single probe result
    Status          — OK / WARN / HARD_FAIL / SKIPPED
"""

from .report import CheckResult, PreflightReport, Status

__all__ = ["CheckResult", "PreflightReport", "Status"]
