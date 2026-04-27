# API Credential Preflight — Design Spec

**Date:** 2026-04-27
**Status:** Approved (pending implementation plan)
**Owner:** AJ Anderson

## Purpose

Catch credential, quota, and storage problems **before** a long export run starts, so users don't lose 20+ minutes mid-run to a 401, an exhausted ElevenLabs character budget, or a full Google Drive.

The preflight is a **credential + capacity readout**, not a forecaster. It reports current allowances; the user judges whether the headroom is enough for their planned run.

## Scope

**In scope:**
- OpenAI (Whisper) API key — validity check via `/v1/models` (OpenAI exposes no quota endpoint).
- ElevenLabs API key — validity + character quota + reset time + tier via `/v1/user/subscription`.
- Google Drive — OAuth token validity + storage quota via `about.get(fields=storageQuota,user)`.

**Out of scope:**
- Workload estimation against quota (no pre-scanning device file counts; not adding ffprobe duration sums).
- Appium / ADB / WhatsApp device readiness (already handled by `verify_whatsapp_is_open()`).
- Standalone `whatsapp preflight` subcommand (auto-run + TUI panel + opt-out only).
- Per-provider threshold customisation through Settings (constants only, revisit if users ask).

## Architecture

### File layout

```
whatsapp_chat_autoexport/
└── preflight/
    ├── __init__.py            # exports run_preflight, PreflightReport, Status
    ├── report.py              # CheckResult, PreflightReport, Status enum
    ├── runner.py              # run_preflight(settings) → PreflightReport, threshold constants
    └── probes/
        ├── __init__.py
        ├── whisper.py         # check_whisper(api_key) → CheckResult
        ├── elevenlabs.py      # check_elevenlabs(api_key) → CheckResult
        └── drive.py           # check_drive(auth) → CheckResult
```

### Boundaries

- `preflight` depends on `config.api_key_manager`, `google_drive.auth`. **No reverse dependencies.**
- Probes never raise. They catch HTTP/auth errors and return a `CheckResult` with `Status.HARD_FAIL`. The orchestrator never handles exceptions from probes.
- The runner is **synchronous**. Three providers, three short HTTP calls, ~2–5 seconds total. No async complexity needed.

### Consumers

| Consumer | Behaviour |
|---|---|
| `headless.py` (`run_headless`) | Calls `run_preflight()` after API-key validation, prints report to stderr, exits 2 on hard fail. |
| `headless.py` (`run_pipeline_only`) | Same gate. Skips Drive probe if `--skip-drive-download`. |
| `cli_entry.py` | Adds `--skip-preflight` flag to bypass the gate in either headless mode. |
| `tui/textual_screens/discovery_screen.py` | Mounts a new `PreflightPanel` widget; disables "Continue" until hard failures resolved. |
| API-key settings widget (existing) | Gains a "Re-run preflight" button. |

## Data Model

```python
# preflight/report.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class Status(str, Enum):
    OK = "ok"              # green: usable, headroom available (or unknowable but valid)
    WARN = "warn"          # yellow: usable now, but low headroom or near a limit
    HARD_FAIL = "hard_fail"  # red: cannot proceed
    SKIPPED = "skipped"    # grey: not configured, not in use this run

@dataclass
class CheckResult:
    provider: str                        # "whisper" | "elevenlabs" | "drive"
    display_name: str                    # "OpenAI (Whisper)" etc.
    status: Status
    summary: str                         # one-line for stderr/TUI
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

### Per-provider `details` shapes

| Provider | `details` keys |
|---|---|
| `whisper` | `key_valid: bool`, `models_endpoint_ok: bool` |
| `elevenlabs` | `character_count`, `character_limit`, `characters_remaining`, `next_reset_unix`, `tier`, `can_extend_character_limit` |
| `drive` | `token_valid`, `storage_used_bytes`, `storage_limit_bytes` (None for pooled), `storage_free_bytes` |

### Status thresholds (named constants in `runner.py`)

| Constant | Value | Meaning |
|---|---|---|
| `ELEVENLABS_WARN_THRESHOLD` | `50_000` chars | Below this → WARN |
| `ELEVENLABS_HARD_THRESHOLD` | `0` chars | At/below this → HARD_FAIL |
| `DRIVE_WARN_BYTES` | `5 * 1024**3` (5 GB) | Below this → WARN |
| `DRIVE_HARD_FAIL_BYTES` | `500 * 1024**2` (500 MB) | Below this → HARD_FAIL |

Whisper has no quota visibility → only `OK` (key works) / `HARD_FAIL` (key invalid). No WARN possible.

A provider whose key isn't loaded → `Status.SKIPPED`. SKIPPED never blocks. (If the user picks `--transcription-provider elevenlabs` but only OpenAI key is set, that's caught by existing API-key validation upstream — not a preflight responsibility.)

## Probe Behaviour

### Whisper (`probes/whisper.py`)

- `GET https://api.openai.com/v1/models` with `Authorization: Bearer <key>`, 10 s timeout.
- 200 → `Status.OK`, summary `"Key valid (quota not introspectable)"`.
- 401 → `Status.HARD_FAIL`, error `"Invalid OpenAI API key"`.
- Any `httpx.HTTPError` (timeout, connection refused, 5xx) → `Status.HARD_FAIL` with the exception message.
- No key → `Status.SKIPPED`.

