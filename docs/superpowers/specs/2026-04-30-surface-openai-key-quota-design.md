# Design — surface OpenAI key identity & quota in preflight

**Issue:** #25 — *Surface OpenAI key identity and remaining quota in preflight*
**Mode:** `--ship-it` (silent draft)
**Status:** Draft (no human gate in --ship-it)

---

## Problem

The current Whisper preflight probe (`whatsapp_chat_autoexport/preflight/probes/whisper.py`) reports `OpenAI (Whisper): Key valid (quota not introspectable)` after a successful `GET /v1/models` 200. That tells the user almost nothing useful before a run that may burn through OpenAI quota mid-export:

1. They cannot confirm *which* key is loaded (last-4? which account?), so a stale/wrong env var goes unnoticed.
2. They cannot see remaining credit / spend allowance.

This issue asks the probe to surface a key-identity hint and remaining usage if any OpenAI endpoint exposes it — and, where nothing is exposed, to say so explicitly rather than silently.

## Investigation — what OpenAI exposes to a standard `sk-...` key

Endpoints checked (logged to `assets/verification/25/flow.log`):

| Endpoint | Auth | Returns useful? |
|---|---|---|
| `GET /v1/models` | `sk-...` | ✓ key validity, **and** response headers include `OpenAI-Organization` |
| `GET /v1/organization` | dashboard cookie only | ✗ not callable with `sk-...` |
| `GET /v1/usage?start_date=…` | dashboard cookie only | ✗ not callable with `sk-...` |
| `GET /v1/dashboard/billing/credit_grants` | dashboard cookie only | ✗ not callable with `sk-...` |
| `GET /v1/organization/projects/{id}/api_keys/{key_id}` | `sk-admin-...` only | ✗ not callable with project key |

**Conclusion:** there is **no public endpoint** that exposes remaining credit/quota to a standard project key. The probe must be honest about that.

**However:** the `OpenAI-Organization` response header *is* returned on the existing `/v1/models` call. Combined with the last-4 of the API key, that gives the user a verifiable identity hint at zero added latency.

## Definition of done (from the issue, restated)

1. Whisper probe surfaces a **key identity hint** (org-id from response header + last-4 of key).
2. Whisper probe surfaces remaining usage/credit **if any endpoint exposes it**, otherwise prints an explicit `OpenAI does not expose remaining quota` note (not silent).
3. Investigation captured in PR description (which endpoints were tried, which worked).
4. **TUI `PreflightPanel` and headless stderr both render the new info.**
5. Unit tests cover the new probe branches.

## Out of scope

- ElevenLabs and Drive probes — this issue only touches the Whisper probe and its renderers.
- No new dependencies. No async. No retries beyond what `httpx` already does (none).

## Approach

### Probe behaviour change

`check_whisper(api_key)` continues to call `GET /v1/models` once. New work in the 200-OK branch:

1. Read the `OpenAI-Organization` response header (case-insensitive). May be absent on personal-tier keys — in that case record `org_id = None`.
2. Compute `key_last4 = api_key[-4:]` (or `api_key[-4:]` masked as `****<last4>`). Never log the full key.
3. Build a summary string that reads like:

   ```
   Key …<last4> · org <org-id-or-"unknown"> · quota not exposed by OpenAI
   ```

   When `org_id` is None:

   ```
   Key …<last4> · org not in response · quota not exposed by OpenAI
   ```

4. Add to `result.details`:
   - `key_last4` — last 4 chars of the key
   - `organization_id` — org id from header, or `None`
   - `quota_introspected` — `False` (constant; future-proofs the field if OpenAI ever ships an endpoint)
   - existing fields (`key_valid`, `models_endpoint_ok`) preserved

5. Status remains `Status.OK` in the success branch — identity is informational, not a gate.

### Renderer changes

- **Headless stderr** (`runner.format_report_for_stderr`): no logic change required. The existing layout already prints `r.summary`, so the longer string flows through as-is. Verify the `_NAME_WIDTH` / column wrap still looks right; widen if needed.
- **TUI `PreflightPanel`** (`tui/textual_widgets/preflight_panel.py`): no logic change required. `set_report` already emits one row per `r.summary`. Verify the row's `height: 1` CSS doesn't truncate the longer string at typical TUI widths; if it does, allow `height: auto` for the row only when the text would clip — but prefer keeping the summary terse enough to fit a 60-col panel.

The renderers are passive; the change is in the data model.

### Error branches — unchanged

- 401 → HARD_FAIL "Invalid key" (existing).
- 5xx → HARD_FAIL `Unexpected response (...)` (existing).
- Network error → HARD_FAIL "Could not reach OpenAI" (existing).
- No key → SKIPPED (existing).

In the HARD_FAIL branches we do **not** add a key-last4 hint to the summary — those are already noisy enough and the user's first action is to fix the key, not identify it.

## Tests

Extend `tests/unit/test_preflight_probes.py::TestWhisperProbe`:

1. `test_valid_key_with_org_header` — `OpenAI-Organization: org-abc123` in mock response → summary contains `…test`, `org-abc123`, and `quota not exposed`. `details["organization_id"] == "org-abc123"`, `details["key_last4"] == "test"`, `details["quota_introspected"] is False`.
2. `test_valid_key_without_org_header` — no header → summary contains `org not in response`, `details["organization_id"] is None`.
3. `test_key_last4_redaction` — assert `result.summary` does **not** contain the full key (only `…<last4>`). Defensive check against accidental log-leak.
4. Existing `test_valid_key_ok` updated: it should still pass — summary contains "Key valid"-style language **or** the new format. We update the assertion to match the new contract (`"Key …" in result.summary` and `"quota" in result.summary.lower()`).
5. Existing 401/5xx/network error tests stay as-is.

`tests/unit/test_preflight_panel.py`: smoke-test that a `CheckResult` with the new longer summary renders without raising. No behavioural assertion — that file already has a render-text helper.

`tests/integration/test_headless_preflight.py`: confirm the new summary string appears in stderr for the OK branch.

## Risk / unknowns

- **Header case sensitivity:** `httpx.Response.headers` is case-insensitive, so `response.headers.get("openai-organization")` is safe.
- **Old keys without org:** confirmed — some legacy keys return no `OpenAI-Organization` header. Probe must not crash; render `org not in response`.
- **Future OpenAI usage endpoint:** if OpenAI ever ships per-key quota introspection, the `quota_introspected` flag and the structure of `details` are in place to extend without breaking renderers.

## Non-goals

- No retry logic, no parallel calls, no caching. Single GET, sub-second.
- No env-var sniffing beyond what `api_key_manager` already does. The probe only sees the key the manager hands it.
- No persisting org-id across runs. It's surfaced fresh each preflight.
