# API Credential Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch credential, quota, and storage problems **before** a long export run starts, so users don't lose 20+ minutes mid-run to a 401, an exhausted ElevenLabs character budget, or a full Google Drive.

**Architecture:** New `whatsapp_chat_autoexport/preflight/` package with three pure-function probes (Whisper, ElevenLabs, Drive) coordinated by a synchronous `runner.py`. Probes never raise — they return `CheckResult` objects. The runner returns a `PreflightReport` aggregate. Three consumers wire it in: `headless.run_headless`, `headless.run_pipeline_only`, and `tui.textual_panes.connect_pane.ConnectPane`.

**Tech Stack:** Python 3.13, httpx (raw GET), dataclasses + Enum, pytest with httpx.MockTransport, Textual pilot tests.

**Spec reference:** `docs/specs/2026-04-27-preflight-design.md`

**Note on TUI integration:** the spec mentions `discovery_screen.py`. The current codebase uses `tui/textual_screens/main_screen.py` (single tabbed screen) with `tui/textual_panes/connect_pane.py` for the device-connection step. The plan integrates the `PreflightPanel` into `ConnectPane` to keep the spec's intent (preflight visible before the user proceeds) without inventing a screen that does not exist.

---

## File Structure

**New files:**
- `whatsapp_chat_autoexport/preflight/__init__.py` — public exports
- `whatsapp_chat_autoexport/preflight/report.py` — `Status` enum, `CheckResult`, `PreflightReport`
- `whatsapp_chat_autoexport/preflight/runner.py` — `run_preflight()`, threshold constants, stderr formatter
- `whatsapp_chat_autoexport/preflight/probes/__init__.py` — re-exports probes
- `whatsapp_chat_autoexport/preflight/probes/whisper.py` — `check_whisper(api_key)`
- `whatsapp_chat_autoexport/preflight/probes/elevenlabs.py` — `check_elevenlabs(api_key)`
- `whatsapp_chat_autoexport/preflight/probes/drive.py` — `check_drive(auth)`
- `whatsapp_chat_autoexport/tui/textual_widgets/preflight_panel.py` — `PreflightPanel` widget
- `tests/unit/test_preflight_report.py` — `PreflightReport`/`CheckResult`/`Status` tests
- `tests/unit/test_preflight_probes.py` — three probe modules' behaviour
- `tests/unit/test_preflight_runner.py` — runner aggregation + stderr format
- `tests/unit/test_preflight_panel.py` — Textual widget rendering
- `tests/integration/test_headless_preflight.py` — `run_headless`/`run_pipeline_only` exit codes
- `tests/integration/test_connect_pane_preflight.py` — `ConnectPane` pilot test
- `tests/manual/__init__.py` — marker file
- `tests/manual/test_preflight_live.py` — manual live test, skipped by default
- `tests/fixtures/preflight/elevenlabs_subscription_full.json`
- `tests/fixtures/preflight/elevenlabs_subscription_low.json`
- `tests/fixtures/preflight/elevenlabs_subscription_exhausted.json`
- `tests/fixtures/preflight/drive_about_full.json`
- `tests/fixtures/preflight/drive_about_low.json`
- `tests/fixtures/preflight/drive_about_exhausted.json`
- `tests/fixtures/preflight/drive_about_pooled.json`

**Modified files:**
- `pyproject.toml` — add `httpx = "^0.28.1"` to deps
- `whatsapp_chat_autoexport/cli_entry.py` — add `--skip-preflight` flag
- `whatsapp_chat_autoexport/headless.py` — call `run_preflight()` in `run_headless` and `run_pipeline_only`
- `whatsapp_chat_autoexport/tui/textual_panes/connect_pane.py` — mount `PreflightPanel`, gate Connected message on no hard-fail (unless skipped)
- `whatsapp_chat_autoexport/tui/textual_widgets/__init__.py` — export `PreflightPanel`
- `whatsapp_chat_autoexport/tui/textual_app.py` — add `skip_preflight` arg, plumb to `ConnectPane`
- `CLAUDE.md` — document `--skip-preflight` flag

---

## Task Plan Overview

| # | Task | Files |
|---|---|---|
| 1 | Add `httpx` dependency | `pyproject.toml` |
| 2 | Create `Status`/`CheckResult`/`PreflightReport` data model | `preflight/report.py` |
| 3 | Implement Whisper probe | `preflight/probes/whisper.py` |
| 4 | Implement ElevenLabs probe | `preflight/probes/elevenlabs.py` |
| 5 | Implement Drive probe | `preflight/probes/drive.py` |
| 6 | Create runner + threshold constants + skip_drive | `preflight/runner.py`, `preflight/__init__.py` |
| 7 | Add stderr formatter for headless | `preflight/runner.py` |
| 8 | Add `--skip-preflight` CLI flag | `cli_entry.py` |
| 9 | Wire preflight into `run_headless` | `headless.py` |
| 10 | Wire preflight into `run_pipeline_only` | `headless.py` |
| 11 | Build `PreflightPanel` Textual widget | `preflight_panel.py`, `__init__.py` |
| 12 | Mount `PreflightPanel` in `ConnectPane`, gate connection | `connect_pane.py`, `textual_app.py` |
| 13 | Write `ConnectPane` pilot integration test | `test_connect_pane_preflight.py` |
| 14 | Write manual live test (skipped by default) | `test_preflight_live.py` |
| 15 | Update `CLAUDE.md` with new flag | `CLAUDE.md` |

---

## Task 1: Add `httpx` dependency

**Files:**
- Modify: `pyproject.toml` (deps section, after `python-dotenv` line)

- [ ] **Step 1: Inspect current deps**

Run: `grep -n "python-dotenv\|elevenlabs" pyproject.toml`
Expected: shows the lines around where to insert.

- [ ] **Step 2: Add httpx to `[tool.poetry.dependencies]`**

Edit `pyproject.toml` — insert this line directly after `python-dotenv = "^1.1.0"`:

```toml
httpx = "^0.28.1"
```

- [ ] **Step 3: Lock and install**

Run: `poetry lock --no-update && poetry install`
Expected: succeeds; `httpx` appears in `poetry show httpx`.

- [ ] **Step 4: Verify import works**

Run: `poetry run python -c "import httpx; print(httpx.__version__)"`
Expected: prints something like `0.28.1`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "feat(preflight): add httpx as explicit dependency

Preflight probes use raw GET requests to /v1/models, /v1/user/subscription,
and Drive about.get to surface validity and quota before runs. SDKs do not
expose subscription/quota uniformly. httpx was already a transitive dep."
```

---

## Task 2: Data Model — `Status`, `CheckResult`, `PreflightReport`

**Files:**
- Create: `whatsapp_chat_autoexport/preflight/__init__.py`
- Create: `whatsapp_chat_autoexport/preflight/report.py`
- Test: `tests/unit/test_preflight_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_preflight_report.py`:

```python
"""Tests for preflight data model: Status, CheckResult, PreflightReport."""

from datetime import datetime

import pytest

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)


class TestStatus:
    def test_status_string_values(self):
        assert Status.OK.value == "ok"
        assert Status.WARN.value == "warn"
        assert Status.HARD_FAIL.value == "hard_fail"
        assert Status.SKIPPED.value == "skipped"

    def test_status_is_str_enum(self):
        # Must be comparable to plain strings (str subclass)
        assert Status.OK == "ok"


class TestCheckResult:
    def test_minimal_construction(self):
        r = CheckResult(
            provider="whisper",
            display_name="OpenAI (Whisper)",
            status=Status.OK,
            summary="Key valid",
        )
        assert r.provider == "whisper"
        assert r.display_name == "OpenAI (Whisper)"
        assert r.status == Status.OK
        assert r.summary == "Key valid"
        assert r.details == {}
        assert r.error is None

    def test_with_details_and_error(self):
        r = CheckResult(
            provider="elevenlabs",
            display_name="ElevenLabs",
            status=Status.HARD_FAIL,
            summary="Invalid key",
            details={"tier": "creator"},
            error="401 Unauthorized",
        )
        assert r.details == {"tier": "creator"}
        assert r.error == "401 Unauthorized"


