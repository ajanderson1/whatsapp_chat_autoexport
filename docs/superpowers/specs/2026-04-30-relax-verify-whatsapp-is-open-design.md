# Spec — Relax `verify_whatsapp_is_open()` for WhatsApp 2.26 Material 3

- **Issue:** [#27](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/27) — `fix: relax verify_whatsapp_is_open for WhatsApp 2.26 Material 3 redesign`
- **Status:** Approved (guided brainstorm, 2026-04-30)
- **Date:** 2026-04-30
- **Author:** AJ Anderson via aj-flow

## Problem

`verify_whatsapp_is_open()` in `whatsapp_chat_autoexport/export/whatsapp_driver.py:1211-1349` returns `False` on WhatsApp 2.26.15.76 (Material 3 redesign) because Check 3 (lines 1272-1329) probes four hardcoded legacy resource IDs that no longer exist in the redesigned view hierarchy:

- `com.whatsapp:id/conversations_row_contact_name`
- `com.whatsapp:id/toolbar`
- `com.whatsapp:id/action_bar`
- `com.whatsapp:id/menuitem_search`

When all four come back empty, Check 3 hard-fails — even though Check 1 (current package == `com.whatsapp`) and Check 2 (current activity not in unsafe list) have already proven WhatsApp is foregrounded and safe.

**Real-world impact:** an autonomous full-export run against 874 chats aborted after 1 successful chat (transient cached fragment matched a legacy ID once). Every subsequent chat hit `WhatsApp verification failed`, and `_attempt_session_recovery()` re-invoked the same broken verifier on every retry, poisoning the entire batch.

Full diagnosis: `docs/solutions/integration-issues/whatsapp-material3-resource-id-allowlist-2026-04-30.md`.

## Goals

1. `verify_whatsapp_is_open()` returns `True` on WhatsApp 2.26.15.76 (Material 3) when WhatsApp is foregrounded and unlocked.
2. `verify_whatsapp_is_open()` continues to return `False` when the wrong package is foreground or the activity is unsafe (lock screen, system UI, settings).
3. A future verifier regression cannot poison more than 3 chats in a batch run before the orchestrator halts.

## Non-goals

- Updating `create_default_selectors()` in `config/selectors.py` for `export_chat_option`, `chat_list_item`, `toolbar`, or `menu_button`. Those need real Appium Inspector dumps against 2.26.x to confirm new IDs and belong in a follow-up issue with device-verification artifacts.
- Adding versioned per-build YAML selectors under `config/selectors/whatsapp_2.26.yaml`. YAGNI for one build; revisit when a second build forces selector divergence.
- Selector-drift CI smoke tests, monthly release-monitoring agents, or the broader Prevention list from the diagnosis doc.
- Changes to `export_pane.py:563` — that call site is per-chat in the TUI and does not own a batch loop. Verifier-relaxation alone fixes the cascade there.
- Changes to legacy code paths (`legacy/cli/commands/export.py`, `legacy/textual_screens/export_screen.py`, `whatsapp_export.py`).

## Design

### Change 1 — Delete Check 3 from `verify_whatsapp_is_open()`

**File:** `whatsapp_chat_autoexport/export/whatsapp_driver.py`
**Lines affected:** 1272-1329 (Check 3 block) — deleted in full.

Checks 1 and 2 already prove WhatsApp is foregrounded:

- **Check 1** (lines 1225-1250): asserts `current_package == "com.whatsapp"`, hard-fails otherwise.
- **Check 2** (lines 1252-1270): asserts current activity is not in `["Keyguard", "LockScreen", "lockscreen", "StatusBar", "systemui", "Settings"]`, hard-fails otherwise.

Check 3 was belt-and-braces — meant as a sanity probe that WhatsApp UI was actually rendered. The implementation conflated "no legacy IDs visible" with "WhatsApp is not foregrounded," a category error that turned the safety net into a guillotine.

**Check 4** (lines 1331-1343, the final lock-screen check) is retained — it adds a real signal not covered by Checks 1 and 2 (the screen could be on but locked while WhatsApp is technically the foreground app).

The function shrinks from 139 lines to ~80 lines. The `try/except` at the outer level (lines 1224 and 1351-1359) is preserved — any exception during package/activity probes still hard-fails, which is correct.

### Change 2 — Cascade-halt counter in `ChatExporter`

**File:** `whatsapp_chat_autoexport/export/chat_exporter.py`

Add alongside the existing `_consecutive_recovery_count`:

```python
class ChatExporter:
    MAX_CONSECUTIVE_RECOVERIES = 3          # existing, line 145
    MAX_CONSECUTIVE_VERIFY_FAILURES = 3     # NEW

    def __init__(self, ...):
        ...
        self._consecutive_recovery_count: int = 0          # existing
        self._consecutive_verify_failure_count: int = 0    # NEW
```

Add a small helper:

```python
def _check_consecutive_verify_failure_limit(self) -> bool:
    """Return True if N consecutive verify failures have aborted the batch."""
    if self._consecutive_verify_failure_count >= self.MAX_CONSECUTIVE_VERIFY_FAILURES:
        self.logger.error(
            f"Stopping batch: {self._consecutive_verify_failure_count} consecutive "
            f"WhatsApp verification failures reached the limit of "
            f"{self.MAX_CONSECUTIVE_VERIFY_FAILURES}. The verifier may be regressed; "
            "investigate before re-running."
        )
        return True
    return False
```

Wire it into the two batch-loop verify call sites:

- **Line 501** (`export_chats_to_google_drive`): on `verify_whatsapp_is_open() == False`, increment the counter; if `_check_consecutive_verify_failure_limit()` returns True, break the loop with a `state_manager.fail_chat()` reason of `"Consecutive verify-failure limit reached"`.
- **Line 1666** (`export_chats_to_google_drive_with_session_recovery`, the resumable variant): same wiring.

Reset to 0 in the same places `_consecutive_recovery_count` is reset:

- Line 484 / 1645 (start of batch).
- Line 580 / 1775 (after a fully successful export).

The existing recovery flow is preserved unchanged. The new counter is a separate failure mode and stops the batch *before* recovery is attempted (since recovery itself re-invokes the verifier — exactly the cascade we're guarding against).

### Change 3 — Tests

**File:** `tests/unit/test_whatsapp_driver_verify.py` (new) — covers the verifier:

1. `test_verify_returns_true_when_package_and_activity_safe` — mock driver: package `com.whatsapp`, activity `com.whatsapp.HomeActivity`, lock check returns unlocked. Assert `True`. (Pins post-fix happy path; would fail under current code on Material 3.)
2. `test_verify_returns_false_when_package_not_whatsapp` — mock driver: package `com.android.settings`. Assert `False`. (Pins Check 1.)
3. `test_verify_returns_false_when_activity_unsafe` — mock driver: package `com.whatsapp`, activity `com.android.systemui.Keyguard`. Assert `False`. (Pins Check 2.)
4. `test_verify_returns_false_when_phone_locked` — mock driver: package + activity safe, but `check_if_phone_locked()` returns True. Assert `False`. (Pins Check 4.)

**File:** `tests/unit/test_chat_exporter_verify_cascade.py` (new) — covers the cascade-halt:

5. `test_three_consecutive_verify_failures_halts_batch` — mock driver where `verify_whatsapp_is_open()` always returns False. Submit a batch of 5 chats. Assert the loop breaks at chat 3, the remaining chats are not attempted, and the batch logs the consecutive-verify-failure stop message.

All five tests are pure unit tests with no Appium dependency, no `requires_device` marker, runnable in CI.

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Removing Check 3 lets a non-WhatsApp screen slip through if Checks 1+2 are wrong | Low | Checks 1 and 2 read directly from Appium's session — there is no realistic path where they report `com.whatsapp` + safe activity but the foreground is something else. The original belt-and-braces was a category error, not a real second signal. |
| `MAX_CONSECUTIVE_VERIFY_FAILURES = 3` is too aggressive on a flaky network | Low | The verifier never hits the network — only `current_package`, `current_activity`, and a lock probe. Three consecutive failures of those is a real broken state, not flakiness. |
| Cascade-halt collides with `_attempt_session_recovery`'s own retry budget | Low | The two counters are independent: verify-failures halt *before* recovery is attempted; recovery-count halts after recovery has been attempted. Both can fire within the same run; either firing halts the batch. |
| Other call sites (`export_pane.py:563`, `interactive.py:138`, etc.) still rely on the verifier and won't get the cascade guard | Accepted | The bug they hit is fixed by Change 1 alone. Each non-batch caller fails fast on a single `False`, which is the correct behaviour outside a batch loop. |

## Acceptance criteria

- All four verifier unit tests in `test_whatsapp_driver_verify.py` pass.
- The cascade unit test in `test_chat_exporter_verify_cascade.py` passes.
- Existing `pytest tests/unit/ tests/integration/ -m "not requires_api and not requires_device and not requires_drive"` suite passes (no regressions).
- `poetry run whatsapp --help` exit 0, output contains `--headless` (per `.claude/testing.md`'s `help-flag` recipe).
- `verify_whatsapp_is_open()` no longer references the four legacy resource IDs.
- `ChatExporter` has `MAX_CONSECUTIVE_VERIFY_FAILURES` class constant and `_consecutive_verify_failure_count` instance counter.
- Issue #27 referenced in the PR body via `Closes #27`.

## Related

- `docs/solutions/integration-issues/whatsapp-material3-resource-id-allowlist-2026-04-30.md` — full diagnosis including Open Questions; this spec resolves all six.
- `docs/failure-reports/2026-04-16-full-run-pause.md` — separate verifier failure (focus-return race); not addressed here, but the simplified verifier reduces surface area.
- `docs/plans/2026-04-17-001-fix-full-run-failures-plan.md` — active plan; cross-reference both ways but land standalone.
