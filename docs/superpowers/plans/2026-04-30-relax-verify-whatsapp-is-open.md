# Relax `verify_whatsapp_is_open()` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `verify_whatsapp_is_open()` work on WhatsApp 2.26 Material 3 by deleting the legacy resource-ID probe (Check 3), and add a cascade-halt counter so a future verifier regression cannot poison more than 3 chats in a batch.

**Architecture:** Two narrow production edits (`whatsapp_driver.py`, `chat_exporter.py`) plus one new unit test file per edit. TDD throughout — every behaviour change has a failing test before code lands. Existing test suite must still pass with no modifications.

**Tech Stack:** Python 3.13, pytest, unittest.mock. No Appium dependency in tests — drivers are mocked.

**Spec:** `docs/superpowers/specs/2026-04-30-relax-verify-whatsapp-is-open-design.md`

**Issue:** [#27](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/27)

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `whatsapp_chat_autoexport/export/whatsapp_driver.py` | Modify (lines 1272-1329 deleted) | Verifier without legacy resource-ID probe |
| `whatsapp_chat_autoexport/export/chat_exporter.py` | Modify (5 sites) | Add `MAX_CONSECUTIVE_VERIFY_FAILURES`, counter, helper, two wired call sites, two reset sites |
| `tests/unit/test_whatsapp_driver_verify.py` | Create | Unit tests for verifier (4 tests) |
| `tests/unit/test_chat_exporter_verify_cascade.py` | Create | Unit test for cascade-halt (1 test) |

The plan is sequenced so test files land first, then prod code, then refactor. Five tasks total.

---

## Task 1: Pin verifier behaviour with failing tests

**Files:**
- Create: `tests/unit/test_whatsapp_driver_verify.py`
- Reference: `whatsapp_chat_autoexport/export/whatsapp_driver.py:1211-1359`

The current verifier hard-fails on Material 3 because Check 3 finds no legacy IDs. We're going to delete Check 3, so we need tests that pin: (a) verifier passes when package + activity are safe and phone unlocked, even if no element-IDs match (this currently FAILS — it's the bug); (b) verifier still fails when package is wrong, activity is unsafe, or phone is locked (these currently PASS but must keep passing after the change).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_whatsapp_driver_verify.py`:

```python
"""Unit tests for WhatsAppDriver.verify_whatsapp_is_open().

Covers the post-fix behaviour: verifier trusts package + activity + lock-screen
checks. The legacy resource-ID probe has been removed (issue #27), so verify
must succeed even when no WhatsApp element IDs are visible.
"""

from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver


def _make_driver(
    *,
    current_package: str = "com.whatsapp",
    current_activity: str = "com.whatsapp.HomeActivity",
    is_locked: bool = False,
    lock_reason: str = "screen on, unlocked",
) -> WhatsAppDriver:
    """Build a WhatsAppDriver with its Appium driver and lock check mocked.

    The verifier reads `driver.current_package` and `driver.current_activity`
    via `safe_driver_call`, and calls `self.check_if_phone_locked()`. Mock
    those three points and the verifier becomes deterministic.
    """
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.driver = MagicMock()
    wd.driver.current_package = current_package
    wd.driver.current_activity = current_activity
    wd.logger = MagicMock()
    wd.safe_driver_call = MagicMock(side_effect=lambda _label, fn, **_kw: fn())
    wd.check_if_phone_locked = MagicMock(return_value=(is_locked, lock_reason))
    return wd


@pytest.mark.unit
def test_verify_returns_true_when_package_and_activity_safe():
    """Material 3 happy path: no legacy IDs visible, package + activity safe."""
    wd = _make_driver()
    assert wd.verify_whatsapp_is_open() is True


@pytest.mark.unit
def test_verify_returns_false_when_package_not_whatsapp():
    """Settings or another app foregrounded — must hard-fail."""
    wd = _make_driver(current_package="com.android.settings")
    assert wd.verify_whatsapp_is_open() is False