### ElevenLabs (`probes/elevenlabs.py`)

- `GET https://api.elevenlabs.io/v1/user/subscription` with `xi-api-key: <key>`, 10 s timeout.
- 401 → `Status.HARD_FAIL`.
- 200: parse `character_count`, `character_limit`, `next_character_count_reset_unix`, `tier`.
  - `remaining = limit - used`
  - `remaining <= 0` → `HARD_FAIL` (`"Quota exhausted (used/limit chars)"`)
  - `remaining < 50_000` → `WARN` (`"<remaining> chars left (<tier>), resets <date>"`)
  - else → `OK` (`"<remaining>/<limit> chars left (<tier>)"`)
- Any `httpx.HTTPError` → `Status.HARD_FAIL`.
- No key → `Status.SKIPPED`.

### Drive (`probes/drive.py`)

- Reuses existing `GoogleDriveAuth` (no duplicate auth flow).
- `auth=None` or `not auth.has_credentials()` → `Status.HARD_FAIL`.
- `service.about().get(fields="storageQuota,user").execute()`:
  - `RefreshError` → `Status.HARD_FAIL` (`"OAuth token expired/revoked"`).
  - `HttpError` → `Status.HARD_FAIL`.
  - 200: parse `storageQuota.usage` and `storageQuota.limit`.
    - `limit is None` (Workspace pooled) → `OK`, no warning logic, summary `"Authenticated (storage limit not reported)"`.
    - `free < 500 MB` → `HARD_FAIL` (`"Only <free> free"`).
    - `free < 5 GB` → `WARN` (`"<free> free (low)"`).
    - else → `OK` (`"<free> free of <limit>"`).

### Runner (`runner.py`)

```python
def run_preflight(settings: Settings) -> PreflightReport:
    started = datetime.now()
    km = get_api_key_manager()
    auth = _build_drive_auth(settings)  # same construction headless.py uses

    results = [
        check_whisper(km.get_api_key("whisper")),
        check_elevenlabs(km.get_api_key("elevenlabs")),
        check_drive(auth),
    ]
    duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    return PreflightReport(results=results, started_at=started, duration_ms=duration_ms)
```

For `run_pipeline_only` with `--skip-drive-download`, the runner has a `skip_drive: bool` parameter that omits the Drive probe.

## Integration

### CLI flag

```
--skip-preflight    Skip the credential capacity preflight (default: run)
```

No new subcommand. No `--preflight` flag. The check runs implicitly before any export.

### Headless mode

```python
def run_headless(args) -> int:
    # ... existing API-key validation ...

    if not args.skip_preflight:
        report = run_preflight(settings)
        _log_preflight_to_stderr(report)
        if report.has_hard_fail:
            return 2  # fatal error
        # warnings logged but execution continues

    # ... existing AppiumManager → WhatsAppDriver → ChatExporter → Pipeline ...
```

### Stderr output format

Greppable, fixed-width status column, one line per provider. The internal `Status` enum values map to display tokens as: `OK → "OK"`, `WARN → "WARN"`, `HARD_FAIL → "FAIL"`, `SKIPPED → "SKIP"`.

```
[preflight] OpenAI (Whisper)    OK     Key valid (quota not introspectable)
[preflight] ElevenLabs          WARN   8,420 chars left (creator), resets 2026-05-01
[preflight] Google Drive        OK     12.4 GB free of 15.0 GB
[preflight] 1 warning, 0 hard failures — proceeding (370 ms)
```

On hard fail:

```
[preflight] ElevenLabs          FAIL   Quota exhausted (100,000/100,000 chars used)
[preflight] Aborting: 1 hard failure. Use --skip-preflight to bypass.
```

### TUI mode

- New `PreflightPanel` widget under `tui/textual_widgets/`.
- Mounts on `DiscoveryScreen` after the credentials section, before "Continue".
- Renders three rows with status icons (✓ / ⚠ / ✗ / —) and the summary text.
- Clicking a failed row opens an actionable hint (e.g. "Set `ELEVENLABS_API_KEY` in `.env`", "Re-run Drive auth").
- "Continue" button is disabled while any row is `HARD_FAIL`, unless the app was launched with `--skip-preflight`.
- Existing API-key settings widget gains a "Re-run preflight" button that re-renders the panel.

