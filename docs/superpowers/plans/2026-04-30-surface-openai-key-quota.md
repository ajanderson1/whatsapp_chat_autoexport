# Surface OpenAI key identity & quota in preflight — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Whisper preflight probe useful by surfacing a key-identity hint (last-4 of key + OpenAI organization id) and an explicit "OpenAI does not expose remaining quota" note, instead of the unhelpful current `Key valid (quota not introspectable)` line.

**Architecture:** Single-file behaviour change in `whatsapp_chat_autoexport/preflight/probes/whisper.py` — capture the `OpenAI-Organization` header from the existing `GET /v1/models` response, build a richer summary string, expand `details`. Renderers (`runner.format_report_for_stderr`, `tui/textual_widgets/preflight_panel.py`) are passive — they print whatever `summary` contains, so no logic change there. Tests added to `tests/unit/test_preflight_probes.py` and one assertion update in `tests/integration/test_headless_preflight.py`.

**Tech Stack:** Python 3.13, `httpx` (already a dep), `pytest` with `httpx.MockTransport`.

---

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `whatsapp_chat_autoexport/preflight/probes/whisper.py` | modify | Probe logic — read header, build summary, expand details |
| `tests/unit/test_preflight_probes.py` | modify | Unit tests — add 3 new tests, update 1 existing |
| `tests/integration/test_headless_preflight.py` | modify | Update OK-branch assertion if it inspects the whisper summary string |

No new files. No new modules. No renderer changes.

---

## Task 1: Add failing test — header captured into details

**Files:**
- Test: `tests/unit/test_preflight_probes.py:26-83` (extend `class TestWhisperProbe`)

- [ ] **Step 1: Append new test to `TestWhisperProbe`**

```python
def test_valid_key_with_org_header(self):
    """When OpenAI-Organization header is present, capture org id + last-4 of key."""
    from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": []},
            headers={"OpenAI-Organization": "org-abc123"},
        )

    result = check_whisper(
        "sk-test-key-1234",
        _client=httpx.Client(transport=_mock_transport(handler)),
    )
    assert result.status == Status.OK
    assert result.details["organization_id"] == "org-abc123"
    assert result.details["key_last4"] == "1234"
    assert result.details["quota_introspected"] is False
    # Identity surfaced in the user-visible summary
    assert "1234" in result.summary
    assert "org-abc123" in result.summary
    assert "quota" in result.summary.lower()
```

- [ ] **Step 2: Run the new test — verify it fails for the right reason**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe::test_valid_key_with_org_header -v`
Expected: FAIL — `KeyError: 'organization_id'` (or similar — `details` dict has no such key yet).

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_preflight_probes.py
git commit -m "test(preflight): whisper probe captures OpenAI-Organization header (failing)"
```

---

## Task 2: Implement header capture + new summary

**Files:**
- Modify: `whatsapp_chat_autoexport/preflight/probes/whisper.py:61-68` (the 200-OK branch)

- [ ] **Step 1: Replace the 200-OK return block**

Old code (lines 61-68 of the current file):

```python
if response.status_code == 200:
    return CheckResult(
        provider="whisper",
        display_name=_DISPLAY,
        status=Status.OK,
        summary="Key valid (quota not introspectable)",
        details={"key_valid": True, "models_endpoint_ok": True},
    )
```

Replace with:

```python
if response.status_code == 200:
    org_id = response.headers.get("openai-organization")
    key_last4 = api_key[-4:] if len(api_key) >= 4 else api_key
    org_part = f"org {org_id}" if org_id else "org not in response"
    summary = f"Key …{key_last4} · {org_part} · quota not exposed by OpenAI"
    return CheckResult(
        provider="whisper",
        display_name=_DISPLAY,
        status=Status.OK,
        summary=summary,
        details={
            "key_valid": True,
            "models_endpoint_ok": True,
            "key_last4": key_last4,
            "organization_id": org_id,
            "quota_introspected": False,
        },
    )
```

- [ ] **Step 2: Run the test — verify it now passes**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe::test_valid_key_with_org_header -v`
Expected: PASS.

- [ ] **Step 3: Commit the implementation**

```bash
git add whatsapp_chat_autoexport/preflight/probes/whisper.py
git commit -m "feat(preflight): whisper probe surfaces key …last4 + OpenAI org id

OpenAI exposes no public quota endpoint to a standard sk- key. The probe
now captures the OpenAI-Organization response header (returned by
/v1/models) and the last-4 of the API key, so users can verify the right
key is loaded before a run. Summary string explicitly states 'quota not
exposed by OpenAI' rather than the silent 'quota not introspectable'.

