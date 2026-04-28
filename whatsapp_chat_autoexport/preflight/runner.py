"""Preflight runner — calls each probe synchronously and aggregates results.

Three providers, three short HTTP calls, ~2-5 seconds total. Sync only;
no async complexity.
"""

from datetime import datetime
from typing import Optional

from ..config.api_key_manager import get_api_key_manager
from .probes import check_drive, check_elevenlabs, check_whisper
from .report import PreflightReport

# Thresholds — re-exported here so callers and tests can reach them via
# a single import path.
ELEVENLABS_WARN_THRESHOLD = 50_000        # chars
ELEVENLABS_HARD_THRESHOLD = 0             # chars
DRIVE_WARN_BYTES = 5 * 1024**3            # 5 GB
DRIVE_HARD_FAIL_BYTES = 500 * 1024**2     # 500 MB


def _build_drive_auth():
    """Construct a GoogleDriveAuth using the same defaults headless uses."""
    from ..google_drive.auth import GoogleDriveAuth

    return GoogleDriveAuth()


def run_preflight(*, skip_drive: bool = False) -> PreflightReport:
    """Run all probes and return an aggregated report.

    Args:
        skip_drive: When True, the Drive probe is omitted entirely (used by
            pipeline-only mode with --skip-drive-download).
    """
    started = datetime.now()
    km = get_api_key_manager()

    results = [
        check_whisper(km.get_api_key("whisper")),
        check_elevenlabs(km.get_api_key("elevenlabs")),
    ]

    if not skip_drive:
        auth = _build_drive_auth()
        results.append(check_drive(auth))

    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    return PreflightReport(
        results=results,
        started_at=started,
        duration_ms=duration_ms,
    )