## Edge Cases

| Case | Behaviour |
|---|---|
| Network down (any probe) | All probes return `HARD_FAIL` with reachability error. Without `--skip-preflight`, run aborts. (A network-down WhatsApp export wouldn't get far anyway.) |
| `--no-transcribe` set, both transcription keys missing | Both rows → `SKIPPED`. Drive is the only thing that matters. Run proceeds if Drive is OK. |
| `--skip-drive-download` (pipeline-only) | Runner omits the Drive probe. |
| `--auto-select` headless with no `--skip-preflight`, no TTY | Never prompts. Exits 2 on hard fail. (No interactive fallback — that's the TUI's job.) |
| User picks `--transcription-provider X` but key X missing | Caught by existing API-key validation upstream, before preflight runs. Not a preflight responsibility. |
| Drive Workspace account with pooled storage | `limit is None` → `OK` with summary `"Authenticated (storage limit not reported)"`. Never warns. |

## Testing

### Unit tests — `tests/unit/test_preflight.py`

All probes mocked at the HTTP layer (`respx` if already a dep, else `httpx.MockTransport`).

| Test | Verifies |
|---|---|
| `test_whisper_no_key_skipped` | `check_whisper(None)` → `Status.SKIPPED` |
| `test_whisper_valid_key_ok` | 200 from `/v1/models` → `Status.OK` |
| `test_whisper_invalid_key_hard_fail` | 401 → `Status.HARD_FAIL`, error includes "Invalid OpenAI API key" |
| `test_whisper_network_error_hard_fail` | `httpx.ConnectError` → `Status.HARD_FAIL` |
| `test_elevenlabs_full_quota_ok` | high `characters_remaining` → OK |
| `test_elevenlabs_low_quota_warn` | remaining below threshold → WARN |
| `test_elevenlabs_exhausted_hard_fail` | remaining=0 → HARD_FAIL |
| `test_elevenlabs_invalid_key` | 401 → HARD_FAIL |
| `test_elevenlabs_network_error` | `httpx.HTTPError` → HARD_FAIL |
| `test_drive_no_auth_hard_fail` | `auth=None` → HARD_FAIL |
| `test_drive_token_expired` | `RefreshError` → HARD_FAIL |
| `test_drive_low_storage_warn` | `< 5 GB free` → WARN |
| `test_drive_exhausted_hard_fail` | `< 500 MB free` → HARD_FAIL |
| `test_drive_pooled_no_limit_ok` | `limit is None` → OK |
| `test_runner_aggregates_results` | `run_preflight()` returns a `PreflightReport` with all three probe results |
| `test_runner_skip_drive_omits_probe` | `skip_drive=True` → Drive row absent |
| `test_report_has_hard_fail` / `has_warning` | aggregate properties |

### Integration tests

- `tests/integration/test_headless_preflight.py` — `run_headless()` with mocked probes returning HARD_FAIL → asserts exit code 2 and stderr contains `[preflight]` lines.
- `tests/integration/test_textual_preflight.py` — Textual pilot test that `DiscoveryScreen` renders `PreflightPanel` with the right statuses and disables "Continue" on hard fail.

### Live-call test (manual)

`tests/manual/test_preflight_live.py`, marked `@pytest.mark.requires_api`, **skipped by default**. Maintainer runs occasionally to confirm real endpoint shapes still match parsing — important because both ElevenLabs and OpenAI have changed schemas before.

### Test fixtures

- `mock_elevenlabs_subscription_response` — JSON file with the realistic shape, parameterised so individual tests override `character_count` etc.
- `mock_drive_about_response` — same idea for Drive `about.get`.
- Reuses existing `mock_api_key` fixture from `conftest.py`.

## Dependencies

- `httpx` — already a transitive dep via OpenAI/ElevenLabs SDKs. Added explicitly to `pyproject.toml` since we use it directly.
- Probes use **raw HTTP endpoints**, not SDK clients. Reason: SDKs don't expose subscription/quota endpoints uniformly, and a raw GET is shorter and more honest about what we're doing.

## Open Questions / Future Work

- **Threshold tuning.** Initial values are heuristics. If users report false WARNs or missed FAILs, expose them in `Settings`.
- **Cost estimate column.** Future enhancement: pair with a workload pre-scan to print "estimated cost: $0.42" alongside the quota readout.
- **Rate-limit headers.** OpenAI returns `x-ratelimit-remaining-requests` headers on real calls; could surface those mid-run as live capacity rather than only at preflight.