@pytest.mark.unit
def test_verify_returns_false_when_activity_unsafe():
    """Lock screen / system UI / settings activity must hard-fail."""
    wd = _make_driver(current_activity="com.android.systemui.Keyguard")
    assert wd.verify_whatsapp_is_open() is False


@pytest.mark.unit
def test_verify_returns_false_when_phone_locked():
    """Final lock check (Check 4) still fires after package + activity pass."""
    wd = _make_driver(is_locked=True, lock_reason="phone is locked")
    assert wd.verify_whatsapp_is_open() is False
```

- [ ] **Step 2: Run tests to verify the happy-path test fails (the bug)**

Run: `poetry run pytest tests/unit/test_whatsapp_driver_verify.py -v`

Expected:
- `test_verify_returns_true_when_package_and_activity_safe` → **FAIL** (current verifier returns False because Check 3 finds no legacy IDs in the MagicMock).
- The other three → **PASS** (Checks 1, 2, 4 are unchanged).

This proves the test correctly captures the bug from issue #27.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_whatsapp_driver_verify.py
git commit -m "test: pin verify_whatsapp_is_open() behaviour for Material 3 (#27)

Happy-path test currently fails: verifier rejects Material 3 because
Check 3 probes legacy resource IDs that no longer exist."
```

---

## Task 2: Delete Check 3 from `verify_whatsapp_is_open()`

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py:1272-1329`

- [ ] **Step 1: Delete the Check 3 block**

In `whatsapp_chat_autoexport/export/whatsapp_driver.py`, delete the entire block from line 1272 through 1329 inclusive — that is, from the comment `# Check 3: Verify we can see WhatsApp UI elements` through and including the `return False` and the trailing `self.logger.success("✓ WhatsApp UI elements accessible")` line.

