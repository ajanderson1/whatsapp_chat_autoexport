"""Google Drive probe — OAuth + storage quota.

Reuses GoogleDriveAuth (no duplicate auth flow). Calls
about().get(fields="storageQuota,user").execute() and reports free space.
Pooled (Workspace) accounts return no limit → always OK.
"""

from typing import Optional

from ..report import CheckResult, Status

_DISPLAY = "Google Drive"
_HARD_FAIL_BYTES = 500 * 1024**2  # 500 MB
_WARN_BYTES = 5 * 1024**3         # 5 GB


def _format_bytes(n: int) -> str:
    """Human-readable bytes (binary units)."""
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def check_drive(auth) -> CheckResult:
    """Probe Drive auth + storage.

    Args:
        auth: A GoogleDriveAuth instance, or None.

    Returns:
        CheckResult.
    """
    if auth is None or not auth.has_credentials():
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary="Not authenticated",
            error="No Drive credentials available",
        )

    try:
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary="Drive libraries missing",
            error=str(exc),
        )

    try:
        service = auth.get_service()
        about = service.about().get(fields="storageQuota,user").execute()
    except RefreshError as exc:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary="OAuth token expired/revoked",
            error=f"Token refresh failed: {exc}",
        )
    except HttpError as exc:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary="Drive API error",
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — last-resort fallback
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary="Drive probe failed",
            error=f"{type(exc).__name__}: {exc}",
        )

    quota = about.get("storageQuota", {}) or {}
    user = about.get("user", {}) or {}
    used_str = quota.get("usage")
    limit_str = quota.get("limit")  # may be missing for pooled accounts

    used = int(used_str) if used_str is not None else 0
    limit = int(limit_str) if limit_str is not None else None

    details = {
        "token_valid": True,
        "storage_used_bytes": used,
        "storage_limit_bytes": limit,
        "storage_free_bytes": (limit - used) if limit is not None else None,
        "user_email": user.get("emailAddress"),
    }

    if limit is None:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.OK,
            summary="Authenticated (storage limit not reported)",
            details=details,
        )

    free = limit - used
    if free < _HARD_FAIL_BYTES:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary=f"Only {_format_bytes(free)} free",
            details=details,
        )
    if free < _WARN_BYTES:
        return CheckResult(
            provider="drive",
            display_name=_DISPLAY,
            status=Status.WARN,
            summary=f"{_format_bytes(free)} free (low)",
            details=details,
        )
    return CheckResult(
        provider="drive",
        display_name=_DISPLAY,
        status=Status.OK,
        summary=f"{_format_bytes(free)} free of {_format_bytes(limit)}",
        details=details,
    )
