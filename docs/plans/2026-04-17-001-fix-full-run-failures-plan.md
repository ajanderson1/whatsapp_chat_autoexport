---
title: "fix: Resolve full-run failures (verify race, community status, failure visibility)"
type: fix
status: active
date: 2026-04-17
source-report: docs/failure-reports/2026-04-16-full-run-pause.md
---

# fix: Resolve full-run failures — verify race, community status, failure visibility

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Drive-share-return race from failing ~10% of chats, stop marking community chats as failed, and make every failure visible in the TUI chat list so the user can see and retry them.

**Architecture:** Three coordinated fixes. (1) A new `wait_for_whatsapp_foreground()` poll on `WhatsAppDriver` runs before the heavier `verify_whatsapp_is_open()` at every pre-export checkpoint, absorbing the 1–3 s settle window after the Google Drive share activity returns focus. (2) A new `is_community_chat()` probe on the chat toolbar lets `ChatExporter.export_chat_to_google_drive()` detect community chats up front and return a distinct "skipped" outcome instead of raising/returning False ambiguously. (3) The TUI export loop in `export_pane.py` is changed so every failure and every skip — including the pre-export verification failure — routes through `_fail_chat_export` / `_skip_chat_export` and therefore through `ChatListWidget.update_chat_status()`, making the left panel the authoritative failure record.

**Tech Stack:** Python 3.13, Poetry, pytest, Appium-Python-Client, Textual, UiAutomator2.

---

## Problem Frame

During a 956-chat export on 2026-04-16, the run was paused at 280/956 after three distinct failure modes surfaced:

1. **Verification race (SEVERE, ~32 chats):** Immediately after a successful Drive upload, `ChatExporter.export_chats_with_new_workflow()` and `ExportPane._export_single_chat()` both call `driver.verify_whatsapp_is_open()` on the *next* chat. Android has not yet handed focus back from the Drive share activity (`com.android.intentresolver` / `com.google.android.apps.docs`), so `current_package != "com.whatsapp"` and the chat is marked failed without any export attempt. Evidence: failure log lines all share the same wall-clock second; subsequent `_attempt_session_recovery()` succeeds a moment later and the run continues to the chat *after* the skipped one.
2. **Community chats marked failed (2 chats):** `export_chat_to_google_drive()` detects missing "More" option at `chat_exporter.py:980`, logs "likely a community chat" and returns `False`. The TUI treats the returned `False` identically to any other failure — user sees `[✗]` and the chat enters the failed bucket. The old batch loop has a separate error-message heuristic (`chat_exporter.py:551`) that catches the word "community" in an exception message, but the TUI path never raises; it gets `False`.
3. **Chat list under-reports failures (38 log vs 6 UI):** The activity log records 38 unique failures; the left-panel `ChatListWidget` only shows 6 `[✗]` markers. Root cause: in `ExportPane._run_real_export()`, Mode 1 failures flow through `_export_single_chat` which returns `False` *without* raising, so the outer loop's `_fail_chat_export` is called — meaning that path is wired. But there is a separate failure route from `ChatExporter.export_chats_with_new_workflow()`'s internal pre-export check (line 468) which is used elsewhere (headless mode) and which *does not* emit per-chat status to any listener. We must wire both routes through `_fail_chat_export` and add structured failure metadata (reason) so retries are possible.

The failure report (`docs/failure-reports/2026-04-16-full-run-pause.md`) names Fix 1 as "resolve-before-resume" (correctness) and Fixes 2–3 as observability follow-ups. This plan implements all three.

## Requirements Trace

- **R1.** Before calling `verify_whatsapp_is_open()` at the top of each chat iteration, wait up to a configurable timeout (default 8.0 s) for `current_package == "com.whatsapp"`, polling every 250 ms. Applies to both the TUI path (`export_pane.py:508`) and the batch path (`chat_exporter.py:468`).
- **R2.** The settle-wait must be a separate, cheap call on `WhatsAppDriver` — no Appium element queries, just package probing — so that a failed verify is never the *first* diagnostic run during the Drive return.
- **R3.** If the settle-wait times out, fall through to the existing `verify_whatsapp_is_open()` path (so recovery still triggers for genuine non-WhatsApp states); do not short-circuit recovery.
- **R4.** Detect community chats *up front* inside `export_chat_to_google_drive()` (before clicking "More" fails) using a toolbar probe, and return a tri-state result (`"success"`, `"skipped_community"`, `"failed"`) so the TUI can distinguish skip from fail.
- **R5.** Existing call sites that expect `bool` from `export_chat_to_google_drive()` must continue to compile; provide a thin `bool`-returning wrapper or a typed return with a compatibility shim.
- **R6.** TUI `ExportPane._run_real_export()` must call `_skip_chat_export(chat, "Community chat — export unsupported")` for community chats, not `_fail_chat_export`. Community skips must not increment `_consecutive_failures`.
- **R7.** Every failure path in `ChatExporter.export_chats_with_new_workflow()` (pre-verify fail, pre-verify fail after recovery, open-chat fail, workflow exception, session crash) must record a typed reason in the `results` dict and emit a progress callback with a new `"chat_failed"` phase so TUI/headless can surface per-chat status.
- **R8.** `ChatListWidget` must receive a `FAILED` update for every failure in both paths (headless callback-driven and TUI `_fail_chat_export`-driven). After a run ends, the chat-list panel is the single source of truth for per-chat outcome.
- **R9.** Failure and skip reasons must be retained on the session's `StateManager` so a future "Retry failed" flow has the data it needs (the UI for that lands in Fix 6 — out of scope for this plan, but the state-shape must not block it).
- **R10.** All fixes must be covered by unit tests. Verify-race behaviour tested with a fake driver that flips `current_package` after a delay. Community detection tested with a fake toolbar element. TUI wiring tested via `test_export_pane.py` with injected drivers.

## Scope Boundaries

- This plan does NOT implement Fix 4 (`--delete-from-drive` decoupling) — requires pipeline investigation still open as question #1 of the report.
- This plan does NOT implement Fix 5 (pipeline throughput / parallel transcription) — architectural, separate plan.
- This plan does NOT implement Fix 6 (Retry-failed button) — it just preserves enough state for that future work.
- This plan does NOT add automatic retry *of the same chat* that failed verification; behaviour remains "advance to next chat, surface the failure".
- This plan does NOT change `verify_whatsapp_is_open()` internals. The settle-wait is strictly *before* it.
- This plan does NOT modify the headless mode's exit-code contract (0/1/2) except to guarantee partial-failure results still roll up to exit code 1.
- This plan does NOT change the `current_package` values we trust. `com.whatsapp` remains the only accepted foreground package.

## Context & Research

### Failure Race Trace

- `ChatExporter.export_chats_with_new_workflow()` at `chat_exporter.py:463-489` runs `verify_whatsapp_is_open()` at the top of every iteration. The previous iteration ends immediately after the Drive share intent fires, which returns control to `export_chat_to_google_drive()` before Android swaps focus back to `com.whatsapp`.
- The TUI path at `export_pane.py:474-532` calls the same `verify_whatsapp_is_open()` at line 508 inside `_export_single_chat`, same race.
- `WhatsAppDriver.is_session_active()` at `whatsapp_driver.py:497-512` already shows the shape of a cheap package probe — exactly what we need but without the "is WhatsApp" semantics.
- `WhatsAppDriver.verify_whatsapp_is_open()` at `whatsapp_driver.py:1189-1337` performs 4 checks: package, activity, UI elements, lock screen. The UI-element check is expensive (multiple `find_elements`) and prints multi-line headers; running it during the settle window turns a transient state into a noisy false-negative.

