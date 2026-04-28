"""Whisper (OpenAI) probe.

OpenAI exposes no quota endpoint, so `check_whisper` is purely a key-validity
check via GET /v1/models. Key works → OK. Key rejected → HARD_FAIL. Network
error → HARD_FAIL. No key → SKIPPED.
"""

from typing import Optional

import httpx

from ..report import CheckResult, Status

_DISPLAY = "OpenAI (Whisper)"
_ENDPOINT = "https://api.openai.com/v1/models"
_TIMEOUT = 10.0


def check_whisper(
    api_key: Optional[str],
    *,
    _client: Optional[httpx.Client] = None,
) -> CheckResult:
    """Probe the OpenAI key by hitting /v1/models.

    Args:
        api_key: The OPENAI_API_KEY value, or None if not configured.
        _client: Test seam — inject an httpx.Client with a MockTransport to
            avoid real network calls. Production callers leave this None.

    Returns:
        CheckResult with status:
            SKIPPED   — no key configured
            OK        — 200 from /v1/models
            HARD_FAIL — 401 / 5xx / network error
    """
    if not api_key:
        return CheckResult(
            provider="whisper",
            display_name=_DISPLAY,
            status=Status.SKIPPED,
            summary="No key configured",
        )

    client = _client if _client is not None else httpx.Client(timeout=_TIMEOUT)
    try:
        try:
            response = client.get(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        except httpx.HTTPError as exc:
            return CheckResult(
                provider="whisper",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary="Could not reach OpenAI",
                error=str(exc),
            )

        if response.status_code == 200:
            return CheckResult(
                provider="whisper",
                display_name=_DISPLAY,
                status=Status.OK,
                summary="Key valid (quota not introspectable)",
                details={"key_valid": True, "models_endpoint_ok": True},
            )
        if response.status_code == 401:
            return CheckResult(
                provider="whisper",
                display_name=_DISPLAY,
                status=Status.HARD_FAIL,
                summary="Invalid key",
                error="Invalid OpenAI API key (401)",
            )
        return CheckResult(
            provider="whisper",
            display_name=_DISPLAY,
            status=Status.HARD_FAIL,
            summary=f"Unexpected response ({response.status_code})",
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )
    finally:
        if _client is None:
            client.close()
