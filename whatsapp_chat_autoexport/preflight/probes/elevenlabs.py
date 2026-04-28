"""ElevenLabs probe.

Hits GET /v1/user/subscription which returns character_count, character_limit,
next_character_count_reset_unix, tier. Reports remaining capacity and warns
below 50_000 chars, hard-fails at zero.
"""

from datetime import datetime
from typing import Optional

import httpx

from ..report import CheckResult, Status

_DISPLAY = "ElevenLabs"
_ENDPOINT = "https://api.elevenlabs.io/v1/user/subscription"
_TIMEOUT = 10.0
_WARN_THRESHOLD = 50_000  # chars
_HARD_THRESHOLD = 0       # chars


def check_elevenlabs(
    api_key: Optional[str],
    *,
    _client: Optional[httpx.Client] = None,
) -> CheckResult:
    """Probe the ElevenLabs key + quota."""
    if not api_key:
        return CheckResult(
            provider="elevenlabs",
            display_name=_DISPLAY,
            status=Status.SKIPPED,
            summary="No key configured",
        )

    client = _client if _client is not None else httpx.Client(timeout=_TIMEOUT)
    try:
        try:
            response = client.get(
                _ENDPOINT,
                headers={"xi-api-key": api_key},
            )
        except httpx.HTTPError as exc:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary="Could not reach ElevenLabs",
                error=str(exc),
            )

        if response.status_code == 401:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary="Invalid key",
                error="Invalid ElevenLabs API key (401)",
            )
        if response.status_code != 200:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary=f"Unexpected response ({response.status_code})",
                error=f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            body = response.json()
            count = int(body["character_count"])
            limit = int(body["character_limit"])
            tier = str(body.get("tier", "unknown"))
            reset_unix = int(body["next_character_count_reset_unix"])
            can_extend = bool(body.get("can_extend_character_limit", False))
        except (KeyError, TypeError, ValueError) as exc:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary="Malformed subscription response",
                error=f"Could not parse response: {exc}",
            )

        remaining = limit - count
        details = {
            "character_count": count,
            "character_limit": limit,
            "characters_remaining": remaining,
            "next_reset_unix": reset_unix,
            "tier": tier,
            "can_extend_character_limit": can_extend,
        }

        if remaining <= _HARD_THRESHOLD:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary=f"Quota exhausted ({count:,}/{limit:,} chars used)",
                details=details,
            )

        reset_date = datetime.fromtimestamp(reset_unix).strftime("%Y-%m-%d")
        if remaining < _WARN_THRESHOLD:
            return CheckResult(
                provider="elevenlabs",
                display_name=_DISPLAY,
                status=Status.WARN,
                summary=(
                    f"{remaining:,} chars left ({tier}), resets {reset_date}"
                ),
                details=details,
            )
        return CheckResult(
            provider="elevenlabs",
            display_name=_DISPLAY,
            status=Status.OK,
            summary=f"{remaining:,}/{limit:,} chars left ({tier})",
            details=details,
        )
    finally:
        if _client is None:
            client.close()