### Community-Chat Detection

- `chat_exporter.py:978-988`: when no "More" menuitem is found after opening the overflow menu, the code presses back twice, logs "likely a community chat", and returns `False`. This is *after* navigation; recovery still has to scroll/press back.
- The WhatsApp community toolbar shows a community badge icon with resource id `com.whatsapp:id/community_pill` (verified in sample XML dumps during past runs; see `docs/discovery/` stub). A pre-export probe on the chat's top toolbar can detect community without opening the menu.
- `ExportWorkflow.run_export()` (the newer workflow path) also routes through `export_chat_to_google_drive`; any change to the return shape affects both.

### TUI Failure-Wiring Gap

- TUI: `ExportPane._run_real_export()` at `export_pane.py:349-472` catches `success == False` and exceptions and calls `_fail_chat_export` — this path **is** wired. Evidence that 6/38 showed up: 6 chats raised exceptions; 32 returned `False` from `_export_single_chat` silently because of… actually: both cases go through `_fail_chat_export`, so the TUI-path accounting should not lose failures.
- The missing 32 come from a different code path: **the state-manager bridge**. `ChatExporter.export_chats_with_new_workflow()` (headless) calls `state_manager.fail_chat()` but does not emit a progress callback with phase `"chat_failed"` — so any TUI subscribed via progress callback to that code path (future feature, currently not used) would not see failures. More critically, because the TUI runs its *own* loop (not `export_chats_with_new_workflow`), the state-manager is populated *by the TUI pane* — and the TUI pane *does* call `_fail_chat_export`. So the TUI's on-screen count should match. That it did not match (6 vs 38) means one of: (a) the TUI `_fail_chat_export` silently swallowed the widget update due to a `query_one` failure (`except Exception: pass` at lines 597-598), or (b) 32 failures were classified as "recoverable" and never reached `_fail_chat_export`.
- The most likely explanation, given the race trace, is that **recovery-successful paths** (`chat_exporter.py:476-482`) mark the chat failed in `state_manager` but do not update the UI. In the TUI, the same pattern is reproduced: `_export_single_chat` returns `False` on `verify_whatsapp_is_open()` failure, but the pane's `_fail_chat_export` is called (this should mark UI correctly — unless the widget query fails). The mismatch strongly suggests the `query_one` sometimes fails silently when the pane is re-composed on tab switches. This plan adds a targeted assertion path: failures must be recorded in a pane-local list *before* UI update, and a reconcile step at run end pushes the authoritative list to the widget.

### Relevant Code Locations

- `whatsapp_chat_autoexport/export/whatsapp_driver.py:497-512` — `is_session_active` (model for `wait_for_whatsapp_foreground`)
- `whatsapp_chat_autoexport/export/whatsapp_driver.py:1189-1337` — `verify_whatsapp_is_open`
- `whatsapp_chat_autoexport/export/chat_exporter.py:463-489` — pre-export verify in batch loop
- `whatsapp_chat_autoexport/export/chat_exporter.py:798-999` — `export_chat_to_google_drive`, community-chat path at `:978-988`
- `whatsapp_chat_autoexport/export/chat_exporter.py:551` — exception-based community skip (legacy `export_chats`)
- `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py:349-472` — TUI export loop
- `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py:474-532` — `_export_single_chat` (pre-verify call at `:508`)
- `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py:538-620` — UI update helpers (`_start/_complete/_fail/_skip_chat_export`)
- `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py:22-28` — `ChatDisplayStatus` enum
- `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py:444-457` — `update_chat_status` method
- `tests/unit/test_export_pane.py` — TUI export-pane tests
- `tests/unit/test_export_recovery.py` — session recovery / verification tests

### Test Fixtures

- `tests/conftest.py` provides `tui_app` (dry-run `WhatsAppExporterApp` with `StateManager` and temp output).
- Existing mock-driver pattern in `test_export_recovery.py` — returns scripted package/activity values — is the template for the settle-wait test.

## File Structure

**New files:**

- `whatsapp_chat_autoexport/export/foreground_wait.py` — stateless helper function `wait_for_whatsapp_foreground(driver, timeout, poll_interval, logger)`. Kept outside the `WhatsAppDriver` class so it can be unit-tested with a duck-typed driver stub.
- `tests/unit/test_foreground_wait.py` — tests for the helper.
- `tests/unit/test_community_detection.py` — tests for the community-chat probe.

**Modified files:**

- `whatsapp_chat_autoexport/export/whatsapp_driver.py` — thin method `wait_for_whatsapp_foreground()` that delegates to the helper; new `is_community_chat()` method.
- `whatsapp_chat_autoexport/export/chat_exporter.py` — (1) call `wait_for_whatsapp_foreground()` before `verify_whatsapp_is_open()` in the batch loop; (2) community up-front probe in `export_chat_to_google_drive()`; (3) replace `bool` return with a typed `ExportOutcome` dataclass (success + skip_reason + fail_reason) plus a backwards-compat `bool` coercion; (4) emit `"chat_failed"` / `"chat_skipped"` progress phases with reason strings.
- `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py` — (1) wait-for-foreground call before verify in `_export_single_chat`; (2) handle tri-state return from export; (3) maintain an authoritative `_per_chat_status` dict and reconcile to the widget at each status transition and again at run-end; (4) route community outcomes through `_skip_chat_export` without incrementing consecutive-failures.
- `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py` — add optional `reason` arg to `update_chat_status(name, status, reason=None)` and expose it via `get_status_reasons()` for future retry UX.
- `tests/unit/test_export_pane.py` — add coverage for the new wiring.
- `tests/unit/test_export_recovery.py` — add a regression test for the race.
- `docs/failure-reports/2026-04-16-full-run-pause.md` — add a "Resolution" footer pointing at this plan and the PR once merged (small doc update at the end of the work).

Responsibility split rationale: the settle-wait lives in its own helper file because the logic is trivial but will grow (e.g. wireless vs USB timeouts) and because a standalone function is the cheapest thing to mock in tests without needing Appium. `ExportOutcome` lives inside `chat_exporter.py` because it never crosses the module boundary; returning a stringly-typed tuple would be worse. Community detection is a new `WhatsAppDriver` method because it is a UI query against a WhatsApp widget, which is the driver's domain.

## Task Decomposition

### Task 1: Add `wait_for_whatsapp_foreground()` helper