Closes #25 (one-of-three commits)."
```

---

## Task 3: Add failing test — missing header (legacy keys)

**Files:**
- Test: `tests/unit/test_preflight_probes.py` (extend `TestWhisperProbe`)

- [ ] **Step 1: Append the test**

```python
def test_valid_key_without_org_header(self):
    """Legacy / personal keys may not return OpenAI-Organization — render gracefully."""
    from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})  # no header

    result = check_whisper(
        "sk-old-style-key-9999",
        _client=httpx.Client(transport=_mock_transport(handler)),
    )
    assert result.status == Status.OK
    assert result.details["organization_id"] is None
    assert result.details["key_last4"] == "9999"
    assert "9999" in result.summary
    assert "org not in response" in result.summary
```

- [ ] **Step 2: Run the test — should already pass**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe::test_valid_key_without_org_header -v`
Expected: PASS (Task 2's implementation already handles `org_id is None`).

This is a **belt-and-braces test** — it locks the behaviour in so a future refactor doesn't regress the missing-header path.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_preflight_probes.py
git commit -m "test(preflight): whisper handles missing OpenAI-Organization header"
```

---

## Task 4: Add failing test — never leak the full key

**Files:**
- Test: `tests/unit/test_preflight_probes.py` (extend `TestWhisperProbe`)

- [ ] **Step 1: Append the test**

```python
def test_full_key_never_leaks_into_summary(self):
    """Defensive: only the last 4 chars of the key may appear in summary."""
    from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

    full_key = "sk-secret-AAAAAAAAAAAAAAAAAAAA-LAST"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": []},
            headers={"OpenAI-Organization": "org-x"},
        )

    result = check_whisper(
        full_key,
        _client=httpx.Client(transport=_mock_transport(handler)),
    )
    # The full key must not appear anywhere in summary or stringified details.
    assert full_key not in result.summary
    assert full_key not in str(result.details)
    # Last-4 is fine.
    assert "LAST" in result.summary
```

- [ ] **Step 2: Run the test — should pass**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe::test_full_key_never_leaks_into_summary -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_preflight_probes.py
git commit -m "test(preflight): whisper never logs full API key, only last 4"
```

---

## Task 5: Update existing `test_valid_key_ok` assertion

**Files:**
- Modify: `tests/unit/test_preflight_probes.py:41-53` (existing `test_valid_key_ok`)

The existing test asserts `"Key valid" in result.summary` — that string is gone. Update it to match the new contract.

- [ ] **Step 1: Edit the assertion**

Find:

```python
assert result.status == Status.OK
assert "Key valid" in result.summary
assert result.details["key_valid"] is True
assert result.details["models_endpoint_ok"] is True
```

Replace with:

```python
assert result.status == Status.OK
# New summary format: "Key …<last4> · org … · quota not exposed by OpenAI"
assert "Key …" in result.summary
assert "quota" in result.summary.lower()
assert result.details["key_valid"] is True
assert result.details["models_endpoint_ok"] is True
```

The existing handler in this test does **not** set the `OpenAI-Organization` header — that's fine, the assertion only checks the universal parts of the summary. The header-present and header-absent cases are covered by Tasks 1 and 3.

- [ ] **Step 2: Run the full whisper test class — all should pass**