class TestPreflightReport:
    def _make(self, statuses: list[Status]) -> PreflightReport:
        results = [
            CheckResult(
                provider=f"p{i}",
                display_name=f"P{i}",
                status=s,
                summary="x",
            )
            for i, s in enumerate(statuses)
        ]
        return PreflightReport(
            results=results,
            started_at=datetime(2026, 1, 1),
            duration_ms=123,
        )

    def test_has_hard_fail_true(self):
        report = self._make([Status.OK, Status.HARD_FAIL, Status.OK])
        assert report.has_hard_fail is True

    def test_has_hard_fail_false(self):
        report = self._make([Status.OK, Status.WARN, Status.SKIPPED])
        assert report.has_hard_fail is False

    def test_has_warning_true(self):
        report = self._make([Status.OK, Status.WARN])
        assert report.has_warning is True

    def test_has_warning_false_when_only_ok(self):
        report = self._make([Status.OK, Status.OK])
        assert report.has_warning is False

    def test_empty_results(self):
        report = PreflightReport(results=[], started_at=datetime.now(), duration_ms=0)
        assert report.has_hard_fail is False
        assert report.has_warning is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_preflight_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whatsapp_chat_autoexport.preflight'`.

- [ ] **Step 3: Create the package init**

Create `whatsapp_chat_autoexport/preflight/__init__.py`:

```python
"""API credential preflight package.

Exports:
    run_preflight   — entry point used by headless and TUI modes
    PreflightReport — aggregate of all CheckResults
    CheckResult     — single probe result
    Status          — OK / WARN / HARD_FAIL / SKIPPED
"""

from .report import CheckResult, PreflightReport, Status

__all__ = ["CheckResult", "PreflightReport", "Status"]
```

- [ ] **Step 4: Implement the data model**

Create `whatsapp_chat_autoexport/preflight/report.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_preflight_report.py -v`
Expected: 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/__init__.py \
       whatsapp_chat_autoexport/preflight/report.py \
       tests/unit/test_preflight_report.py
git commit -m "feat(preflight): add Status enum, CheckResult, PreflightReport