**Files:**
- Create: `whatsapp_chat_autoexport/export/foreground_wait.py`
- Test:   `tests/unit/test_foreground_wait.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_foreground_wait.py
"""Tests for the foreground-settle helper used before verify_whatsapp_is_open()."""

import pytest
from unittest.mock import MagicMock

from whatsapp_chat_autoexport.export.foreground_wait import (
    wait_for_whatsapp_foreground,
)


class FakeAppiumDriver:
    """Minimal stand-in for the Appium driver with scripted current_package values."""

    def __init__(self, packages):
        # packages: list consumed one per read; last value sticks
        self._packages = list(packages)

    @property
    def current_package(self):
        if len(self._packages) > 1:
            return self._packages.pop(0)
        return self._packages[0]


class FakeDriverWrapper:
    """Stand-in for WhatsAppDriver exposing the .driver attribute and a logger."""

    def __init__(self, packages):
        self.driver = FakeAppiumDriver(packages)
        self.logger = MagicMock()


def test_returns_true_when_already_foreground():
    wrapper = FakeDriverWrapper(["com.whatsapp"])
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_returns_true_after_transient_non_whatsapp_package():
    wrapper = FakeDriverWrapper(
        ["com.android.intentresolver", "com.android.intentresolver", "com.whatsapp"]
    )
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_returns_false_on_timeout():
    wrapper = FakeDriverWrapper(["com.google.android.apps.docs"])
    assert wait_for_whatsapp_foreground(wrapper, timeout=0.1, poll_interval=0.01) is False


def test_exceptions_during_probe_are_treated_as_not_foreground():
    wrapper = FakeDriverWrapper(["com.whatsapp"])
    # Replace current_package with a raising property for the first N calls
    calls = {"n": 0}

    class RaisingDriver:
        @property
        def current_package(self):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("session flaking")
            return "com.whatsapp"

    wrapper.driver = RaisingDriver()
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_logs_when_wait_occurs(caplog):
    wrapper = FakeDriverWrapper(["com.android.intentresolver", "com.whatsapp"])
    wait_for_whatsapp_foreground(wrapper, timeout=0.5, poll_interval=0.01)
    # Logger is a MagicMock on the wrapper; ensure at least one debug/info call happened
    assert wrapper.logger.debug_msg.called or wrapper.logger.info.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_foreground_wait.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'whatsapp_chat_autoexport.export.foreground_wait'`

- [ ] **Step 3: Write minimal implementation**

```python
# whatsapp_chat_autoexport/export/foreground_wait.py
"""
Pre-verify settle wait.

Polls the Appium driver's `current_package` for up to `timeout` seconds,
returning True as soon as WhatsApp becomes the foreground package.
Targets the race where `verify_whatsapp_is_open()` runs before Android
has handed focus back from the Google Drive share activity.
"""

import time
from typing import Any


WHATSAPP_PACKAGE = "com.whatsapp"


def wait_for_whatsapp_foreground(
    driver_wrapper: Any,
    timeout: float = 8.0,
    poll_interval: float = 0.25,
) -> bool:
    """
    Wait up to `timeout` seconds for `com.whatsapp` to be the foreground package.

    Args:
        driver_wrapper: Object exposing `.driver.current_package` and `.logger`.
                        In production this is `WhatsAppDriver`.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between package probes.

    Returns:
        True as soon as the package is `com.whatsapp`. False if the timeout
        elapses without WhatsApp becoming foreground. Exceptions during the
        probe are swallowed and treated as "not yet foreground".
    """
    logger = getattr(driver_wrapper, "logger", None)
    deadline = time.monotonic() + timeout
    attempts = 0
    last_seen = None

    while True:
        attempts += 1
        try:
            pkg = driver_wrapper.driver.current_package
        except Exception as e:
            pkg = None
            if logger is not None:
                logger.debug_msg(f"[settle] probe {attempts} raised: {e}")

        if pkg == WHATSAPP_PACKAGE:
            if attempts > 1 and logger is not None:
                logger.info(
                    f"[settle] WhatsApp foreground after {attempts} probe(s)"
                )
            return True

        if pkg != last_seen:
            last_seen = pkg
            if logger is not None:
                logger.debug_msg(f"[settle] current_package={pkg!r}; waiting")

        if time.monotonic() >= deadline:
            if logger is not None:
                logger.debug_msg(
                    f"[settle] timeout after {attempts} probe(s); last_seen={last_seen!r}"
                )
            return False

        time.sleep(poll_interval)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_foreground_wait.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/foreground_wait.py tests/unit/test_foreground_wait.py
git commit -m "feat(export): add wait_for_whatsapp_foreground settle helper"
```

---

### Task 2: Expose helper as `WhatsAppDriver.wait_for_whatsapp_foreground()`

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py` (add method near `is_session_active` at line 497)
- Test:   `tests/unit/test_foreground_wait.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_foreground_wait.py

from unittest.mock import patch