Run: `poetry run pytest tests/unit/test_preflight_probes.py::TestWhisperProbe -v`
Expected: 8 passed (5 original + 3 new).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_preflight_probes.py
git commit -m "test(preflight): align test_valid_key_ok with new summary format"
```

---

## Task 6: Update integration assertion in headless preflight test

**Files:**
- Modify: `tests/integration/test_headless_preflight.py` (the OK report builder, around line 76+)

The integration test builds an `_ok_report()` with hard-coded `summary="Key valid"` style strings. We don't need to mutate this — the integration test is checking *exit code* and *stderr emission*, not the summary contents. **But** verify by reading the file: if any assertion inspects `"Key valid"` in stderr, it must be updated.

- [ ] **Step 1: Inspect assertions**

Run: `grep -n 'Key valid\|quota' tests/integration/test_headless_preflight.py`

If matches refer to the **builder's `summary=`** field (a fixture detail, not under test), leave them. If any **assertion** checks `"Key valid" in captured.err` or similar, update to `"Key …" in captured.err` instead.

- [ ] **Step 2: Apply edits as needed (or skip if no assertion impacted)**

If grep shows assertion-side hits, change them to look for substrings that survive both old and new formats. The safest assertion is:

```python
assert "OpenAI (Whisper)" in captured.err  # the display name still appears
```

If grep shows only fixture builder hits, no change needed — fixtures define the world the test inhabits.

- [ ] **Step 3: Run the integration test**

Run: `poetry run pytest tests/integration/test_headless_preflight.py -v`
Expected: PASS.

- [ ] **Step 4: Commit if changes were made; otherwise skip**

```bash
# Only if Step 2 made changes:
git add tests/integration/test_headless_preflight.py
git commit -m "test(preflight): align headless integration with new whisper summary"
```

---

## Task 7: Run the full preflight test suite + the broader unit suite

This is a regression check — ensure nothing else (panel, runner, format_report_for_stderr) trips on the longer summary.

- [ ] **Step 1: Run preflight-related tests**

Run: `poetry run pytest tests/unit/test_preflight_probes.py tests/unit/test_preflight_panel.py tests/unit/test_preflight_runner.py tests/unit/test_preflight_report.py tests/integration/test_headless_preflight.py -v`
Expected: all pass.

- [ ] **Step 2: Run the full unit suite**

Run: `poetry run pytest tests/unit -q`
Expected: all pass (issue 25 changes are isolated; nothing else should regress).

- [ ] **Step 3: Run linter**

Run: `poetry run ruff check whatsapp_chat_autoexport/preflight/probes/whisper.py tests/unit/test_preflight_probes.py`
Expected: no errors.

If anything fails: fix in place, re-run, then commit the fix as `fix(preflight): …`.

- [ ] **Step 4: No commit needed if everything is green** (verification only).

---

## Task 8: Manual visual smoke — confirm renderers display the new line

This is verification, not a code change. It satisfies the issue's "TUI `PreflightPanel` + headless stderr both render the new info" requirement empirically.

- [ ] **Step 1: Headless dry render via the existing format_report_for_stderr helper**

```bash
poetry run python -c "
from datetime import datetime
from whatsapp_chat_autoexport.preflight.report import CheckResult, PreflightReport, Status
from whatsapp_chat_autoexport.preflight.runner import format_report_for_stderr

r = PreflightReport(
    results=[CheckResult(
        provider='whisper',
        display_name='OpenAI (Whisper)',
        status=Status.OK,
        summary='Key …1234 · org org-abc123 · quota not exposed by OpenAI',
        details={'key_last4': '1234', 'organization_id': 'org-abc123'},
    )],
    started_at=datetime.now(),
    duration_ms=120,
)
print(format_report_for_stderr(r))
"
```

Expected output (column-aligned):

```
[preflight] OpenAI (Whisper)     OK     Key …1234 · org org-abc123 · quota not exposed by OpenAI
[preflight] 0 warnings, 0 hard failures — proceeding (120 ms)
```

- [ ] **Step 2: Save the output to the verification artifacts dir**

```bash
poetry run python -c "..." > assets/verification/25/headless-render-sample.txt 2>&1
```

(Use the same one-liner as Step 1, redirected to the file.)

- [ ] **Step 3: TUI panel rendering — covered by `tests/unit/test_preflight_panel.py`**

The existing `test_set_report_renders_three_rows` test already exercises `set_report` → row rendering. Since we did not change `PreflightPanel`, the regression check in Task 7 covers TUI rendering.

If the user wants a live screenshot they can run `poetry run whatsapp` — but that's a manual/optional check, not a gating step for the PR.

- [ ] **Step 4: No commit needed** — artifacts dir is in `.gitignore` already (per `flow.md` Step 9).

---

## Self-review

**Spec coverage:**
- ✓ Identity hint surfaced (Task 2: org id + last-4)
- ✓ Explicit "quota not exposed" note (Task 2: hard-coded into summary)
- ✓ Investigation captured (already in `flow.log` and the spec; PR body will reference)
- ✓ TUI + headless render (Tasks 7 + 8: regression-tested + visually confirmed)
- ✓ Unit tests cover new branches (Tasks 1, 3, 4 — three new tests)

**Placeholder scan:** none — every step has runnable code or commands.

**Type consistency:** `details` keys (`key_last4`, `organization_id`, `quota_introspected`) appear identically across Tasks 1, 2, and 4. `summary` formatting (`Key …<last4>`) appears identically across Tasks 1, 2, 3, 4.

**Nothing skipped from spec.**