Foundational data model. Probes return CheckResult, runner aggregates them
into a PreflightReport with has_hard_fail/has_warning properties for the
hard-fail gate."
```

---

## Task 3: Whisper Probe

**Files:**
- Create: `whatsapp_chat_autoexport/preflight/probes/__init__.py`
- Create: `whatsapp_chat_autoexport/preflight/probes/whisper.py`
- Test: `tests/unit/test_preflight_probes.py` (new — Whisper section)

- [ ] **Step 1: Write the failing tests for Whisper**

Create `tests/unit/test_preflight_probes.py`:

```python
"""Tests for preflight probes (whisper, elevenlabs, drive)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from whatsapp_chat_autoexport.preflight.report import Status


# ---------------------------------------------------------------------------
# Helpers — build a mocked httpx.Client transport that the probes can use
# ---------------------------------------------------------------------------

def _mock_transport(response_factory):
    """Return an httpx.MockTransport that serves the given factory."""
    return httpx.MockTransport(response_factory)


# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------

class TestWhisperProbe:
    def test_no_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        result = check_whisper(None)
        assert result.status == Status.SKIPPED
        assert result.provider == "whisper"
        assert result.display_name == "OpenAI (Whisper)"

    def test_empty_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        result = check_whisper("")
        assert result.status == Status.SKIPPED

    def test_valid_key_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/models"
            assert request.headers["authorization"] == "Bearer sk-test"
            return httpx.Response(200, json={"data": []})

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.OK
        assert "Key valid" in result.summary
        assert result.details["key_valid"] is True
        assert result.details["models_endpoint_ok"] is True

    def test_invalid_key_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid"}})

        result = check_whisper("sk-bad", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL
        assert "Invalid OpenAI API key" in result.error

    def test_server_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL

    def test_network_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        result = check_whisper("sk-test", _client=httpx.Client(transport=_mock_transport(handler)))
        assert result.status == Status.HARD_FAIL
        assert result.error  # non-empty
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whatsapp_chat_autoexport.preflight.probes'`.

- [ ] **Step 3: Create the probes package init**

Create `whatsapp_chat_autoexport/preflight/probes/__init__.py`:

```python
"""Probe functions — one per provider."""

from .drive import check_drive
from .elevenlabs import check_elevenlabs
from .whisper import check_whisper

__all__ = ["check_whisper", "check_elevenlabs", "check_drive"]
```

(`check_drive` and `check_elevenlabs` are imported here for re-export but
will be created in Tasks 4 and 5. Run after Task 5 completes if the import
trips; until then, comment those two out and re-enable in Task 5.)

**For now, write a stub to keep this task self-contained:**

```python
"""Probe functions — one per provider."""

from .whisper import check_whisper

__all__ = ["check_whisper"]
```

(Tasks 4 and 5 will append `check_elevenlabs` and `check_drive` as they
land.)

- [ ] **Step 4: Implement the Whisper probe**

Create `whatsapp_chat_autoexport/preflight/probes/whisper.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/probes/__init__.py \
       whatsapp_chat_autoexport/preflight/probes/whisper.py \
       tests/unit/test_preflight_probes.py
git commit -m "feat(preflight): add Whisper key-validity probe

Hits GET /v1/models with the user's OPENAI_API_KEY. Returns OK on 200,
HARD_FAIL on 401/5xx/network errors, SKIPPED when no key. OpenAI exposes
no quota endpoint, so OK is the strongest signal we get."
```

---

## Task 4: ElevenLabs Probe

**Files:**
- Create: `whatsapp_chat_autoexport/preflight/probes/elevenlabs.py`
- Create: `tests/fixtures/preflight/elevenlabs_subscription_full.json`
- Create: `tests/fixtures/preflight/elevenlabs_subscription_low.json`
- Create: `tests/fixtures/preflight/elevenlabs_subscription_exhausted.json`
- Modify: `whatsapp_chat_autoexport/preflight/probes/__init__.py`
- Modify: `tests/unit/test_preflight_probes.py` (append ElevenLabs section)

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/preflight/elevenlabs_subscription_full.json`:

```json
{
  "tier": "creator",
  "character_count": 1000,
  "character_limit": 100000,
  "can_extend_character_limit": true,
  "next_character_count_reset_unix": 1746057600,
  "currency": "usd",
  "status": "active"
}
```

Create `tests/fixtures/preflight/elevenlabs_subscription_low.json`:

```json
{
  "tier": "creator",
  "character_count": 95000,
  "character_limit": 100000,
  "can_extend_character_limit": true,
  "next_character_count_reset_unix": 1746057600,
  "currency": "usd",
  "status": "active"
}
```

Create `tests/fixtures/preflight/elevenlabs_subscription_exhausted.json`:

```json
{
  "tier": "creator",
  "character_count": 100000,
  "character_limit": 100000,
  "can_extend_character_limit": false,
  "next_character_count_reset_unix": 1746057600,
  "currency": "usd",
  "status": "active"
}
```

- [ ] **Step 2: Append ElevenLabs tests**

Append to `tests/unit/test_preflight_probes.py`:

```python
# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures" / "preflight"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


class TestElevenLabsProbe:
    def test_no_key_skipped(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        result = check_elevenlabs(None)
        assert result.status == Status.SKIPPED
        assert result.provider == "elevenlabs"

    def test_full_quota_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_full.json")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/user/subscription"
            assert request.headers["xi-api-key"] == "el-test"
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.OK
        assert result.details["character_count"] == 1000
        assert result.details["character_limit"] == 100000
        assert result.details["characters_remaining"] == 99000
        assert result.details["tier"] == "creator"
        assert result.details["next_reset_unix"] == 1746057600

    def test_low_quota_warn(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_low.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.WARN
        assert result.details["characters_remaining"] == 5000

    def test_exhausted_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        body = _load_fixture("elevenlabs_subscription_exhausted.json")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.details["characters_remaining"] == 0

    def test_invalid_key_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Unauthorized"})

        result = check_elevenlabs(
            "bad",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.error  # non-empty

    def test_network_error_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timed out")

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL

    def test_malformed_response_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.elevenlabs import (
            check_elevenlabs,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        result = check_elevenlabs(
            "el-test",
            _client=httpx.Client(transport=_mock_transport(handler)),
        )
        assert result.status == Status.HARD_FAIL
        assert result.error
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestElevenLabsProbe -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the ElevenLabs probe**

Create `whatsapp_chat_autoexport/preflight/probes/elevenlabs.py`:

```python
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
```

- [ ] **Step 5: Re-export from probes package**

Edit `whatsapp_chat_autoexport/preflight/probes/__init__.py`:

```python
"""Probe functions — one per provider."""

from .elevenlabs import check_elevenlabs
from .whisper import check_whisper

__all__ = ["check_whisper", "check_elevenlabs"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestElevenLabsProbe -v`
Expected: 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/probes/elevenlabs.py \
       whatsapp_chat_autoexport/preflight/probes/__init__.py \
       tests/fixtures/preflight/elevenlabs_subscription_full.json \
       tests/fixtures/preflight/elevenlabs_subscription_low.json \
       tests/fixtures/preflight/elevenlabs_subscription_exhausted.json \
       tests/unit/test_preflight_probes.py
git commit -m "feat(preflight): add ElevenLabs subscription probe

GET /v1/user/subscription. WARN below 50k chars remaining, HARD_FAIL at
zero, OK otherwise. Surfaces tier and reset date in summary."
```

---

## Task 5: Drive Probe

**Files:**
- Create: `whatsapp_chat_autoexport/preflight/probes/drive.py`
- Create: `tests/fixtures/preflight/drive_about_full.json`
- Create: `tests/fixtures/preflight/drive_about_low.json`
- Create: `tests/fixtures/preflight/drive_about_exhausted.json`
- Create: `tests/fixtures/preflight/drive_about_pooled.json`
- Modify: `whatsapp_chat_autoexport/preflight/probes/__init__.py`
- Modify: `tests/unit/test_preflight_probes.py` (append Drive section)

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/preflight/drive_about_full.json`:

```json
{
  "user": {"emailAddress": "user@example.com", "displayName": "User"},
  "storageQuota": {
    "limit": "16106127360",
    "usage": "3221225472"
  }
}
```

(`16 GiB` limit, `3 GiB` used → ~13 GiB free → OK)

Create `tests/fixtures/preflight/drive_about_low.json`:

```json
{
  "user": {"emailAddress": "user@example.com", "displayName": "User"},
  "storageQuota": {
    "limit": "16106127360",
    "usage": "13958643712"
  }
}
```

(`16 GiB` limit, `13 GiB` used → ~2 GiB free → WARN)

Create `tests/fixtures/preflight/drive_about_exhausted.json`:

```json
{
  "user": {"emailAddress": "user@example.com", "displayName": "User"},
  "storageQuota": {
    "limit": "16106127360",
    "usage": "16000000000"
  }
}
```

(`16 GiB` limit, `15.9 GiB` used → ~100 MiB free → HARD_FAIL)

Create `tests/fixtures/preflight/drive_about_pooled.json`:

```json
{
  "user": {"emailAddress": "user@workspace.example.com", "displayName": "Workspace User"},
  "storageQuota": {
    "usage": "5368709120"
  }
}
```

(no `limit` key → pooled storage → OK with no warning)

- [ ] **Step 2: Append Drive tests**

Append to `tests/unit/test_preflight_probes.py`:

```python
# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

class _FakeAbout:
    """Minimal stand-in for googleapiclient about() resource."""

    def __init__(self, response_or_exc):
        self._response_or_exc = response_or_exc

    def get(self, fields):
        return self  # `.execute()` is the next call

    def execute(self):
        if isinstance(self._response_or_exc, Exception):
            raise self._response_or_exc
        return self._response_or_exc


class _FakeService:
    def __init__(self, response_or_exc):
        self._inner = _FakeAbout(response_or_exc)

    def about(self):
        return self._inner


class _FakeAuth:
    """Stand-in for GoogleDriveAuth used by check_drive."""

    def __init__(self, has_creds: bool, response_or_exc=None):
        self._has = has_creds
        self._response_or_exc = response_or_exc

    def has_credentials(self) -> bool:
        return self._has

    def get_service(self):
        return _FakeService(self._response_or_exc)


class TestDriveProbe:
    def test_no_auth_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        result = check_drive(None)
        assert result.status == Status.HARD_FAIL
        assert result.provider == "drive"

    def test_no_creds_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(has_creds=False)
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL

    def test_token_expired_hard_fail(self):
        from google.auth.exceptions import RefreshError

        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=RefreshError("Token expired"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL
        assert "expired" in result.error.lower() or "revoked" in result.error.lower()

    def test_full_storage_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_full.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.OK
        assert result.details["storage_limit_bytes"] == 16106127360
        assert result.details["storage_used_bytes"] == 3221225472

    def test_low_storage_warn(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_low.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.WARN

    def test_exhausted_storage_hard_fail(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_exhausted.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL

    def test_pooled_no_limit_ok(self):
        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=_load_fixture("drive_about_pooled.json"),
        )
        result = check_drive(auth)
        assert result.status == Status.OK
        assert result.details["storage_limit_bytes"] is None
        assert "limit not reported" in result.summary.lower()

    def test_http_error_hard_fail(self):
        from googleapiclient.errors import HttpError

        from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

        # HttpError requires (resp, content); use a minimal stand-in
        class _FakeResp:
            status = 503
            reason = "Service Unavailable"

        auth = _FakeAuth(
            has_creds=True,
            response_or_exc=HttpError(_FakeResp(), b"err"),
        )
        result = check_drive(auth)
        assert result.status == Status.HARD_FAIL
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestDriveProbe -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the Drive probe**

Create `whatsapp_chat_autoexport/preflight/probes/drive.py`:

```python
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

    # Imports deferred — we don't want preflight import to hard-fail when the
    # google libs aren't installed in some lightweight contexts.
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
```

**Note:** The probe calls `auth.get_service()`. The current
`GoogleDriveAuth` class does not have that method — it has `get_credentials()`.
We'll add a thin `get_service()` shim during this task to avoid duplicating
service-construction logic across probes and existing code paths.

- [ ] **Step 5: Add `get_service()` to `GoogleDriveAuth`**

Modify `whatsapp_chat_autoexport/google_drive/auth.py` — append after
`get_credentials_status()`:

```python
    def has_credentials(self) -> bool:
        """Lightweight check used by preflight: token file exists and is loadable.

        Does NOT trigger an OAuth flow. Returns False if no token,
        if pickle load fails, or if credentials lack a refresh token.
        """
        if not self.token_file.exists():
            return False
        try:
            creds = self.load_token()
        except Exception:
            return False
        return creds is not None

    def get_service(self):
        """Build a Drive v3 API service using the cached credentials.

        Used by preflight (and any caller that needs a quick about() lookup
        without re-running auth). Raises if no credentials are loaded.
        """
        from googleapiclient.discovery import build

        if not self.credentials:
            self.credentials = self.load_token()
        if not self.credentials:
            raise RuntimeError("No Drive credentials available")
        return build("drive", "v3", credentials=self.credentials, cache_discovery=False)
```

- [ ] **Step 6: Re-export from probes package**

Replace `whatsapp_chat_autoexport/preflight/probes/__init__.py`:

```python
"""Probe functions — one per provider."""

from .drive import check_drive
from .elevenlabs import check_elevenlabs
from .whisper import check_whisper

__all__ = ["check_whisper", "check_elevenlabs", "check_drive"]
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestDriveProbe -v`
Expected: 8 tests PASS.

Run: `poetry run pytest tests/unit/test_preflight_probes.py -v`
Expected: all 21 probe tests PASS.

- [ ] **Step 8: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/probes/drive.py \
       whatsapp_chat_autoexport/preflight/probes/__init__.py \
       whatsapp_chat_autoexport/google_drive/auth.py \
       tests/fixtures/preflight/drive_about_full.json \
       tests/fixtures/preflight/drive_about_low.json \
       tests/fixtures/preflight/drive_about_exhausted.json \
       tests/fixtures/preflight/drive_about_pooled.json \
       tests/unit/test_preflight_probes.py
git commit -m "feat(preflight): add Drive OAuth + storage probe

Reuses GoogleDriveAuth (with new has_credentials() and get_service()
helpers). HARD_FAIL on missing creds, RefreshError, or <500 MB free.
WARN below 5 GB free. Pooled (Workspace) accounts always OK."
```

---

## Task 6: Runner

**Files:**
- Create: `whatsapp_chat_autoexport/preflight/runner.py`
- Modify: `whatsapp_chat_autoexport/preflight/__init__.py`
- Test: `tests/unit/test_preflight_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_preflight_runner.py`:

```python
"""Tests for the preflight runner."""

from datetime import datetime
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.preflight.report import CheckResult, Status
from whatsapp_chat_autoexport.preflight.runner import (
    DRIVE_HARD_FAIL_BYTES,
    DRIVE_WARN_BYTES,
    ELEVENLABS_HARD_THRESHOLD,
    ELEVENLABS_WARN_THRESHOLD,
    run_preflight,
)


def _ok(provider, name):
    return CheckResult(provider=provider, display_name=name, status=Status.OK, summary="ok")


def _fail(provider, name):
    return CheckResult(
        provider=provider, display_name=name, status=Status.HARD_FAIL, summary="bad"
    )


def _warn(provider, name):
    return CheckResult(
        provider=provider, display_name=name, status=Status.WARN, summary="meh"
    )


class TestRunner:
    def test_constants_exist(self):
        assert ELEVENLABS_WARN_THRESHOLD == 50_000
        assert ELEVENLABS_HARD_THRESHOLD == 0
        assert DRIVE_WARN_BYTES == 5 * 1024**3
        assert DRIVE_HARD_FAIL_BYTES == 500 * 1024**2

    def test_aggregates_three_results(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_ok("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_warn("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive",
            return_value=_ok("drive", "Google Drive"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth",
            return_value=object(),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.side_effect = lambda p: f"key-{p}"

            report = run_preflight()

        assert len(report.results) == 3
        providers = [r.provider for r in report.results]
        assert providers == ["whisper", "elevenlabs", "drive"]
        assert report.has_warning is True
        assert report.has_hard_fail is False
        assert isinstance(report.started_at, datetime)
        assert report.duration_ms >= 0

    def test_skip_drive_omits_probe(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_ok("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_ok("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive"
        ) as drive_mock, patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth"
        ) as build_mock, patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.return_value = "k"

            report = run_preflight(skip_drive=True)

        drive_mock.assert_not_called()
        build_mock.assert_not_called()
        providers = [r.provider for r in report.results]
        assert "drive" not in providers
        assert len(report.results) == 2

    def test_hard_fail_propagates(self):
        with patch(
            "whatsapp_chat_autoexport.preflight.runner.check_whisper",
            return_value=_fail("whisper", "OpenAI (Whisper)"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_elevenlabs",
            return_value=_ok("elevenlabs", "ElevenLabs"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.check_drive",
            return_value=_ok("drive", "Google Drive"),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner._build_drive_auth",
            return_value=object(),
        ), patch(
            "whatsapp_chat_autoexport.preflight.runner.get_api_key_manager"
        ) as km_mock:
            km_mock.return_value.get_api_key.return_value = "k"

            report = run_preflight()

        assert report.has_hard_fail is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_preflight_runner.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_preflight'`.

- [ ] **Step 3: Implement the runner**

Create `whatsapp_chat_autoexport/preflight/runner.py`:

```python
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
```

- [ ] **Step 4: Re-export from package**

Replace `whatsapp_chat_autoexport/preflight/__init__.py`:

```python
"""API credential preflight package."""

from .report import CheckResult, PreflightReport, Status
from .runner import (
    DRIVE_HARD_FAIL_BYTES,
    DRIVE_WARN_BYTES,
    ELEVENLABS_HARD_THRESHOLD,
    ELEVENLABS_WARN_THRESHOLD,
    run_preflight,
)

__all__ = [
    "CheckResult",
    "PreflightReport",
    "Status",
    "run_preflight",
    "DRIVE_HARD_FAIL_BYTES",
    "DRIVE_WARN_BYTES",
    "ELEVENLABS_HARD_THRESHOLD",
    "ELEVENLABS_WARN_THRESHOLD",
]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_preflight_runner.py -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/runner.py \
       whatsapp_chat_autoexport/preflight/__init__.py \
       tests/unit/test_preflight_runner.py
git commit -m "feat(preflight): add run_preflight() runner

Synchronous orchestrator. Calls all three probes, returns
PreflightReport with timing. skip_drive=True for pipeline-only +
--skip-drive-download. Threshold constants exposed at package level."
```

---

## Task 7: Stderr Formatter

**Files:**
- Modify: `whatsapp_chat_autoexport/preflight/runner.py`
- Modify: `tests/unit/test_preflight_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_preflight_runner.py`:

```python
from datetime import datetime as _dt

from whatsapp_chat_autoexport.preflight.report import CheckResult, PreflightReport, Status
from whatsapp_chat_autoexport.preflight.runner import format_report_for_stderr


def _report(*statuses_and_summaries):
    results = []
    for provider, name, status, summary in statuses_and_summaries:
        results.append(
            CheckResult(
                provider=provider,
                display_name=name,
                status=status,
                summary=summary,
            )
        )
    return PreflightReport(results=results, started_at=_dt(2026, 1, 1), duration_ms=370)


class TestFormatReport:
    def test_all_ok(self):
        report = _report(
            ("whisper", "OpenAI (Whisper)", Status.OK, "Key valid"),
            ("elevenlabs", "ElevenLabs", Status.OK, "99,000/100,000 chars left (creator)"),
            ("drive", "Google Drive", Status.OK, "12.4 GB free of 15.0 GB"),
        )
        lines = format_report_for_stderr(report).splitlines()

        # One row per provider plus one summary line
        assert len(lines) == 4
        assert "[preflight] OpenAI (Whisper)" in lines[0]
        assert " OK " in lines[0]
        assert "Key valid" in lines[0]
        assert "0 warnings, 0 hard failures" in lines[3]
        assert "proceeding" in lines[3]
        assert "370 ms" in lines[3]

    def test_warn_displays_warn_token(self):
        report = _report(
            ("elevenlabs", "ElevenLabs", Status.WARN, "8,420 chars left"),
        )
        out = format_report_for_stderr(report)
        assert " WARN " in out
        assert "1 warning" in out

    def test_hard_fail_displays_fail_and_aborts(self):
        report = _report(
            ("elevenlabs", "ElevenLabs", Status.HARD_FAIL, "Quota exhausted"),
        )
        out = format_report_for_stderr(report)
        assert " FAIL " in out
        assert "Aborting" in out
        assert "--skip-preflight" in out

    def test_skipped_displays_skip(self):
        report = _report(
            ("whisper", "OpenAI (Whisper)", Status.SKIPPED, "No key configured"),
        )
        out = format_report_for_stderr(report)
        assert " SKIP " in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_preflight_runner.py::TestFormatReport -v`
Expected: FAIL with `ImportError: cannot import name 'format_report_for_stderr'`.

- [ ] **Step 3: Add the formatter**

Append to `whatsapp_chat_autoexport/preflight/runner.py`:

```python
# ---------------------------------------------------------------------------
# Stderr formatter
# ---------------------------------------------------------------------------

_STATUS_TOKEN = {
    Status.OK: "OK",
    Status.WARN: "WARN",
    Status.HARD_FAIL: "FAIL",
    Status.SKIPPED: "SKIP",
}

# Match the spec example: column widths matter for greppability.
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
        if r.status == Status.WARN:
            n_warn += 1
        elif r.status == Status.HARD_FAIL:
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
```

Also extend `__all__` in `whatsapp_chat_autoexport/preflight/__init__.py`:

```python
from .runner import (
    DRIVE_HARD_FAIL_BYTES,
    DRIVE_WARN_BYTES,
    ELEVENLABS_HARD_THRESHOLD,
    ELEVENLABS_WARN_THRESHOLD,
    format_report_for_stderr,
    run_preflight,
)

__all__ = [
    "CheckResult",
    "PreflightReport",
    "Status",
    "run_preflight",
    "format_report_for_stderr",
    "DRIVE_HARD_FAIL_BYTES",
    "DRIVE_WARN_BYTES",
    "ELEVENLABS_HARD_THRESHOLD",
    "ELEVENLABS_WARN_THRESHOLD",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/test_preflight_runner.py -v`
Expected: 8 tests PASS (4 from earlier + 4 new).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/preflight/runner.py \
       whatsapp_chat_autoexport/preflight/__init__.py \
       tests/unit/test_preflight_runner.py
git commit -m "feat(preflight): add stderr formatter

Greppable fixed-width layout. Status tokens: OK / WARN / FAIL / SKIP.
On hard fail, the trailing line points at --skip-preflight."
```

---

## Task 8: `--skip-preflight` CLI Flag

**Files:**
- Modify: `whatsapp_chat_autoexport/cli_entry.py:155` (Pipeline options group)
- Test: `tests/unit/test_cli_entry.py` (append a new section)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_cli_entry.py` (or create the test if the file doesn't already cover argparse):

```python
class TestSkipPreflightFlag:
    def test_skip_preflight_default_false(self):
        from whatsapp_chat_autoexport.cli_entry import create_parser

        parser = create_parser()
        args = parser.parse_args(["--headless", "--output", "/tmp/out", "--auto-select"])
        assert args.skip_preflight is False

    def test_skip_preflight_set_true(self):
        from whatsapp_chat_autoexport.cli_entry import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["--headless", "--output", "/tmp/out", "--auto-select", "--skip-preflight"]
        )
        assert args.skip_preflight is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_cli_entry.py::TestSkipPreflightFlag -v`
Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'skip_preflight'`.

- [ ] **Step 3: Add the flag**

Edit `whatsapp_chat_autoexport/cli_entry.py` — find the "Pipeline options"
group (around line 149 in the existing file) and add a new flag immediately
after `--skip-drive-download`:

```python
    pipeline_group.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the credential capacity preflight (default: run)",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_cli_entry.py::TestSkipPreflightFlag -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Verify the help text renders**

Run: `poetry run whatsapp --help | grep skip-preflight`
Expected: shows `--skip-preflight     Skip the credential capacity preflight (default: run)`.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/cli_entry.py tests/unit/test_cli_entry.py
git commit -m "feat(preflight): add --skip-preflight CLI flag

Bypasses the credential preflight gate. Accepted by all modes; only
relevant when the gate would otherwise fire (headless and pipeline-only)."
```

---

## Task 9: Wire Preflight Into `run_headless`

**Files:**
- Modify: `whatsapp_chat_autoexport/headless.py:107-117` (after API-key validation)
- Test: `tests/integration/test_headless_preflight.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_headless_preflight.py`:

```python
"""End-to-end-ish tests for preflight integration in headless modes."""

import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)


def _build_args(**overrides) -> Namespace:
    """Argparse Namespace shaped like the headless path expects."""
    base = dict(
        output="/tmp/preflight-test",
        headless=True,
        pipeline_only=False,
        source=None,
        pipeline_output=None,
        auto_select=True,
        no_transcribe=False,
        transcription_provider="whisper",
        skip_preflight=False,
        debug=False,
        wireless_adb=None,
        skip_appium=True,  # we don't actually want Appium in this test
        resume=None,
        without_media=False,
        no_output_media=False,
        delete_from_drive=False,
        keep_drive_duplicates=False,
        force_transcribe=False,
        skip_opus_conversion=False,
        google_drive_folder=None,
        poll_interval=8,
        poll_timeout=300,
        transcription_language=None,
        limit=None,
    )
    base.update(overrides)
    return Namespace(**base)


@pytest.fixture
def mock_passing_api_key():
    """Skip the API-key validation pre-step."""
    with patch(
        "whatsapp_chat_autoexport.headless._validate_api_key",
        return_value=True,
    ) as m:
        yield m


def _hard_fail_report() -> PreflightReport:
    from datetime import datetime

    return PreflightReport(
        results=[
            CheckResult(
                provider="elevenlabs",
                display_name="ElevenLabs",
                status=Status.HARD_FAIL,
                summary="Quota exhausted",
                error="0 chars left",
            ),
        ],
        started_at=datetime.now(),
        duration_ms=120,
    )


def _ok_report() -> PreflightReport:
    from datetime import datetime

    return PreflightReport(
        results=[
            CheckResult(
                provider="whisper",
                display_name="OpenAI (Whisper)",
                status=Status.OK,
                summary="Key valid",
            )
        ],
        started_at=datetime.now(),
        duration_ms=120,
    )


class TestHeadlessPreflightGate:
    def test_hard_fail_returns_exit_code_2(
        self, mock_passing_api_key, capsys
    ):
        from whatsapp_chat_autoexport.headless import run_headless

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=_hard_fail_report(),
        ):
            exit_code = run_headless(_build_args())

        assert exit_code == 2
        err = capsys.readouterr().err
        assert "[preflight]" in err
        assert "FAIL" in err

    def test_skip_preflight_bypasses_gate(self, mock_passing_api_key):
        from whatsapp_chat_autoexport.headless import run_headless

        # If the gate ran, run_preflight would be called; assert it isn't.
        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight"
        ) as preflight_mock, patch(
            "whatsapp_chat_autoexport.export.appium_manager.AppiumManager"
        ), patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver"
        ) as driver_cls:
            # Force device check to fail so we exit early after the gate
            driver_cls.return_value.check_device_connection.return_value = False

            run_headless(_build_args(skip_preflight=True))

        preflight_mock.assert_not_called()

    def test_warn_does_not_block(self, mock_passing_api_key, capsys):
        """A WARN-only report must not abort; execution continues until
        the next early-exit (no device)."""
        from datetime import datetime

        warn_report = PreflightReport(
            results=[
                CheckResult(
                    provider="elevenlabs",
                    display_name="ElevenLabs",
                    status=Status.WARN,
                    summary="Low quota",
                )
            ],
            started_at=datetime.now(),
            duration_ms=30,
        )

        from whatsapp_chat_autoexport.headless import run_headless

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=warn_report,
        ), patch(
            "whatsapp_chat_autoexport.export.appium_manager.AppiumManager"
        ), patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver"
        ) as driver_cls:
            driver_cls.return_value.check_device_connection.return_value = False

            exit_code = run_headless(_build_args())

        # Device check fails → exit code 2, but the preflight gate didn't
        # cause it. Stderr should still show the warn line.
        err = capsys.readouterr().err
        assert "[preflight]" in err
        assert "WARN" in err
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/integration/test_headless_preflight.py::TestHeadlessPreflightGate -v`
Expected: FAIL — `run_preflight` is not yet patched into `headless.py`.

- [ ] **Step 3: Wire preflight into `run_headless`**

Edit `whatsapp_chat_autoexport/headless.py`:

1. Add an import at the top (after existing imports):

```python
from .preflight import format_report_for_stderr, run_preflight
```

2. Locate the API-key validation block (currently lines 108-117) and insert
the preflight gate **immediately after** it:

```python
    # --- API-key validation -----------------------------------------------
    no_transcribe = getattr(args, "no_transcribe", False)
    if not no_transcribe:
        provider = getattr(args, "transcription_provider", "whisper")
        if not _validate_api_key(provider, logger):
            logger.error(
                "Cannot proceed without a valid API key for transcription. "
                "Set the key or use --no-transcribe to skip."
            )
            logger.close()
            return 2

    # --- Preflight gate ---------------------------------------------------
    if not getattr(args, "skip_preflight", False):
        report = run_preflight()
        print(format_report_for_stderr(report), file=sys.stderr)
        if report.has_hard_fail:
            logger.close()
            return 2
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/integration/test_headless_preflight.py::TestHeadlessPreflightGate -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/headless.py \
       tests/integration/test_headless_preflight.py
git commit -m "feat(preflight): gate run_headless on preflight result

After API-key validation, run_preflight() is called and the formatted
report goes to stderr. has_hard_fail → exit 2. Warnings log but proceed.
--skip-preflight bypasses entirely."
```

---

## Task 10: Wire Preflight Into `run_pipeline_only`

**Files:**
- Modify: `whatsapp_chat_autoexport/headless.py:285-360` (`run_pipeline_only`)
- Modify: `tests/integration/test_headless_preflight.py` (append section)

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_headless_preflight.py`:

```python
class TestPipelineOnlyPreflightGate:
    @pytest.fixture
    def pipeline_args(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        out = tmp_path / "out"
        return Namespace(
            source=str(source),
            pipeline_output=str(out),
            no_transcribe=False,
            force_transcribe=False,
            transcription_provider="whisper",
            no_output_media=False,
            delete_from_drive=False,
            keep_drive_duplicates=False,
            skip_drive_download=False,
            skip_preflight=False,
            limit=None,
            debug=False,
        )

    def test_hard_fail_returns_exit_2(
        self, mock_passing_api_key, pipeline_args, capsys
    ):
        from whatsapp_chat_autoexport.headless import run_pipeline_only

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=_hard_fail_report(),
        ):
            exit_code = run_pipeline_only(pipeline_args)

        assert exit_code == 2
        assert "[preflight]" in capsys.readouterr().err

    def test_skip_drive_download_passes_skip_drive_true(
        self, mock_passing_api_key, pipeline_args
    ):
        from whatsapp_chat_autoexport.headless import run_pipeline_only

        pipeline_args.skip_drive_download = True

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight",
            return_value=_ok_report(),
        ) as preflight_mock, patch(
            "whatsapp_chat_autoexport.headless.WhatsAppPipeline"
        ) as pipeline_cls:
            pipeline_cls.return_value.run.return_value = {"success": True}
            run_pipeline_only(pipeline_args)

        preflight_mock.assert_called_once_with(skip_drive=True)

    def test_skip_preflight_bypasses(self, mock_passing_api_key, pipeline_args):
        from whatsapp_chat_autoexport.headless import run_pipeline_only

        pipeline_args.skip_preflight = True

        with patch(
            "whatsapp_chat_autoexport.headless.run_preflight"
        ) as preflight_mock, patch(
            "whatsapp_chat_autoexport.headless.WhatsAppPipeline"
        ) as pipeline_cls:
            pipeline_cls.return_value.run.return_value = {"success": True}
            run_pipeline_only(pipeline_args)

        preflight_mock.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/integration/test_headless_preflight.py::TestPipelineOnlyPreflightGate -v`
Expected: FAIL — preflight isn't called from `run_pipeline_only` yet.

- [ ] **Step 3: Wire preflight into `run_pipeline_only`**

Edit `whatsapp_chat_autoexport/headless.py` — locate the function, find the
spot **immediately after** the API-key validation but **before** the
`PipelineConfig(...)` construction:

```python
    # Validate API key if transcription is enabled
    no_transcribe = getattr(args, "no_transcribe", False)
    if not no_transcribe:
        provider = getattr(args, "transcription_provider", "whisper")
        if not _validate_api_key(provider, logger):
            return 2

    # --- Preflight gate ---------------------------------------------------
    if not getattr(args, "skip_preflight", False):
        skip_drive = getattr(args, "skip_drive_download", False)
        report = run_preflight(skip_drive=skip_drive)
        print(format_report_for_stderr(report), file=sys.stderr)
        if report.has_hard_fail:
            return 2

    # Build PipelineConfig mirroring pipeline_cli/cli.py
    config = PipelineConfig(
        ...
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/integration/test_headless_preflight.py::TestPipelineOnlyPreflightGate -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Run all integration preflight tests**

Run: `poetry run pytest tests/integration/test_headless_preflight.py -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/headless.py \
       tests/integration/test_headless_preflight.py
git commit -m "feat(preflight): gate run_pipeline_only on preflight

skip_drive=True propagates from --skip-drive-download so the runner
omits the Drive probe entirely (no spurious HARD_FAIL when the user
explicitly opts out of Drive)."
```

---

## Task 11: `PreflightPanel` Textual Widget

**Files:**
- Create: `whatsapp_chat_autoexport/tui/textual_widgets/preflight_panel.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/__init__.py`
- Test: `tests/unit/test_preflight_panel.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_preflight_panel.py`:

```python
"""Tests for the PreflightPanel widget."""

from datetime import datetime

import pytest
from textual.app import App, ComposeResult

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)
from whatsapp_chat_autoexport.tui.textual_widgets.preflight_panel import (
    PreflightPanel,
)


class _PanelHost(App):
    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _report(*specs):
    results = [
        CheckResult(
            provider=p,
            display_name=name,
            status=s,
            summary=summary,
        )
        for p, name, s, summary in specs
    ]
    return PreflightReport(
        results=results,
        started_at=datetime.now(),
        duration_ms=42,
    )


@pytest.mark.asyncio
async def test_initial_render_shows_pending():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        text = panel.render_text()
        assert "Preflight" in text


@pytest.mark.asyncio
async def test_set_report_renders_three_rows():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "Key valid"),
                ("elevenlabs", "ElevenLabs", Status.WARN, "8,420 chars left"),
                ("drive", "Google Drive", Status.HARD_FAIL, "Only 200 MB free"),
            )
        )
        await pilot.pause()
        text = panel.render_text()
        assert "OpenAI (Whisper)" in text
        assert "ElevenLabs" in text
        assert "Google Drive" in text


@pytest.mark.asyncio
async def test_has_hard_fail_property():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "x"),
                ("elevenlabs", "ElevenLabs", Status.HARD_FAIL, "y"),
            )
        )
        assert panel.has_hard_fail is True


@pytest.mark.asyncio
async def test_no_hard_fail_property_initial():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        assert panel.has_hard_fail is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_preflight_panel.py -v`
Expected: FAIL with `ImportError: cannot import name 'PreflightPanel'`.

- [ ] **Step 3: Implement the widget**

Create `whatsapp_chat_autoexport/tui/textual_widgets/preflight_panel.py`:

```python
"""PreflightPanel — read-only Textual widget showing the preflight report.