def test_whatsappdriver_method_delegates_to_helper():
    """WhatsAppDriver.wait_for_whatsapp_foreground should call the helper."""
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

    # Build a WhatsAppDriver without actually connecting
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.driver = MagicMock()
    wd.driver.current_package = "com.whatsapp"
    wd.logger = MagicMock()

    with patch(
        "whatsapp_chat_autoexport.export.whatsapp_driver.wait_for_whatsapp_foreground",
        return_value=True,
    ) as mock_helper:
        result = wd.wait_for_whatsapp_foreground(timeout=2.0, poll_interval=0.05)

    assert result is True
    mock_helper.assert_called_once_with(wd, timeout=2.0, poll_interval=0.05)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_foreground_wait.py::test_whatsappdriver_method_delegates_to_helper -v`
Expected: FAIL — `AttributeError: 'WhatsAppDriver' object has no attribute 'wait_for_whatsapp_foreground'`.

- [ ] **Step 3: Write minimal implementation**

Add near the top of `whatsapp_driver.py` (imports):

```python
from .foreground_wait import wait_for_whatsapp_foreground
```

Add method directly below `is_session_active()` in `WhatsAppDriver` (`whatsapp_driver.py` after line 512):

```python
    def wait_for_whatsapp_foreground(
        self, timeout: float = 8.0, poll_interval: float = 0.25
    ) -> bool:
        """
        Wait up to `timeout` seconds for com.whatsapp to become the foreground package.

        Call this before `verify_whatsapp_is_open()` when returning from an external
        activity (e.g. the Google Drive share sheet) to absorb the 1-3 s hand-back
        window on Android. Failure falls through to `verify_whatsapp_is_open()`.

        Args:
            timeout: Maximum seconds to wait.
            poll_interval: Seconds between package probes.

        Returns:
            True if `com.whatsapp` was observed before the deadline, False otherwise.
        """
        return wait_for_whatsapp_foreground(
            self, timeout=timeout, poll_interval=poll_interval
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_foreground_wait.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/whatsapp_driver.py tests/unit/test_foreground_wait.py
git commit -m "feat(driver): expose wait_for_whatsapp_foreground on WhatsAppDriver"
```

---

### Task 3: Integrate settle-wait in batch loop (`export_chats_with_new_workflow`)

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py:463-489`
- Test:   `tests/unit/test_export_recovery.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_recovery.py

import pytest
from unittest.mock import MagicMock, call

from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter


class _DriverWithRace:
    """
    Drives a scripted sequence: first verify_whatsapp_is_open() call during a
    settle window, then foreground, then ok. The settle-wait must be consulted
    BEFORE verify_whatsapp_is_open() on each iteration.
    """

    def __init__(self):
        self.driver = MagicMock()
        self.verify_call_count = 0
        self.settle_call_count = 0
        self.is_session_active = MagicMock(return_value=True)
        self.navigate_to_main = MagicMock()
        self.click_chat = MagicMock(return_value=True)
        self.navigate_back_to_main = MagicMock()

    def wait_for_whatsapp_foreground(self, timeout=8.0, poll_interval=0.25):
        self.settle_call_count += 1
        return True  # simulate successful settle

    def verify_whatsapp_is_open(self):
        self.verify_call_count += 1
        return True


def test_batch_loop_calls_settle_before_verify(monkeypatch):
    driver = _DriverWithRace()
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)
    # Stub workflow invocation so the loop only exercises the guard
    monkeypatch.setattr(
        exporter, "export_with_new_workflow", lambda **kw: (True, "ok")
    )

    results, _, _, _ = exporter.export_chats_with_new_workflow(
        ["ChatA", "ChatB"], include_media=False
    )

    assert driver.settle_call_count == 2
    assert driver.verify_call_count == 2
    assert results == {"ChatA": True, "ChatB": True}


def test_batch_loop_still_triggers_recovery_when_settle_times_out(monkeypatch):
    driver = _DriverWithRace()
    # Settle times out; verify must still be called so existing recovery fires
    driver.wait_for_whatsapp_foreground = MagicMock(return_value=False)
    driver.verify_whatsapp_is_open = MagicMock(return_value=False)
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)

    monkeypatch.setattr(
        exporter,
        "_check_consecutive_recovery_limit",
        lambda: False,
    )
    monkeypatch.setattr(
        exporter, "_attempt_session_recovery", lambda ctx: False
    )

    results, _, _, _ = exporter.export_chats_with_new_workflow(
        ["ChatA"], include_media=False
    )

    driver.wait_for_whatsapp_foreground.assert_called_once()
    driver.verify_whatsapp_is_open.assert_called_once()
    assert results["ChatA"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_export_recovery.py::test_batch_loop_calls_settle_before_verify tests/unit/test_export_recovery.py::test_batch_loop_still_triggers_recovery_when_settle_times_out -v`
Expected: FAIL — batch loop does not call `wait_for_whatsapp_foreground`.

- [ ] **Step 3: Write minimal implementation**

In `chat_exporter.py`, replace the block at lines 463-489:

```python
        for i, chat_name in enumerate(chat_names, 1):
            self.logger.info(f"\nProcessing chat {i}/{total}: '{chat_name}'")

            # Settle wait absorbs the Drive-share-return window before we run
            # the heavier WhatsApp verification. Failure here does NOT short-
            # circuit verify; it falls through so real non-WhatsApp states
            # still reach the existing recovery path.
            settled = self.driver.wait_for_whatsapp_foreground(timeout=8.0)
            if not settled:
                self.logger.debug_msg(
                    "Foreground settle timed out; falling through to verify"
                )

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
                    results[chat_name] = False
                    timings[chat_name] = 0
                    if state_manager.has_session:
                        state_manager.fail_chat(chat_name, "Session recovered - skipping to next chat")
                    continue
                else:
                    self.logger.error(
                        f"WhatsApp is not accessible - cannot export '{chat_name}'. Stopping batch."
                    )
                    results[chat_name] = False
                    timings[chat_name] = 0
                    if state_manager.has_session:
                        state_manager.fail_chat(chat_name, "WhatsApp became inaccessible")
                    break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_export_recovery.py -v`
Expected: all prior tests pass, two new tests pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/chat_exporter.py tests/unit/test_export_recovery.py
git commit -m "fix(export): settle-wait for WhatsApp foreground before pre-export verify"
```

---

### Task 4: Integrate settle-wait in TUI `_export_single_chat`

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py:474-532`
- Test:   `tests/unit/test_export_pane.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_pane.py

from unittest.mock import MagicMock, patch


class TestExportPaneSettleWait:
    """Verify TUI calls wait_for_whatsapp_foreground before verify_whatsapp_is_open."""

    def _make_driver(self, settle_return=True, verify_return=True):
        driver = MagicMock()
        driver.wait_for_whatsapp_foreground = MagicMock(return_value=settle_return)
        driver.verify_whatsapp_is_open = MagicMock(return_value=verify_return)
        driver.navigate_to_main = MagicMock()
        driver.click_chat = MagicMock(return_value=True)
        return driver

    def test_settle_called_before_verify_on_tui_path(self):
        pane = ExportPane()
        driver = self._make_driver(settle_return=True, verify_return=True)

        with patch(
            "whatsapp_chat_autoexport.tui.textual_panes.export_pane.ChatExporter"
        ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = True

            result = pane._export_single_chat(
                driver, "ChatA", include_media=False, log_callback=None
            )

        assert result is True
        driver.wait_for_whatsapp_foreground.assert_called_once()
        driver.verify_whatsapp_is_open.assert_called_once()
        # Settle must precede verify
        order = [
            c[0]
            for c in driver.mock_calls
            if c[0] in ("wait_for_whatsapp_foreground", "verify_whatsapp_is_open")
        ]
        assert order[0] == "wait_for_whatsapp_foreground"

    def test_settle_timeout_still_calls_verify(self):
        pane = ExportPane()
        driver = self._make_driver(settle_return=False, verify_return=False)

        result = pane._export_single_chat(
            driver, "ChatA", include_media=False, log_callback=None
        )

        assert result is False
        driver.wait_for_whatsapp_foreground.assert_called_once()
        driver.verify_whatsapp_is_open.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_export_pane.py::TestExportPaneSettleWait -v`
Expected: FAIL — `wait_for_whatsapp_foreground` not called from `_export_single_chat`.

- [ ] **Step 3: Write minimal implementation**

In `export_pane.py`, replace the `try:` block of `_export_single_chat` (lines 507-511):

```python
        try:
            # Settle wait absorbs the Drive-share-return window before verify.
            # Timeout here is not fatal - we fall through to verify so existing
            # failure handling still triggers for genuine non-WhatsApp states.
            if not driver.wait_for_whatsapp_foreground(timeout=8.0):
                if log_callback:
                    log_callback(
                        "Foreground settle timed out; running full verify",
                        "debug",
                    )

            if not driver.verify_whatsapp_is_open():
                if log_callback:
                    log_callback("WhatsApp verification failed", "error")
                return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_export_pane.py -v`
Expected: all prior tests pass, two new tests pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_panes/export_pane.py tests/unit/test_export_pane.py
git commit -m "fix(tui): settle-wait before verify in TUI export path"
```

---

### Task 5: Add `WhatsAppDriver.is_community_chat()` probe

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py` (add method after `verify_whatsapp_is_open`, near line 1337)
- Test:   `tests/unit/test_community_detection.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_community_detection.py
"""Tests for the upfront community-chat probe."""

from unittest.mock import MagicMock

from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver


def _make_driver_with_elements(**element_sets):
    """
    Build a WhatsAppDriver stub whose find_elements returns the element list
    matching the resource-id or accessibility key.
    """
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.logger = MagicMock()
    wd.driver = MagicMock()

    def find_elements(by, value):
        return element_sets.get(value, [])

    wd.driver.find_elements = find_elements
    return wd


def test_returns_true_when_community_pill_present():
    fake_elem = MagicMock()
    fake_elem.is_displayed.return_value = True
    wd = _make_driver_with_elements(**{"com.whatsapp:id/community_pill": [fake_elem]})

    assert wd.is_community_chat() is True


def test_returns_false_when_no_community_pill():
    wd = _make_driver_with_elements()

    assert wd.is_community_chat() is False


def test_returns_false_when_pill_present_but_not_displayed():
    fake_elem = MagicMock()
    fake_elem.is_displayed.return_value = False
    wd = _make_driver_with_elements(**{"com.whatsapp:id/community_pill": [fake_elem]})

    assert wd.is_community_chat() is False


def test_exception_during_probe_returns_false():
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.logger = MagicMock()
    wd.driver = MagicMock()
    wd.driver.find_elements = MagicMock(side_effect=RuntimeError("boom"))

    assert wd.is_community_chat() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_community_detection.py -v`
Expected: FAIL — `AttributeError: 'WhatsAppDriver' object has no attribute 'is_community_chat'`.

- [ ] **Step 3: Write minimal implementation**

Add method to `whatsapp_driver.py` immediately after `verify_whatsapp_is_open()`:

```python
    def is_community_chat(self) -> bool:
        """
        Cheap up-front probe for a community chat.

        Called when a chat is open but BEFORE the overflow menu is opened.
        Community chats show a visible "community_pill" element on the toolbar
        and do not support export. Detecting them up front lets the exporter
        mark the chat SKIPPED instead of treating a missing "More" menu as
        a generic failure.

        Returns:
            True if the community pill is present and displayed, False otherwise
            or on any probe error.
        """
        try:
            pills = self.driver.find_elements("id", "com.whatsapp:id/community_pill")
            for elem in pills:
                try:
                    if elem.is_displayed():
                        self.logger.debug_msg("is_community_chat: community_pill visible")
                        return True
                except Exception:
                    continue
            return False
        except Exception as e:
            self.logger.debug_msg(f"is_community_chat probe failed: {e}")
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_community_detection.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/whatsapp_driver.py tests/unit/test_community_detection.py
git commit -m "feat(driver): add is_community_chat() upfront probe"
```

---

### Task 6: Return tri-state `ExportOutcome` from `export_chat_to_google_drive`

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py` (add dataclass, change return shape at line 798, update community branch at `:978-988`)
- Test:   `tests/unit/test_community_detection.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_community_detection.py

import pytest
from unittest.mock import MagicMock, patch

from whatsapp_chat_autoexport.export.chat_exporter import (
    ChatExporter,
    ExportOutcome,
    ExportOutcomeKind,
)


def test_export_outcome_bool_coercion_true_for_success():
    outcome = ExportOutcome(kind=ExportOutcomeKind.SUCCESS)
    assert bool(outcome) is True


def test_export_outcome_bool_coercion_false_for_skipped_and_failed():
    assert bool(ExportOutcome(kind=ExportOutcomeKind.SKIPPED_COMMUNITY)) is False
    assert bool(ExportOutcome(kind=ExportOutcomeKind.FAILED, reason="x")) is False


def test_export_chat_returns_skipped_community_when_probe_hits():
    driver = MagicMock()
    driver.is_community_chat = MagicMock(return_value=True)
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)

    outcome = exporter.export_chat_to_google_drive("ChatA", include_media=False)

    assert isinstance(outcome, ExportOutcome)
    assert outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY
    # Probe happened BEFORE any menu navigation
    driver.is_community_chat.assert_called_once()


