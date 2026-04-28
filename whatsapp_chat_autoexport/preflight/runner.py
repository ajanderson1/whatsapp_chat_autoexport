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


# ---------------------------------------------------------------------------
# Stderr formatter
# ---------------------------------------------------------------------------

from .report import Status as _Status  # noqa: E402

_STATUS_TOKEN = {
    _Status.OK: "OK",
    _Status.WARN: "WARN",
    _Status.HARD_FAIL: "FAIL",
    _Status.SKIPPED: "SKIP",
}

_NAME_WIDTH = 20
_TOKEN_WIDTH = 6


def format_report_for_stderr(report: PreflightReport) -> str:
    """Render a PreflightReport as fixed-width text suitable for stderr.

    Layout matches the spec:
        [preflight] OpenAI (Whisper)    OK     Key valid (...)
        [preflight] ElevenLabs          WARN   8,420 chars left
        [preflight] Google Drive        OK     12.4 GB free of 15.0 GB
        [preflight] 1 warning, 0 hard failures — proceeding (370 ms)

    On hard fail, the trailing line names the abort and points at the
    --skip-preflight escape hatch.
    """
    lines = []
    n_warn = 0
    n_fail = 0

    for r in report.results:
        token = _STATUS_TOKEN[r.status]
        if r.status == _Status.WARN:
            n_warn += 1
        elif r.status == _Status.HARD_FAIL:
            n_fail += 1
        lines.append(
            f"[preflight] {r.display_name.ljust(_NAME_WIDTH)} "
            f"{token.ljust(_TOKEN_WIDTH)} {r.summary}"
        )

    if n_fail > 0:
        lines.append(
            f"[preflight] Aborting: {n_fail} hard "
            f"{'failure' if n_fail == 1 else 'failures'}. "
            "Use --skip-preflight to bypass."
        )
    else:
        warn_word = "warning" if n_warn == 1 else "warnings"
        fail_word = "hard failure" if n_fail == 1 else "hard failures"
        lines.append(
            f"[preflight] {n_warn} {warn_word}, {n_fail} {fail_word} — "
            f"proceeding ({report.duration_ms} ms)"
        )

    return "\n".join(lines)