Lives inside ConnectPane (above the device list). When `set_report()` is
called, renders three labelled rows with status icons. Exposes
`has_hard_fail` so the parent pane can gate the Connected message.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ...preflight.report import PreflightReport, Status

_STATUS_ICON = {
    Status.OK: "[green]✓[/green]",
    Status.WARN: "[yellow]⚠[/yellow]",
    Status.HARD_FAIL: "[red]✗[/red]",
    Status.SKIPPED: "[dim]—[/dim]",
}


class PreflightPanel(Vertical):
    """Read-only view of the preflight report.

    State machine:
        - mounted with no report → "Preflight: not yet run"
        - set_report(report)     → render rows
        - clear()                → back to pending
    """

    DEFAULT_CSS = """
    PreflightPanel {
        height: auto;
        border: solid $accent;
        padding: 0 1;
        margin-bottom: 1;
    }
    PreflightPanel > Static.preflight-row {
        height: 1;
    }
    PreflightPanel > Static#preflight-summary {
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._report: Optional[PreflightReport] = None

    def compose(self) -> ComposeResult:
        yield Static("Preflight: not yet run", id="preflight-summary")

    @property
    def has_hard_fail(self) -> bool:
        return bool(self._report and self._report.has_hard_fail)

    def set_report(self, report: PreflightReport) -> None:
        """Replace contents with rendered rows for the given report."""
        self._report = report
        self.remove_children()

        for r in report.results:
            icon = _STATUS_ICON[r.status]
            self.mount(
                Static(
                    f"{icon} {r.display_name}: {r.summary}",
                    classes="preflight-row",
                )
            )

        n_warn = sum(1 for x in report.results if x.status == Status.WARN)
        n_fail = sum(1 for x in report.results if x.status == Status.HARD_FAIL)
        if n_fail:
            tail = (
                f"[red]{n_fail} hard "
                f"{'failure' if n_fail == 1 else 'failures'}[/red] — fix above to continue."
            )
        else:
            warn_word = "warning" if n_warn == 1 else "warnings"
            tail = f"{n_warn} {warn_word}, ready to continue ({report.duration_ms} ms)"
        self.mount(Static(tail, id="preflight-summary"))

    def clear(self) -> None:
        """Reset the panel to its pre-run state."""
        self._report = None
        self.remove_children()
        self.mount(Static("Preflight: not yet run", id="preflight-summary"))

    def render_text(self) -> str:
        """Return the panel's combined text content (for tests)."""
        return "\n".join(child.renderable.plain for child in self.children
                         if hasattr(child, "renderable") and hasattr(child.renderable, "plain"))