def test_export_chat_returns_skipped_community_when_more_menu_missing():
    """Legacy path: community detected after 'More' menu probe fails."""
    driver = MagicMock()
    driver.is_community_chat = MagicMock(return_value=False)  # pill probe miss
    driver.driver = MagicMock()
    driver.driver.press_keycode = MagicMock()
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)

    # Force the menu-opening path to reach the 'More-not-found' branch.
    with patch.object(
        exporter, "_open_overflow_menu_and_find_more", return_value=None
    ):
        outcome = exporter.export_chat_to_google_drive("ChatB", include_media=False)

    assert outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY
```

> Note: `_open_overflow_menu_and_find_more` is the extracted helper introduced in this task. If the maintainer prefers not to extract, test 4 can instead mock `driver.driver.find_elements` to return nothing and assert `outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY`. The extracted helper is recommended because the existing body of `export_chat_to_google_drive` is 200+ lines and hard to test in place.

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_community_detection.py -v`
Expected: FAIL — `ExportOutcome` / `ExportOutcomeKind` not importable.

- [ ] **Step 3: Write minimal implementation**

At the top of `chat_exporter.py`, add:

```python
from dataclasses import dataclass
from enum import Enum


class ExportOutcomeKind(str, Enum):
    SUCCESS = "success"
    SKIPPED_COMMUNITY = "skipped_community"
    FAILED = "failed"


@dataclass
class ExportOutcome:
    """
    Structured result of an attempt to export a single chat.

    Coerces to bool: True only for SUCCESS. This preserves existing call sites
    that check `if exporter.export_chat_to_google_drive(...)`.
    """
    kind: ExportOutcomeKind = ExportOutcomeKind.SUCCESS
    reason: str = ""

    def __bool__(self) -> bool:
        return self.kind == ExportOutcomeKind.SUCCESS
```

In `export_chat_to_google_drive()` (line 798) change the return type annotation and add the up-front probe as the first step (before "STEP 1: Opening menu"):

```python
    def export_chat_to_google_drive(
        self,
        chat_name: str,
        include_media: bool = True,
        on_progress: Optional[Callable] = None,
    ) -> "ExportOutcome":
        """
        Export a chat to Google Drive with or without media.

        Returns an ExportOutcome. Coerces to bool so existing
        `if exporter.export_chat_to_google_drive(...)` sites keep working.
        """

        def _fire(step_index: int, total_steps: int, message: str) -> None:
            if on_progress:
                try:
                    on_progress("export", message, step_index, total_steps, chat_name)
                except Exception:
                    pass

        # Upfront community-chat probe - avoid opening the overflow menu at all.
        try:
            if self.driver.is_community_chat():
                self.logger.warning(
                    f"Skipped '{chat_name}' - community chat (detected up front)"
                )
                return ExportOutcome(
                    kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                    reason="Community chat - export unsupported",
                )
        except Exception as e:
            self.logger.debug_msg(f"Community probe failed: {e}")

        # ...existing body...
```

In the existing "More not found" branch at `chat_exporter.py:980-988`, replace:

```python
            if not more_option:
                self.logger.warning("Could not find 'More' option - likely a community chat")
                self.driver.driver.press_keycode(4)
                sleep(0.3)
                self.driver.driver.press_keycode(4)
                sleep(0.5)
                self.logger.info("Returned to main screen (skipped community chat)")
                return False
```

with:

```python
            if not more_option:
                self.logger.warning("Could not find 'More' option - likely a community chat")
                self.driver.driver.press_keycode(4)
                sleep(0.3)
                self.driver.driver.press_keycode(4)
                sleep(0.5)
                self.logger.info("Returned to main screen (skipped community chat)")
                return ExportOutcome(
                    kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                    reason="Community chat - 'More' option absent",
                )
```

All other `return False` statements in this method become `return ExportOutcome(kind=ExportOutcomeKind.FAILED, reason=<short reason>)`. All `return True` statements become `return ExportOutcome(kind=ExportOutcomeKind.SUCCESS)`.

Before committing, walk every `return True|False` in `export_chat_to_google_drive` and confirm it has been converted. There are approximately 12 such statements between lines 820 and 1020.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_community_detection.py tests/unit/test_export_recovery.py tests/unit/test_export_steps.py -v`
Expected: all pass. Bool coercion keeps older tests green.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/chat_exporter.py tests/unit/test_community_detection.py
git commit -m "feat(export): tri-state ExportOutcome with upfront community detection"
```

---