The exact text to remove (verify with `grep -n "Check 3" whatsapp_chat_autoexport/export/whatsapp_driver.py` first to confirm line numbers haven't drifted):

```python
            # Check 3: Verify we can see WhatsApp UI elements
            self.logger.info("Checking for WhatsApp UI elements...")

            # Try to find common WhatsApp elements
            whatsapp_elements_found = False

            # Look for chat list elements
            try:
                chat_elements = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
                if len(chat_elements) > 0:
                    self.logger.success(f"✓ Found {len(chat_elements)} chat elements")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No chat elements found: {e}")

            # Look for toolbar (present on most WhatsApp screens)
            try:
                toolbar = self.driver.find_elements("id", "com.whatsapp:id/toolbar")
                if len(toolbar) > 0:
                    self.logger.success("✓ Found WhatsApp toolbar")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No toolbar found: {e}")

            # Look for action bar (another common element)
            try:
                action_bar = self.driver.find_elements("id", "com.whatsapp:id/action_bar")
                if len(action_bar) > 0:
                    self.logger.success("✓ Found WhatsApp action bar")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No action bar found: {e}")

            # Look for menu button
            try:
                menu_button = self.driver.find_elements("id", "com.whatsapp:id/menuitem_search")
                if len(menu_button) > 0:
                    self.logger.success("✓ Found WhatsApp menu button")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No menu button found: {e}")

            if not whatsapp_elements_found:
                self.logger.error("=" * 70)
                self.logger.error("❌ CRITICAL FAILURE: No WhatsApp UI elements found!")
                self.logger.error("=" * 70)
                self.logger.error("Package is com.whatsapp but UI is not accessible.")
                self.logger.error("")
                self.logger.error("This could mean:")
                self.logger.error("  - Phone is locked but showing WhatsApp in background")
                self.logger.error("  - WhatsApp is loading but not ready")
                self.logger.error("  - Dialog or overlay is blocking WhatsApp UI")
                self.logger.error("")
                self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
                self.logger.error("=" * 70)
                return False

            self.logger.success("✓ WhatsApp UI elements accessible")
```

The line immediately before the deletion remains: `self.logger.success(f"✓ Activity confirmed safe: {current_activity}")` (currently line 1270). The line immediately after is the renumbered Check 4 block, beginning `# Check 4: Final lock screen check` (currently line 1331).

After deletion, Check 4's comment stays as-is (`# Check 4: Final lock screen check`) — the gap in numbering is intentional and a useful breadcrumb that this function once had a Check 3.

- [ ] **Step 2: Run the new tests — all four pass**

Run: `poetry run pytest tests/unit/test_whatsapp_driver_verify.py -v`

Expected: 4 passed.

- [ ] **Step 3: Run the full unit + integration suite — no regressions**

Run: `poetry run pytest tests/unit/ tests/integration/ -m "not requires_api and not requires_device and not requires_drive" -q --tb=short`

Expected: all green. If any test fails referencing the deleted block, surface the failure — do not paper over it.

- [ ] **Step 4: Commit**

```bash
git add whatsapp_chat_autoexport/export/whatsapp_driver.py
git commit -m "fix: drop legacy resource-ID probe from verify_whatsapp_is_open (#27)

Check 3 hard-failed on WhatsApp 2.26 Material 3 because the four legacy
IDs (conversations_row_contact_name, toolbar, action_bar, menuitem_search)
no longer exist in the redesigned view hierarchy. Checks 1 (package) and
2 (activity) already prove WhatsApp is foregrounded; Check 4 (lock screen)
still fires. Verifier shrinks ~57 lines and is now resilient to future
WhatsApp redesigns that rename view IDs.

Closes the verifier half of #27. Cascade-halt counter follows in the
next commit so a future verifier regression cannot poison >3 chats."
```

---

## Task 3: Add cascade-halt test for `ChatExporter`

**Files:**
- Create: `tests/unit/test_chat_exporter_verify_cascade.py`
- Reference: `whatsapp_chat_autoexport/export/chat_exporter.py` (the existing `MAX_CONSECUTIVE_RECOVERIES` pattern)

This test pins the new behaviour: if `verify_whatsapp_is_open()` returns False three times in a row, the batch halts with a clear log message and does not attempt the remaining chats.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_chat_exporter_verify_cascade.py`:

```python
"""Unit tests for ChatExporter's consecutive-verify-failure cascade halt.

Pins the defence-in-depth behaviour added for issue #27: if the verifier
ever regresses again, the orchestrator halts the batch after 3 consecutive
verification failures rather than grinding through hundreds of chats.
"""

from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter


@pytest.mark.unit
def test_three_consecutive_verify_failures_halts_batch(tmp_path):
    """Mock driver where verify always fails; batch must halt at chat 3."""
    driver = MagicMock()
    driver.verify_whatsapp_is_open.return_value = False
    driver.is_session_active.return_value = True
    driver.reconnect.return_value = False  # any recovery attempt also fails

    logger = MagicMock()
    logger.debug = False  # match Logger contract used elsewhere

    exporter = ChatExporter(driver, logger)

    chat_names = [f"Chat {i}" for i in range(1, 6)]  # 5 chats

    # Use the legacy `export_chats` path (line 1666 verify call site) — its
    # cascade-halt logic is structurally simpler to test (no StateManager
    # setup required). The new-workflow path (`export_chats_with_new_workflow`,
    # line 501) uses identical counter logic and is exercised in production.
    results, _timings, _total, _skipped = exporter.export_chats(
        chat_names=chat_names,
        include_media=False,
    )

    # Three verify calls (chats 1, 2, 3) — then the limit fires and the loop
    # breaks before chat 4's verify call.
    assert driver.verify_whatsapp_is_open.call_count == ChatExporter.MAX_CONSECUTIVE_VERIFY_FAILURES, (
        f"Expected exactly {ChatExporter.MAX_CONSECUTIVE_VERIFY_FAILURES} verify "
        f"calls before halt, got {driver.verify_whatsapp_is_open.call_count}"
    )

    # Chats 4 and 5 must not appear in results — the batch halted before them.
    assert "Chat 4" not in results
    assert "Chat 5" not in results

    # Chats 1–3 are recorded as failed.
    for n in (1, 2, 3):
        assert results.get(f"Chat {n}") is False, f"Chat {n} should be recorded as failed"

    # The halt message reaches the logger.
    halt_messages = [
        call for call in logger.error.call_args_list
        if "consecutive WhatsApp verification failures" in str(call)
    ]
    assert halt_messages, "Expected a 'consecutive verify failures' halt log message"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_chat_exporter_verify_cascade.py -v`

Expected: **FAIL** — `MAX_CONSECUTIVE_VERIFY_FAILURES` does not exist on `ChatExporter`. Likely an `AttributeError`.

This proves the test is exercising the not-yet-implemented behaviour.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_chat_exporter_verify_cascade.py
git commit -m "test: pin cascade-halt at 3 consecutive verify failures (#27)

Defence-in-depth so a future verifier regression cannot poison more
than 3 chats. Test fails until MAX_CONSECUTIVE_VERIFY_FAILURES and the
counter are wired in chat_exporter.py."
```

---

## Task 4: Implement cascade-halt in `ChatExporter`

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py` — five edit sites

Make all five edits in this single task (one task per file is the right granularity here — they're a coherent set), then run the suite.

- [ ] **Step 1: Add the class constant alongside `MAX_CONSECUTIVE_RECOVERIES`**

In `chat_exporter.py`, find the existing constant at line 145:

```python
    # Max consecutive recovery attempts before aborting the batch.
    # 1 = transient, 2 = unlucky, 3 = systemic issue (phone overheating, OOM, etc.)
    MAX_CONSECUTIVE_RECOVERIES = 3
```

Replace it with:

```python
    # Max consecutive recovery attempts before aborting the batch.
    # 1 = transient, 2 = unlucky, 3 = systemic issue (phone overheating, OOM, etc.)
    MAX_CONSECUTIVE_RECOVERIES = 3

    # Max consecutive verify_whatsapp_is_open() failures before aborting the batch.
    # Defence-in-depth (issue #27): a regressed verifier cannot poison more than
    # this many chats. Counter is independent of MAX_CONSECUTIVE_RECOVERIES.
    MAX_CONSECUTIVE_VERIFY_FAILURES = 3
```

- [ ] **Step 2: Add the instance counter alongside `_consecutive_recovery_count`**

Find lines 160-161:

```python
        # Session recovery tracking
        self._consecutive_recovery_count: int = 0
```

Replace with:

```python
        # Session recovery tracking
        self._consecutive_recovery_count: int = 0
        # Verify-failure cascade tracking (issue #27)
        self._consecutive_verify_failure_count: int = 0
```

- [ ] **Step 3: Add the helper next to `_check_consecutive_recovery_limit`**

Find the existing helper at line 217-230:

```python
    def _check_consecutive_recovery_limit(self) -> bool:
        """Check if the consecutive recovery limit has been reached.

        Returns:
            True if the limit has been reached (batch should stop), False otherwise.
        """
        if self._consecutive_recovery_count >= self.MAX_CONSECUTIVE_RECOVERIES:
            self.logger.error(
                f"Stopping batch: {self._consecutive_recovery_count} consecutive session recoveries "
                f"reached the limit of {self.MAX_CONSECUTIVE_RECOVERIES}. "
                f"This suggests a systemic issue (phone overheating, memory exhaustion, etc.)"
            )
            return True
        return False
```

Add immediately after it:

```python
    def _check_consecutive_verify_failure_limit(self) -> bool:
        """Check if the consecutive verify-failure limit has been reached.

        Returns:
            True if the limit has been reached (batch should stop), False otherwise.
        """
        if self._consecutive_verify_failure_count >= self.MAX_CONSECUTIVE_VERIFY_FAILURES:
            self.logger.error(
                f"Stopping batch: {self._consecutive_verify_failure_count} consecutive WhatsApp "
                f"verification failures reached the limit of {self.MAX_CONSECUTIVE_VERIFY_FAILURES}. "
                "The verifier may be regressed; investigate before re-running."
            )
            return True
        return False
```

- [ ] **Step 4: Wire counter increment + check at the two batch verify call sites**

There are two batch methods that call `verify_whatsapp_is_open()`:
- `export_chats_with_new_workflow()` — verify at **line 501**, the active TUI path. Uses `state_manager.fail_chat()`.
- `export_chats()` — verify at **line 1666**, the legacy path. Uses `chat_timings` instead of state_manager.

Both need the cascade-halt; their wiring differs slightly because their failure-recording machinery differs.

**Site A — line 501 in `export_chats_with_new_workflow`:**

Find (currently lines 499-509):

```python
            # CRITICAL: Verify WhatsApp is still accessible before each export.
            # If verification fails, attempt session recovery before aborting.
            if not self.driver.verify_whatsapp_is_open():
                state_manager = self._get_state_manager()
                if self._check_consecutive_recovery_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    if state_manager.has_session:
                        state_manager.fail_chat(chat_name, "Consecutive recovery limit reached")
                    break
                if self._attempt_session_recovery("Pre-export verification failed"):
```

Replace with:

```python
            # CRITICAL: Verify WhatsApp is still accessible before each export.
            # If verification fails, attempt session recovery before aborting.
            if not self.driver.verify_whatsapp_is_open():
                self._consecutive_verify_failure_count += 1
                state_manager = self._get_state_manager()
                if self._check_consecutive_verify_failure_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    if state_manager.has_session:
                        state_manager.fail_chat(chat_name, "Consecutive verify-failure limit reached")
                    break
                if self._check_consecutive_recovery_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    if state_manager.has_session:
                        state_manager.fail_chat(chat_name, "Consecutive recovery limit reached")
                    break
                if self._attempt_session_recovery("Pre-export verification failed"):
```

The verify-failure check is checked **before** the recovery-limit check because verify-failures halt the batch *without* attempting recovery (recovery itself re-invokes the verifier — exactly the cascade we're guarding against).

**Site B — line 1666 in `export_chats` (legacy path):**

Find (currently lines 1664-1672):

```python
            # CRITICAL: Verify WhatsApp is still accessible before each export.
            # If verification fails, attempt session recovery before aborting.
            if not self.driver.verify_whatsapp_is_open():
                if self._check_consecutive_recovery_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    ct.status = ChatStatus.FAILED
                    self.chat_timings.append(ct)
                    break
                if self._attempt_session_recovery("Pre-export verification failed"):
```

Replace with:

```python
            # CRITICAL: Verify WhatsApp is still accessible before each export.
            # If verification fails, attempt session recovery before aborting.
            if not self.driver.verify_whatsapp_is_open():
                self._consecutive_verify_failure_count += 1
                if self._check_consecutive_verify_failure_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    ct.status = ChatStatus.FAILED
                    self.chat_timings.append(ct)
                    break
                if self._check_consecutive_recovery_limit():
                    results[chat_name] = False
                    timings[chat_name] = 0
                    ct.status = ChatStatus.FAILED
                    self.chat_timings.append(ct)
                    break
                if self._attempt_session_recovery("Pre-export verification failed"):
```

Note `ct` (`ChatTiming`) and `ChatStatus.FAILED` are already in scope at this point in `export_chats` — see lines 1662, 1670 for the existing pattern.

- [ ] **Step 5: Wire counter reset at the four reset sites**

**Reset Sites — start-of-batch (lines 484, 1645):**

Find each `self._consecutive_recovery_count = 0` at the top of the batch loops and add a sibling line:

Before:
```python
        self._consecutive_recovery_count = 0
```

After:
```python
        self._consecutive_recovery_count = 0
        self._consecutive_verify_failure_count = 0
```

**Reset Sites — after a fully successful export (lines 580, 1775):**

Find each:
```python
                else:
                    # A fully successful export resets the consecutive counter
                    self._consecutive_recovery_count = 0
```

Replace with:
```python
                else:
                    # A fully successful export resets the consecutive counters
                    self._consecutive_recovery_count = 0
                    self._consecutive_verify_failure_count = 0
```

If line numbers have drifted, locate by `grep -n "consecutive counter" whatsapp_chat_autoexport/export/chat_exporter.py`.

- [ ] **Step 6: Run the cascade test — passes**

Run: `poetry run pytest tests/unit/test_chat_exporter_verify_cascade.py -v`

Expected: 1 passed.

- [ ] **Step 7: Run the full suite — no regressions**

Run: `poetry run pytest tests/unit/ tests/integration/ -m "not requires_api and not requires_device and not requires_drive" -q --tb=short`

Expected: all green. Pay special attention to:
- `tests/unit/test_export_recovery.py` — exercises the existing recovery counter; new counter must not interfere.
- `tests/unit/test_export_pane.py` — uses the per-chat verify path; behaviour unchanged from its perspective.

- [ ] **Step 8: Commit**

```bash
git add whatsapp_chat_autoexport/export/chat_exporter.py
git commit -m "feat: halt batch after 3 consecutive verify failures (#27)

Adds MAX_CONSECUTIVE_VERIFY_FAILURES=3 and
_consecutive_verify_failure_count alongside the existing recovery
counter. Wired into both batch verify call sites; reset at start of
batch and after each successful export.

Defence-in-depth: if verify_whatsapp_is_open() ever regresses again,
the batch halts at chat 3, not chat 874. Independent of the recovery
counter — verify-failures halt before recovery is attempted because
recovery itself re-invokes the verifier.

Closes #27."
```

---

## Task 5: Final verification

**Files:** none — this task is just running the local pre-flight gates.

- [ ] **Step 1: Run the project's `unit-tests` recipe explicitly**

Run: `poetry run pytest tests/unit/ tests/integration/ -m "not requires_api and not requires_device and not requires_drive" -q --tb=short`

Expected: all green.

- [ ] **Step 2: Run the project's `help-flag` recipe**

Run: `poetry run whatsapp --help`

Expected: exit 0; output contains `--headless`. (`.claude/testing.md` recipe.)

- [ ] **Step 3: Confirm the verifier really lost Check 3**

Run: `grep -n "Check 3\|conversations_row_contact_name\|menuitem_search" whatsapp_chat_autoexport/export/whatsapp_driver.py`

Expected: no matches in `verify_whatsapp_is_open()` (other matches elsewhere in the file are fine — those are unrelated selectors).

- [ ] **Step 4: Confirm the cascade counter exists**

Run: `grep -n "MAX_CONSECUTIVE_VERIFY_FAILURES\|_consecutive_verify_failure_count" whatsapp_chat_autoexport/export/chat_exporter.py`

Expected: at least 7 matches — class constant (1), instance counter init (1), helper definition (3 lines reference it), increment sites (2), reset sites (4). Roughly 11+ lines total.

- [ ] **Step 5: No-op**

If all four steps above passed, the implementation is done. Hand back to `aj-flow flow` Step 9 (Verify) and Step 10 (Self-review).

---

## Self-Review Checklist (run before handing off)

- [x] **Spec coverage:** Each goal in the spec maps to a task — Goal 1 (verifier passes on Material 3) → Task 1 + 2; Goal 2 (still rejects bad states) → Task 1's three negative tests; Goal 3 (cascade halt at N=3) → Task 3 + 4. Acceptance criteria covered by Task 5.
- [x] **No placeholders:** Every step has the actual code or the actual command. Line numbers caveated with `grep` confirmations in case of drift.
- [x] **Type / name consistency:** `MAX_CONSECUTIVE_VERIFY_FAILURES` and `_consecutive_verify_failure_count` used identically across spec, plan, tests, and prod code. Helper name `_check_consecutive_verify_failure_limit` mirrors existing `_check_consecutive_recovery_limit`.
- [x] **Existing-code respect:** Mirrors the existing `MAX_CONSECUTIVE_RECOVERIES` pattern exactly — same structure, same naming, same reset points. Reviewer can reason by analogy.