```

- [ ] **Step 4: Re-export from package**

Edit `whatsapp_chat_autoexport/tui/textual_widgets/__init__.py`:

Add `from .preflight_panel import PreflightPanel` and append to `__all__`:

```python
"""Textual widgets for WhatsApp Chat Auto-Export TUI."""

from .activity_log import ActivityLog
from .cancel_modal import CancelModal
from .chat_list import ChatDisplayStatus, ChatListWidget
from .color_scheme_modal import ColorSchemeModal
from .preflight_panel import PreflightPanel
from .progress_display import ProgressDisplay
from .progress_pane import ProgressPane
from .queue_widget import QueueWidget
from .secret_settings_modal import SecretSettingsModal
from .settings_panel import SettingsPanel

__all__ = [
    "ActivityLog",
    "CancelModal",
    "ChatDisplayStatus",
    "ChatListWidget",
    "ColorSchemeModal",
    "PreflightPanel",
    "ProgressDisplay",
    "ProgressPane",
    "QueueWidget",
    "SecretSettingsModal",
    "SettingsPanel",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `poetry run pytest tests/unit/test_preflight_panel.py -v`
Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_widgets/preflight_panel.py \
       whatsapp_chat_autoexport/tui/textual_widgets/__init__.py \
       tests/unit/test_preflight_panel.py
git commit -m "feat(preflight): add PreflightPanel Textual widget

Read-only widget. Renders three rows with status icons (✓/⚠/✗/—) plus
a summary line. has_hard_fail is exposed so the parent pane can gate
the Continue/Connected transition."
```

---

## Task 12: Mount `PreflightPanel` In `ConnectPane`, Gate Connection

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_panes/connect_pane.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_app.py`

- [ ] **Step 1: Inspect the current `ConnectPane` compose**

Run: `grep -n "def compose\|def on_mount\|def action_\|class Connected" /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport/whatsapp_chat_autoexport/tui/textual_panes/connect_pane.py`
Expected: shows roughly where to mount the panel and where the `Connected`
message is fired.

- [ ] **Step 2: Mount the `PreflightPanel` and run preflight on mount**

In `connect_pane.py`:

1. Add imports near the top:

```python
from ..textual_widgets.preflight_panel import PreflightPanel
from ...preflight import run_preflight
```

2. In `compose()`, yield a `PreflightPanel` at the very top of the pane —
this puts it above the device list. Find the existing `compose()` method
and yield `PreflightPanel(id="preflight-panel")` as the first child.

3. In `on_mount()` (or add one if it doesn't exist), kick off a worker that
runs the preflight off the UI thread:

```python
def on_mount(self) -> None:
    """Run preflight in the background and update the panel when done."""
    if not getattr(self.app, "skip_preflight", False):
        self.run_worker(self._run_preflight, thread=True)

def _run_preflight(self) -> None:
    report = run_preflight()
    panel = self.query_one("#preflight-panel", PreflightPanel)
    self.app.call_from_thread(panel.set_report, report)
```

4. In the existing connection-success path (where `self.post_message(self.Connected(...))` is fired), gate the message on the panel's `has_hard_fail`:

```python
panel = self.query_one("#preflight-panel", PreflightPanel)
if panel.has_hard_fail and not getattr(self.app, "skip_preflight", False):
    self._log_to_pane(
        "Cannot continue: preflight has hard failures. "
        "Fix the issues shown above or relaunch with --skip-preflight."
    )
    return
self.post_message(self.Connected(driver=driver))
```

(The exact spot is wherever the existing `Connected` message is posted.
Search for `Connected(driver` to find it.)

5. Add a "Re-run preflight" binding so users can retry without restarting
the app. Append to `BINDINGS`:

```python
Binding("p", "rerun_preflight", "Re-run Preflight", show=True),
```

And the action:

```python
def action_rerun_preflight(self) -> None:
    panel = self.query_one("#preflight-panel", PreflightPanel)
    panel.clear()
    self.run_worker(self._run_preflight, thread=True)
```

- [ ] **Step 3: Plumb `skip_preflight` through the app**

Edit `whatsapp_chat_autoexport/tui/textual_app.py` — find `WhatsAppExporterApp.__init__`. Add a `skip_preflight: bool = False` parameter and store it:

```python
def __init__(
    self,
    ...,
    skip_preflight: bool = False,
    ...,
) -> None:
    super().__init__()
    ...
    self.skip_preflight = skip_preflight
```

Then in `cli_entry.py:run_tui`, pass it through:

```python
app = WhatsAppExporterApp(
    output_dir=output_dir,
    include_media=not args.no_output_media,
    transcribe_audio=not args.no_transcribe,
    delete_from_drive=args.delete_from_drive,
    transcription_provider=args.transcription_provider,
    limit=args.limit,
    debug=args.debug,
    skip_preflight=args.skip_preflight,
)
```

- [ ] **Step 4: Verify nothing else breaks**

Run: `poetry run pytest tests/unit/test_cli_entry.py tests/unit/test_preflight_panel.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_panes/connect_pane.py \
       whatsapp_chat_autoexport/tui/textual_app.py \
       whatsapp_chat_autoexport/cli_entry.py
git commit -m "feat(preflight): mount PreflightPanel in ConnectPane

Preflight runs on mount in a thread worker. Connected message is
suppressed while panel.has_hard_fail (unless app.skip_preflight).
Adds 'p' binding to re-run after fixing keys."
```

---

## Task 13: `ConnectPane` Pilot Integration Test

**Files:**
- Create: `tests/integration/test_connect_pane_preflight.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_connect_pane_preflight.py`:

```python
"""Pilot integration test: ConnectPane mounts PreflightPanel and gates
the Connected message on preflight result."""

from datetime import datetime
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)


def _hard_fail_report() -> PreflightReport:
    return PreflightReport(
        results=[
            CheckResult(
                provider="elevenlabs",
                display_name="ElevenLabs",
                status=Status.HARD_FAIL,
                summary="Quota exhausted",
            )
        ],
        started_at=datetime.now(),
        duration_ms=20,
    )


def _ok_report() -> PreflightReport:
    return PreflightReport(
        results=[
            CheckResult(
                provider="whisper",
                display_name="OpenAI (Whisper)",
                status=Status.OK,
                summary="Key valid",
            )
        ],
        started_at=datetime.now(),
        duration_ms=20,
    )


@pytest.mark.asyncio
async def test_connect_pane_renders_preflight_panel():
    from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp
    from whatsapp_chat_autoexport.tui.textual_widgets.preflight_panel import (
        PreflightPanel,
    )

    with patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight",
        return_value=_ok_report(),
    ):
        app = WhatsAppExporterApp(skip_preflight=False, debug=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()  # let worker settle
            panels = app.screen.query(PreflightPanel)
            assert len(panels) == 1
            panel = panels.first()
            # Either the report has been applied by now, or pending message
            # is still showing. Both are valid; what matters is the panel
            # exists.
            assert panel is not None


@pytest.mark.asyncio
async def test_skip_preflight_suppresses_panel_run():
    from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp

    with patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight"
    ) as preflight_mock:
        app = WhatsAppExporterApp(skip_preflight=True, debug=True)
        async with app.run_test() as pilot:
            await pilot.pause()

    preflight_mock.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `poetry run pytest tests/integration/test_connect_pane_preflight.py -v`
Expected: 2 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_connect_pane_preflight.py
git commit -m "test(preflight): pilot test for ConnectPane integration

Confirms PreflightPanel mounts inside ConnectPane and that
skip_preflight=True suppresses the worker."
```

---

## Task 14: Manual Live Test

**Files:**
- Create: `tests/manual/__init__.py` (empty)
- Create: `tests/manual/test_preflight_live.py`

- [ ] **Step 1: Add the marker file**

Create `tests/manual/__init__.py` (empty file).

- [ ] **Step 2: Write the live test**

Create `tests/manual/test_preflight_live.py`:

```python
"""Manual live-call preflight test.

Skipped by default. Run with:

    poetry run pytest tests/manual/test_preflight_live.py -m requires_api -v

Used periodically by the maintainer to confirm real endpoint shapes still
match parsing — both ElevenLabs and OpenAI have changed schemas before.

Requires:
    OPENAI_API_KEY      (optional but exercised if set)
    ELEVENLABS_API_KEY  (optional but exercised if set)
    Drive credentials   (optional — picks up ~/.whatsapp_export/google_credentials.json)
"""

import os

import pytest

from whatsapp_chat_autoexport.preflight import run_preflight
from whatsapp_chat_autoexport.preflight.report import Status


@pytest.mark.requires_api
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY")
    and not os.environ.get("ELEVENLABS_API_KEY"),
    reason="No transcription API keys configured",
)
def test_live_preflight_returns_a_report():
    """Sanity check: run against real endpoints and expect a sane report.

    This is a smoke test. We don't assert specific status values because
    the maintainer's quota and Drive state are not deterministic. We only
    assert the report is structurally valid so schema drift is caught.
    """
    report = run_preflight()
    assert len(report.results) >= 2  # whisper + elevenlabs at minimum

    for r in report.results:
        assert r.status in {
            Status.OK,
            Status.WARN,
            Status.HARD_FAIL,
            Status.SKIPPED,
        }
        assert r.summary  # non-empty
        assert r.provider in {"whisper", "elevenlabs", "drive"}
```

- [ ] **Step 3: Confirm it stays skipped by default**

Run: `poetry run pytest tests/manual/test_preflight_live.py -v`
Expected: 1 SKIPPED, 0 failed.

- [ ] **Step 4: Optional sanity run for the maintainer**

(Manual — not part of CI.)

```bash
OPENAI_API_KEY=sk-... ELEVENLABS_API_KEY=... \
poetry run pytest tests/manual/test_preflight_live.py -m requires_api -v
```

Expected: PASS, prints something sane to stdout.

- [ ] **Step 5: Commit**

```bash
git add tests/manual/__init__.py tests/manual/test_preflight_live.py
git commit -m "test(preflight): add manual live-call schema-drift test

Skipped by default. Run with -m requires_api to verify real endpoint
shapes still match parsing — schemas drift over time."
```

---

## Task 15: Document `--skip-preflight` In CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (Commands section)

- [ ] **Step 1: Find the flag listing**

Run: `grep -n "skip-drive-download\|All Available Flags" CLAUDE.md`
Expected: shows the line range to edit.

- [ ] **Step 2: Add the flag to the list**

In `CLAUDE.md`, the "All Available Flags" block contains a fenced list. Add
this line (alphabetised in context — directly below `--skip-drive-download`):

```
--skip-preflight          Skip the credential capacity preflight (default: run)
```

- [ ] **Step 3: Add a brief explanation section**

Add a new H2 section directly below the "Drive Duplicate Cleanup" section:

```markdown
## Credential Preflight

Before each export run, the tool checks credential validity and capacity:

- **OpenAI (Whisper)** — key validity via `/v1/models`
- **ElevenLabs** — key + remaining character quota via `/v1/user/subscription`
- **Google Drive** — OAuth token + free storage via `about.get`

Behaviour:

- `OK` (green): proceed
- `WARN` (yellow): proceed; review headroom
- `FAIL` (red): abort with exit code 2
- `SKIP` (grey): no key configured for that provider

In TUI mode, the `PreflightPanel` shows on the Connect tab. Press `p` to
re-run after fixing a key. Continue is disabled while any check is FAIL.

Bypass:

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --skip-preflight
```
```

- [ ] **Step 4: Verify rendering**

Run: `grep -A 5 "Credential Preflight" CLAUDE.md`
Expected: shows the new section.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document --skip-preflight flag and preflight section"
```

---

## Final Verification

After all tasks land, run the full test suite to confirm nothing regressed:

- [ ] **Run full test suite**

Run: `poetry run pytest -v`
Expected: all tests PASS, including the new ~40 preflight tests.

- [ ] **Run only the new preflight tests for a final sanity check**

Run: `poetry run pytest tests/unit/test_preflight_*.py tests/integration/test_headless_preflight.py tests/integration/test_connect_pane_preflight.py -v`
Expected: ~40 tests PASS.

- [ ] **Smoke-test the CLI**

Run: `poetry run whatsapp --headless --output /tmp/preflight-smoke --auto-select`
Expected: stderr shows the `[preflight]` lines. Either proceeds or exits 2 cleanly with the abort message naming `--skip-preflight`.

Run: `poetry run whatsapp --headless --output /tmp/preflight-smoke --auto-select --skip-preflight`
Expected: no `[preflight]` lines, proceeds straight to Appium startup.

- [ ] **Smoke-test the TUI** (manual)

Run: `poetry run whatsapp`
Expected: `PreflightPanel` renders at the top of the Connect tab. Status icons appear within ~5s. `p` re-runs preflight.

---

## Self-Review

**Spec coverage check:**

- ✅ `preflight/` package layout — Task 2, 3, 4, 5, 6
- ✅ `Status`, `CheckResult`, `PreflightReport` — Task 2
- ✅ Whisper probe (`/v1/models`) — Task 3
- ✅ ElevenLabs probe (`/v1/user/subscription`) — Task 4
- ✅ Drive probe (`about.get`) — Task 5
- ✅ Threshold constants — Task 6
- ✅ Probe behaviour matches spec (HARD_FAIL/WARN/OK/SKIPPED logic, summaries)  — Task 3-5
- ✅ Status display tokens (`OK/WARN/FAIL/SKIP`) — Task 7
- ✅ `run_preflight()` synchronous — Task 6
- ✅ `skip_drive` parameter — Task 6
- ✅ `--skip-preflight` flag — Task 8
- ✅ Headless gate (exit 2 on hard fail) — Task 9
- ✅ Pipeline-only gate — Task 10
- ✅ TUI panel mounts on connection screen — Task 11, 12
- ✅ Continue gated on hard fail — Task 12
- ✅ Re-run preflight binding — Task 12
- ✅ Stderr format matches spec example — Task 7
- ✅ Tests for all probes, runner, TUI, both gates — Tasks 2-13
- ✅ Manual live test for schema drift — Task 14
- ✅ httpx explicit dep — Task 1
- ✅ Documentation — Task 15

**Placeholder scan:** None of "TBD", "TODO", "implement later", "Add appropriate error handling", "Similar to Task N", or steps without code. ✓

**Type consistency:** `CheckResult` fields, `Status` enum members, `PreflightReport` properties, `run_preflight(skip_drive=...)` signature, `format_report_for_stderr(report)` signature — all consistent across tasks. `check_whisper(api_key, *, _client=None)`, `check_elevenlabs(api_key, *, _client=None)`, `check_drive(auth)` signatures match between definitions and tests. ✓

**Note on existing API-key validation:** the existing `_validate_api_key` in `headless.py` (line 44) only validates the **active** transcription provider. The preflight gate is additive: it probes whichever keys are configured (via `ApiKeyManager`), so a missing-key path stays under the old validator's responsibility.