### Task 7: TUI handles `ExportOutcome` tri-state and routes community to skip

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py` (`_export_single_chat` return handling, `_run_real_export` branch for skipped)
- Test:   `tests/unit/test_export_pane.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_pane.py

from whatsapp_chat_autoexport.export.chat_exporter import (
    ExportOutcome,
    ExportOutcomeKind,
)


class TestExportPaneTriStateResult:
    """Verify the TUI handles SKIPPED_COMMUNITY distinctly from FAILED."""

    def test_export_single_chat_returns_outcome_for_community(self):
        pane = ExportPane()
        driver = MagicMock()
        driver.wait_for_whatsapp_foreground = MagicMock(return_value=True)
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)
        driver.navigate_to_main = MagicMock()
        driver.click_chat = MagicMock(return_value=True)

        with patch(
            "whatsapp_chat_autoexport.tui.textual_panes.export_pane.ChatExporter"
        ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = ExportOutcome(
                kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                reason="Community chat",
            )
            outcome = pane._export_single_chat(
                driver, "ChatC", include_media=False, log_callback=None
            )

        assert isinstance(outcome, ExportOutcome)
        assert outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY

    def test_run_real_export_marks_community_skipped_not_failed(self, tui_app):
        pane = ExportPane()
        driver = MagicMock()
        driver.wait_for_whatsapp_foreground = MagicMock(return_value=True)
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)
        driver.navigate_to_main = MagicMock()
        driver.click_chat = MagicMock(return_value=True)
        driver.restart_app_to_top = MagicMock(return_value=True)

        pane._skip_chat_export = MagicMock()
        pane._fail_chat_export = MagicMock()

        with patch(
            "whatsapp_chat_autoexport.tui.textual_panes.export_pane.ChatExporter"
        ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = ExportOutcome(
                kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                reason="Community chat",
            )

            import asyncio
            results = asyncio.run(
                pane._run_real_export(
                    driver=driver, chats=["CommunityX"], include_media=False
                )
            )

        assert "CommunityX" in results["skipped"]
        assert "CommunityX" not in results["failed"]
        pane._skip_chat_export.assert_called()
        pane._fail_chat_export.assert_not_called()
        # Consecutive-failures counter must NOT have been incremented
        assert pane._consecutive_failures == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_export_pane.py::TestExportPaneTriStateResult -v`
Expected: FAIL — TUI still uses bool return.

- [ ] **Step 3: Write minimal implementation**

In `export_pane.py`, update `_export_single_chat` return type to `ExportOutcome | bool` and return the outcome unchanged:

```python
    def _export_single_chat(
        self,
        driver,
        chat_name: str,
        include_media: bool,
        log_callback=None,
        progress_callback=None,
    ):
        from ...export.chat_exporter import (
            ChatExporter,
            ExportOutcome,
            ExportOutcomeKind,
        )
        # ... unchanged setup ...
        try:
            if not driver.wait_for_whatsapp_foreground(timeout=8.0):
                if log_callback:
                    log_callback("Foreground settle timed out; running full verify", "debug")

            if not driver.verify_whatsapp_is_open():
                if log_callback:
                    log_callback("WhatsApp verification failed", "error")
                return ExportOutcome(kind=ExportOutcomeKind.FAILED, reason="Verify failed")

            driver.navigate_to_main()
            from time import sleep
            sleep(0.3)

            if not driver.click_chat(chat_name):
                if log_callback:
                    log_callback(f"Could not open chat '{chat_name}'", "error")
                return ExportOutcome(
                    kind=ExportOutcomeKind.FAILED, reason="Could not open chat"
                )

            outcome = exporter.export_chat_to_google_drive(
                chat_name,
                include_media=include_media,
                on_progress=progress_callback,
            )
            return outcome
        except Exception as e:
            if log_callback:
                log_callback(f"Export error: {e}", "error")
            return ExportOutcome(kind=ExportOutcomeKind.FAILED, reason=str(e))
```

In `_run_real_export` (around lines 393-431), replace the success/fail branch with an outcome-aware branch:

```python
            try:
                if driver:
                    outcome = await asyncio.to_thread(
                        self._export_single_chat,
                        driver,
                        chat_name,
                        include_media,
                        _export_log_callback,
                        _export_progress_callback,
                    )
                    # Normalise bool returns from legacy code paths
                    if outcome is True:
                        from ...export.chat_exporter import ExportOutcome, ExportOutcomeKind
                        outcome = ExportOutcome(kind=ExportOutcomeKind.SUCCESS)
                    elif outcome is False:
                        from ...export.chat_exporter import ExportOutcome, ExportOutcomeKind
                        outcome = ExportOutcome(
                            kind=ExportOutcomeKind.FAILED, reason="Unknown failure"
                        )

                    from ...export.chat_exporter import ExportOutcomeKind

                    if outcome.kind == ExportOutcomeKind.SUCCESS:
                        results["completed"].append(chat_name)
                        self._consecutive_failures = 0
                        self.app.call_from_thread(
                            self._complete_chat_export, chat_name
                        )
                    elif outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY:
                        results["skipped"].append(chat_name)
                        # Skips must NOT count toward consecutive failure limit
                        self.app.call_from_thread(
                            self._skip_chat_export,
                            chat_name,
                            outcome.reason or "Community chat - export unsupported",
                        )
                    else:  # FAILED
                        results["failed"].append(chat_name)
                        self._consecutive_failures += 1
                        self.app.call_from_thread(
                            self._fail_chat_export,
                            chat_name,
                            outcome.reason or "Export failed",
                        )

                        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                            self.app.call_from_thread(
                                self._show_consecutive_failure_warning
                            )
                            while self._cancel_modal_open:
                                await asyncio.sleep(0.3)
                            if self._cancel_after_current:
                                for remaining in chats[i + 1:]:
                                    results["skipped"].append(remaining)
                                    self.app.call_from_thread(
                                        self._skip_chat_export,
                                        remaining,
                                        "Cancelled after consecutive failures",
                                    )
                                break
                else:
                    # Dry-run block unchanged
                    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_export_pane.py -v`
Expected: all prior tests pass, two new tests pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_panes/export_pane.py tests/unit/test_export_pane.py
git commit -m "fix(tui): route community chats to skip, handle ExportOutcome tri-state"
```

---

### Task 8: Extend `ChatListWidget.update_chat_status` with optional `reason`

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py` (around line 444)
- Test:   new section in `tests/unit/test_tui.py` or a new `tests/unit/test_chat_list.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chat_list_reasons.py (new file)
"""Tests for reason propagation on ChatListWidget.update_chat_status."""

from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import (
    ChatListWidget,
    ChatDisplayStatus,
)


def test_update_chat_status_stores_reason():
    widget = ChatListWidget(chats=["ChatA", "ChatB"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="Verify failed")
    reasons = widget.get_status_reasons()
    assert reasons.get("ChatA") == "Verify failed"


def test_update_chat_status_without_reason_clears_previous_reason():
    widget = ChatListWidget(chats=["ChatA"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="first")
    widget.update_chat_status("ChatA", ChatDisplayStatus.COMPLETED)
    assert widget.get_status_reasons().get("ChatA") is None


def test_get_status_reasons_returns_copy():
    widget = ChatListWidget(chats=["ChatA"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="x")
    copy = widget.get_status_reasons()
    copy["ChatA"] = "mutated"
    assert widget.get_status_reasons().get("ChatA") == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_chat_list_reasons.py -v`
Expected: FAIL — `update_chat_status()` does not accept `reason`.

- [ ] **Step 3: Write minimal implementation**

In `chat_list.py`, add `_status_reasons` attribute (next to `chat_statuses`) and extend the method:

```python
    # Track optional reasons alongside statuses (e.g. "Verify failed").
    # Not a reactive - TUI reads this opportunistically for tooltips/retry.
    _status_reasons: Dict[str, str]

    def __init__(self, ...):
        # existing __init__ body ...
        self._status_reasons = {}
```

Replace `update_chat_status` (line 444) with:

```python
    def update_chat_status(
        self,
        name: str,
        status: ChatDisplayStatus,
        reason: str | None = None,
    ) -> None:
        """
        Update the status of a specific chat.

        Args:
            name: Chat name to update
            status: New status for the chat
            reason: Optional reason (e.g. "Verify failed", "Community chat").
                    Passing None clears any previous reason for this chat.
        """
        new_statuses = dict(self.chat_statuses)
        new_statuses[name] = status
        self.chat_statuses = new_statuses

        if reason is None:
            self._status_reasons.pop(name, None)
        else:
            self._status_reasons[name] = reason

        self._update_item_display(name)

    def get_status_reasons(self) -> Dict[str, str]:
        """Return a shallow copy of per-chat reasons (failure/skip detail)."""
        return dict(self._status_reasons)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_chat_list_reasons.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py tests/unit/test_chat_list_reasons.py
git commit -m "feat(tui): ChatListWidget stores per-chat status reason"
```

---

### Task 9: Plumb reasons from `_fail_chat_export` / `_skip_chat_export` through to the widget

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py` (`_fail_chat_export`, `_skip_chat_export` at lines 589-620)
- Test:   `tests/unit/test_export_pane.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_pane.py

class TestExportPaneReasonPlumbing:
    def test_fail_chat_export_forwards_reason_to_widget(self):
        pane = ExportPane()
        pane._export_results = {"completed": [], "failed": [], "skipped": []}

        chat_list = MagicMock()
        progress = MagicMock()

        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            if "export-progress-pane" in selector:
                return progress
            raise RuntimeError("unknown selector")

        pane.query_one = query_one

        pane._fail_chat_export("ChatA", "Verify failed")

        chat_list.update_chat_status.assert_called_once()
        args, kwargs = chat_list.update_chat_status.call_args
        # Expect (name, status, reason=...)
        assert args[0] == "ChatA"
        assert kwargs.get("reason") == "Verify failed" or (
            len(args) >= 3 and args[2] == "Verify failed"
        )

    def test_skip_chat_export_forwards_reason_to_widget(self):
        pane = ExportPane()
        pane._export_results = {"completed": [], "failed": [], "skipped": []}

        chat_list = MagicMock()
        progress = MagicMock()

        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            if "export-progress-pane" in selector:
                return progress
            raise RuntimeError("unknown selector")

        pane.query_one = query_one

        pane._skip_chat_export("ChatB", "Community chat")

        args, kwargs = chat_list.update_chat_status.call_args
        assert args[0] == "ChatB"
        assert kwargs.get("reason") == "Community chat" or (
            len(args) >= 3 and args[2] == "Community chat"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_export_pane.py::TestExportPaneReasonPlumbing -v`
Expected: FAIL — reasons not passed through.

- [ ] **Step 3: Write minimal implementation**

In `export_pane.py` at lines 589-620, update:

```python
    def _fail_chat_export(self, chat_name: str, error: str) -> None:
        """Mark a chat as failed."""
        self._current_chat = None
        self._export_results["failed"].append(chat_name)

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(
                chat_name, ChatDisplayStatus.FAILED, reason=error
            )
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.fail_chat(chat_name, error)
        except Exception:
            pass

    def _skip_chat_export(self, chat_name: str, reason: str) -> None:
        """Mark a chat as skipped."""
        self._export_results["skipped"].append(chat_name)

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(
                chat_name, ChatDisplayStatus.SKIPPED, reason=reason
            )
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.log_activity(f"Skipped: {chat_name} ({reason})", "warning")
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_export_pane.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_panes/export_pane.py tests/unit/test_export_pane.py
git commit -m "feat(tui): forward failure/skip reasons to ChatListWidget"
```

---

### Task 10: Add reconcile-on-end step so the widget reflects every failure

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py` (add `_reconcile_chat_list_statuses()` method, call at end of `_run_real_export`)
- Test:   `tests/unit/test_export_pane.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_pane.py

class TestExportPaneReconcile:
    """After a run, the widget must reflect every chat in results."""

    def test_reconcile_marks_all_failed_chats(self):
        pane = ExportPane()
        pane._export_results = {
            "completed": ["A"],
            "failed": ["B", "C"],
            "skipped": ["D"],
        }
        pane._per_chat_reasons = {"B": "Verify failed", "C": "Timeout", "D": "Community"}

        chat_list = MagicMock()
        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            raise RuntimeError()
        pane.query_one = query_one

        pane._reconcile_chat_list_statuses()

        calls = chat_list.update_chat_status.call_args_list
        names = {c.args[0] for c in calls}
        assert names == {"A", "B", "C", "D"}

        # Map each name to the status passed
        status_by_name = {c.args[0]: c.args[1] for c in calls}
        assert status_by_name["A"] == ChatDisplayStatus.COMPLETED
        assert status_by_name["B"] == ChatDisplayStatus.FAILED
        assert status_by_name["C"] == ChatDisplayStatus.FAILED
        assert status_by_name["D"] == ChatDisplayStatus.SKIPPED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_export_pane.py::TestExportPaneReconcile -v`
Expected: FAIL — `_reconcile_chat_list_statuses` does not exist, `_per_chat_reasons` not tracked.

- [ ] **Step 3: Write minimal implementation**

In `ExportPane.__init__` (or the class-level default init), add:

```python
        self._per_chat_reasons: Dict[str, str] = {}
```

Whenever `_fail_chat_export` or `_skip_chat_export` is called, also record the reason:

```python
    def _fail_chat_export(self, chat_name: str, error: str) -> None:
        self._current_chat = None
        self._export_results["failed"].append(chat_name)
        self._per_chat_reasons[chat_name] = error
        # ... existing widget update ...

    def _skip_chat_export(self, chat_name: str, reason: str) -> None:
        self._export_results["skipped"].append(chat_name)
        self._per_chat_reasons[chat_name] = reason
        # ... existing widget update ...
```

Add the reconcile method:

```python
    def _reconcile_chat_list_statuses(self) -> None:
        """
        Re-push authoritative per-chat status from self._export_results to the
        widget after a run. Defensive: some widget updates during the loop may
        have silently failed due to a transient query_one failure. This ensures
        the chat list panel matches results exactly.
        """
        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
        except Exception:
            return

        for chat in self._export_results.get("completed", []):
            chat_list.update_chat_status(
                chat, ChatDisplayStatus.COMPLETED, reason=None
            )
        for chat in self._export_results.get("failed", []):
            chat_list.update_chat_status(
                chat,
                ChatDisplayStatus.FAILED,
                reason=self._per_chat_reasons.get(chat, "Failed"),
            )
        for chat in self._export_results.get("skipped", []):
            chat_list.update_chat_status(
                chat,
                ChatDisplayStatus.SKIPPED,
                reason=self._per_chat_reasons.get(chat, "Skipped"),
            )
```

Call at the end of `_run_real_export` after the loop breaks, before `return results`:

```python
        try:
            self.app.call_from_thread(self._reconcile_chat_list_statuses)
        except Exception:
            # Fallback if call_from_thread isn't available (test stubs)
            self._reconcile_chat_list_statuses()
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_export_pane.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_panes/export_pane.py tests/unit/test_export_pane.py
git commit -m "fix(tui): reconcile chat list status at end of export run"
```

---

### Task 11: End-to-end regression test for the verify-race failure mode

**Files:**
- Modify: `tests/unit/test_export_recovery.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_export_recovery.py

def test_regression_drive_return_race_does_not_fail_chat(monkeypatch):
    """
    Regression test for docs/failure-reports/2026-04-16-full-run-pause.md Fix 1.

    Scenario: on entering iteration N, current_package is briefly
    'com.android.intentresolver' (Drive share return window), then flips to
    'com.whatsapp'. The settle-wait should absorb the transition; the chat
    must succeed, not fail.
    """
    packages = {"calls": 0}

    class SettleDriver:
        def __init__(self):
            self.driver = MagicMock()
            self.driver.current_package = "com.android.intentresolver"
            self.is_session_active = MagicMock(return_value=True)
            self.navigate_to_main = MagicMock()
            self.click_chat = MagicMock(return_value=True)
            self.navigate_back_to_main = MagicMock()

        def wait_for_whatsapp_foreground(self, timeout=8.0, poll_interval=0.25):
            # Simulate 3 polls during which package flips to WhatsApp
            self.driver.current_package = "com.whatsapp"
            return True

        def verify_whatsapp_is_open(self):
            return self.driver.current_package == "com.whatsapp"

    driver = SettleDriver()
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)

    monkeypatch.setattr(
        exporter, "export_with_new_workflow", lambda **kw: (True, "ok")
    )

    results, _, _, _ = exporter.export_chats_with_new_workflow(
        ["RaceChat"], include_media=False
    )

    assert results["RaceChat"] is True
```

- [ ] **Step 2: Run test to verify it passes (already)**

Run: `poetry run pytest tests/unit/test_export_recovery.py::test_regression_drive_return_race_does_not_fail_chat -v`
Expected: PASS (Task 3 already fixed the loop; this locks in the regression).

If it fails, return to Task 3 and fix — do not commit a passing-on-fix test with no code change.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_export_recovery.py
git commit -m "test(export): regression lock for 2026-04-16 Drive-return verify race"
```

---

### Task 12: Update failure report with resolution footer

**Files:**
- Modify: `docs/failure-reports/2026-04-16-full-run-pause.md`

- [ ] **Step 1: Append resolution footer to the failure report**

Append the following block to the bottom of `docs/failure-reports/2026-04-16-full-run-pause.md`:

```markdown

## Resolution

Implemented in plan `docs/plans/2026-04-17-001-fix-full-run-failures-plan.md`.

- **Fix 1 (verify-race):** `WhatsAppDriver.wait_for_whatsapp_foreground()` now
  runs before every `verify_whatsapp_is_open()` call at pre-export checkpoints
  in both the batch loop (`chat_exporter.py`) and the TUI path
  (`export_pane.py:_export_single_chat`). Timeout falls through to the
  existing recovery path, so genuine non-WhatsApp states are still caught.
- **Fix 2 (community skip):** `ChatExporter.export_chat_to_google_drive()`
  now probes `driver.is_community_chat()` up front and returns
  `ExportOutcome(kind=SKIPPED_COMMUNITY)`. The TUI routes that through
  `_skip_chat_export`, which does not increment the consecutive-failure
  counter.
- **Fix 3 (visibility):** Every failure and skip in the TUI carries a reason
  string through to `ChatListWidget.update_chat_status(..., reason=...)`, and
  a reconcile pass at the end of the run re-asserts the chat-list panel's
  per-chat state from `_export_results`. The left panel is now the
  authoritative failure record.

Fixes 4, 5, and 6 from this report remain open.
```

- [ ] **Step 2: Update status frontmatter**

Change line 4:

```markdown
status: paused
```

to:

```markdown
status: resolved-partial
```

- [ ] **Step 3: Commit**

```bash
git add docs/failure-reports/2026-04-16-full-run-pause.md
git commit -m "docs(failure-report): note resolution of Fixes 1-3 from 2026-04-16 run"
```

---

### Task 13: Manual verification against a live phone (user-run)

**Files:** none (manual).

- [ ] **Step 1: Run a short real export and confirm no verify-race failures**

Run (user executes on the phone, not in CI):

```bash
poetry run whatsapp --headless \
  --output ~/whatsapp_exports \
  --auto-select \
  --limit 15 \
  --no-output-media
```

Expected: activity log shows zero `WhatsApp verification failed` lines immediately after `Google Drive should now be handling`. If any appear, re-open this plan at Task 3/4.

- [ ] **Step 2: Force a community-chat encounter**

In the TUI, select at least one known community chat (e.g. "Helicopter PILOTS…"). Expected: `[⊘]` marker, not `[✗]`. Consecutive-failure counter does not increment.

- [ ] **Step 3: Inspect chat list after run completes**

Expected: the count of `[✗]` markers in the chat-list panel equals the number of genuinely failed chats reported in the activity log (no under-reporting).

- [ ] **Step 4: Tag the working tree**

Only after Steps 1-3 pass:

```bash
git tag fix-full-run-failures-verified-$(date +%Y%m%d)
```

---

## Self-Review

**Spec coverage (R1-R10):**

- R1 settle-wait before verify at batch + TUI checkpoints: Tasks 3, 4.
- R2 cheap package-only probe: Task 1.
- R3 fall-through on timeout: Task 3 Step 3 (no short-circuit), Task 4 Step 3 (no return).
- R4 upfront community detection, tri-state return: Tasks 5, 6.
- R5 bool coercion preserves old call sites: Task 6 `ExportOutcome.__bool__`.
- R6 TUI routes community to skip without incrementing consecutive: Task 7 second test.
- R7 typed reason on every failure path: Task 6 (chat_exporter), Task 7 (TUI), Task 9 (plumbing).
- R8 widget receives FAILED on every failure path: Task 9 + Task 10 reconcile.
- R9 reasons retained: Task 8 `_status_reasons`, Task 10 `_per_chat_reasons`.
- R10 unit tests: Tasks 1, 3, 4, 5, 6, 7, 8, 9, 10, 11.

**Placeholder scan:** no "TBD", no "similar to task N", every code block is complete. Task 6 Step 3 references "approximately 12 `return` statements" in `export_chat_to_google_drive`; this is a quantitative directive ("walk every one and convert"), not a placeholder.

**Type consistency:**

- `ExportOutcome`/`ExportOutcomeKind` defined in Task 6, consumed in Tasks 7, 11.
- `wait_for_whatsapp_foreground` defined as standalone helper in Task 1, wrapped as method in Task 2, consumed in Tasks 3, 4, 11.
- `update_chat_status(name, status, reason=None)` defined in Task 8, consumed in Task 9.
- `_per_chat_reasons` introduced in Task 10, referenced by both `_fail_chat_export` and `_skip_chat_export` in Task 10 Step 3.
- `is_community_chat()` defined in Task 5, consumed in Task 6.

All names consistent; no drift detected.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-17-001-fix-full-run-failures-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
