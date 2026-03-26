---
title: "fix: Restore session recovery logic to export batch loop"
type: fix
status: active
date: 2026-03-26
deepened: 2026-03-26
---

# fix: Restore session recovery logic to export batch loop

## Overview

The refactored `export/chat_exporter.py` lost two critical recovery mechanisms that existed in the original `whatsapp_export.py`: pre-export reconnection on verification failure, and post-export session health checks. This caused a full batch abort at chat 219/409 when UiAutomator2 crashed, leaving 189 chats unprocessed.

## Problem Frame

During an overnight export of 409 chats, the UiAutomator2 instrumentation process on the phone crashed while exporting the "Footvolley try it out group" chat. The crash left `com.android.intentresolver` (Android's share dialog) as the active package. On the next chat iteration, `verify_whatsapp_is_open()` detected the wrong package and the batch loop immediately broke — no recovery was attempted.

The original monolith at `whatsapp_export.py:2491-2507` handled this exact scenario: it called `reconnect()` before breaking, which creates a fresh Appium session and relaunches WhatsApp. The post-export health check at `whatsapp_export.py:2558-2565` would have caught the session death even sooner. Neither pattern was carried forward during the modular refactor.

## Requirements Trace

- R1. When `verify_whatsapp_is_open()` fails at the top of the export loop, attempt session recovery via `reconnect()` before aborting the batch
- R2. After each successful chat export, proactively check session health with `is_session_active()` and recover if needed
- R3. When an exception during export suggests a session-level crash (not just a UI navigation failure), attempt recovery before continuing to the next chat
- R4. Recovery logic must be safe: no data loss, no accidental system UI interaction, bounded retry count
- R5. Both `export_chats()` and `export_chats_with_new_workflow()` must have the same recovery behavior

## Scope Boundaries

- This plan does NOT add automatic re-pairing for wireless ADB disconnections (that requires user interaction for pairing codes)
- This plan does NOT add a retry of the specific chat that was being exported when the crash occurred — it recovers the session and moves to the next chat
- This plan does NOT change the Appium server management or driver connection architecture
- This plan does NOT add external monitoring or alerting
- This plan does NOT fix the pre-existing issue where `poll_for_new_export()` matches ANY recent WhatsApp export rather than the specific chat name (see Known Pre-Existing Issues below)
- This plan does NOT change the Drive deletion timing (currently deletes before archive validation — a separate fix)

## Context & Research

### Relevant Code and Patterns

- **Recovery building blocks already exist** in `whatsapp_driver.py`:
  - `reconnect()` (line 434): Checks ADB, quits dead session, creates new session via `connect()`, relaunches WhatsApp
  - `is_session_active()` (line 417): Lightweight check — tries `self.driver.current_package`
  - `safe_driver_call()` (line 506): Retry wrapper with automatic session recovery for individual operations
  - `restart_app_to_top()` (line 1265): Force-stop + relaunch WhatsApp (preserves Appium session)

- **The old monolith has the exact pattern needed** in `whatsapp_export.py`:
  - Lines 2491-2507: Pre-export reconnect-then-verify
  - Lines 2558-2565: Post-export `is_session_active()` + `reconnect()` health check
  - Note: The old monolith's exception handler (lines 2567-2579) also has the bare `pass` gap — it did not add session-aware recovery there either. Unit 2 in this plan goes beyond the old code.

- **Current refactored code** in `chat_exporter.py`:
  - Lines 1465-1471 (`export_chats`): Hard `break` on verify failure, no reconnect
  - Lines 401-412 (`export_chats_with_new_workflow`): Hard `break` on verify failure, no reconnect
  - Lines 1547-1559 (`export_chats` exception handler): Catches per-chat errors and continues, but no session recovery. The `navigate_back_to_main()` call in the handler will silently fail if the session is dead (wrapped in bare `try/except: pass`), leaving the dead session for the next iteration's verify to catch.
  - Lines 461-473 (`export_chats_with_new_workflow` exception handler): Same pattern, no session recovery

- **Both export methods are actively used**: `export_chats_with_new_workflow()` is called from `cli/commands/export.py:301-307` when `use_new_workflow=True`. Both code paths are live.

- **The two export methods are structurally near-identical** — same loop skeleton (verify → resume-check → navigate → export → handle-error → report-timing). They differ only in: (a) which export method is called, (b) whether `StateManager` tracking fires, and (c) whether pipeline processing runs inline.

### Why Recovery Is Safe

- `reconnect()` calls `self.driver.quit()` on the dead session (safe even if already dead), then `connect()` which creates a fresh UiAutomator2 session
- `connect()` uses `noReset: True` — no WhatsApp data is touched
- The Appium server process is independent of WebDriver sessions — a session crash doesn't affect the server
- ADB connection is independent of both — wireless ADB stays connected even when UiAutomator2 crashes
- After reconnect, the script lands on WhatsApp's main chat screen in a known-good state
- `navigate_to_main()` at the top of the try block correctly handles the post-reconnect state — it detects "Already on main chats screen!" and proceeds

### Google Drive Upload Interaction

- `connect()` force-stops `com.whatsapp`, NOT `com.google.android.apps.docs`. Once the share intent dispatches the export to Google Drive, the upload continues in Google Drive's own process regardless of WhatsApp state
- If the crash happens BEFORE "Upload" was clicked, no file reaches Drive — `export_chat_to_google_drive()` throws an exception and `process_single_export()` is never called. Safe.
- If the crash happens AFTER "Upload" was clicked, the Drive upload proceeds independently. The pipeline's `process_single_export()` may or may not have been called yet (depends on whether the exception occurred before or after the export method returned)
- Edge case: if WhatsApp is still writing the temporary export file when force-stopped, the file could be truncated. Drive would upload a partial file. The `archive_extractor.py` validates zip integrity via `zf.testzip()` and catches `BadZipFile`, so corrupt files are detected during extraction

### Session-Error Keywords

The `safe_driver_call()` method at `whatsapp_driver.py:528-534` uses an overly broad keyword list that includes standalone `"session"` and `"terminated"` as substrings — these would false-match on errors like "Permission session denied". The precise Appium/WebDriver error signatures are:

- `"session is either terminated"` — standard Appium session-dead error
- `"nosuchdrivererror"` — WebDriver session not found
- `"invalidsessionid"` — WebDriver invalid session
- `"instrumentation process is not running"` — UiAutomator2 crashed (the exact error from our incident)
- `"cannot be proxied"` — Appium can't forward to UiAutomator2 (always accompanies the above)
- `"socket hang up"` — connection to UiAutomator2 dropped mid-request

### Known Pre-Existing Issues (Out of Scope)

These were surfaced during deepening research. They are real but separate from this fix:

1. **`poll_for_new_export()` matches ANY recent WhatsApp export**, not the specific chat name. With recovery introducing interleaved export attempts, a wrong file could theoretically be picked up. Low practical risk since recovery skips the crashed chat and moves to the next one, but worth a separate fix.
2. **`delete_from_drive` happens before archive validation** in `batch_download_exports()`. A corrupt file from a crash-interrupted upload would be downloaded, deleted from Drive, then fail extraction — losing the source data. Also worth a separate fix.

## Key Technical Decisions

- **Port the old pattern, don't invent a new one**: The recovery logic in `whatsapp_export.py:2491-2507` and `2558-2565` is proven. Carry it forward to `chat_exporter.py`.
- **Extract a shared helper method**: Both `export_chats()` and `export_chats_with_new_workflow()` have near-identical loop skeletons. Rather than duplicating recovery logic in both, extract an `_attempt_session_recovery()` helper that encapsulates the reconnect-then-verify pattern and consecutive-failure tracking. Both methods call the same helper.
- **Max 1 reconnect attempt per verification failure**: Matches the old code. If reconnect + re-verify both fail, the batch truly cannot continue.
- **Skip the crashed chat, don't retry it**: The chat that caused the crash may have a structural issue (community chat, privacy restriction, corrupt export). Retrying it risks an infinite crash loop. Mark it failed and move on.
- **Add session-crash detection to the exception handler**: When an exception contains session-error keywords, attempt recovery instead of just `continue`-ing with a dead session. This goes beyond the old monolith (which also had the bare `pass` gap here).
- **Use precise session-error keywords**: Extract a `SESSION_ERROR_KEYWORDS` constant in `whatsapp_driver.py` containing the 6 precise signatures listed above. Both `safe_driver_call()` and the export exception handler reference the same constant. This avoids the false-match risk of the current overly broad list.
- **Configurable max consecutive failures (default: 3)**: A safety valve to prevent burning through remaining chats with a fundamentally broken connection. The value 3 is chosen because: (1) a single transient crash should recover on the first attempt, (2) two consecutive crashes could indicate an unlucky sequence, (3) three consecutive failures strongly suggests a systemic issue (phone overheating, memory exhaustion, persistent UiAutomator2 incompatibility). The constant is a class attribute for easy adjustment.

## Open Questions

### Resolved During Planning

- **Should we retry the crashed chat?**: No. The crash may be chat-specific (e.g., large media triggering OOM on UiAutomator2). Skip it and continue. The user can retry individually later.
- **Should we add backoff delays between reconnect attempts?**: The existing `reconnect()` already has a 2-second sleep. No additional backoff needed for a single attempt.
- **Should `export_chats_with_new_workflow` get the same fix?**: Yes (R5). Both methods are actively used (called from `cli/commands/export.py:301-307`).
- **Should we extract a shared helper or duplicate the code?**: Extract a helper. The two methods have near-identical loop skeletons; duplicating recovery logic would create maintenance drift.
- **What about the `safe_driver_call()` keyword list?**: Replace the overly broad list with precise keywords and extract to a shared constant.

### Deferred to Implementation

- **State manager integration in new workflow**: The `export_chats_with_new_workflow` method uses `state_manager.fail_chat()` when verification fails. The recovery path should log the recovery attempt in the state manager too, if natural.

## Implementation Units

- [ ] **Unit 1: Extract session-error keywords and recovery helper**

**Goal:** Create the shared infrastructure for session recovery: a precise keyword constant and a helper method that both export methods will call.

**Requirements:** R4, R5

**Dependencies:** None

**Files:**
- Modify: `whatsapp_chat_autoexport/export/whatsapp_driver.py`
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py`
- Test: `tests/unit/test_export_recovery.py`

**Approach:**
- Add a module-level `SESSION_ERROR_KEYWORDS` tuple in `whatsapp_driver.py` containing the 6 precise signatures: `"session is either terminated"`, `"nosuchdrivererror"`, `"invalidsessionid"`, `"instrumentation process is not running"`, `"cannot be proxied"`, `"socket hang up"`
- Update `safe_driver_call()` to reference the shared constant instead of its inline list
- Add `_attempt_session_recovery(self, context: str) -> bool` method to `ChatExporter` that:
  1. Logs a warning with context (e.g., "Pre-export verification failed", "Post-export session check failed", "Session error during export of 'Chat Name'")
  2. Calls `self.driver.reconnect()`
  3. If reconnect succeeds, calls `self.driver.verify_whatsapp_is_open()`
  4. Returns True if both succeed, False otherwise
  5. Increments `self._consecutive_recovery_count` on success, logs error on failure
- Add `_is_session_error(self, error_msg: str) -> bool` helper that checks the lowercased error against `SESSION_ERROR_KEYWORDS`
- Add `MAX_CONSECUTIVE_RECOVERIES = 3` class attribute to `ChatExporter`
- Add `_check_consecutive_recovery_limit(self) -> bool` helper that returns True if the limit has been reached (and logs the error)

**Patterns to follow:**
- `safe_driver_call()` at `whatsapp_driver.py:506` for keyword detection
- `whatsapp_export.py:2491-2507` for the reconnect-then-verify flow

**Test scenarios:**
- `_attempt_session_recovery()` with successful reconnect + verify → returns True
- `_attempt_session_recovery()` with successful reconnect but failed verify → returns False
- `_attempt_session_recovery()` with failed reconnect → returns False
- `_is_session_error()` with each of the 6 keywords → returns True
- `_is_session_error()` with "community" or generic errors → returns False
- `_check_consecutive_recovery_limit()` trips at exactly 3

**Verification:**
- The keyword constant is used by both `safe_driver_call()` and the export recovery logic
- The helper method encapsulates the complete reconnect-then-verify flow

---

- [ ] **Unit 2: Add recovery to `export_chats()`**

**Goal:** Wire the recovery helper into `export_chats()` at all three insertion points: pre-export verify guard, exception handler, and post-export health check.

**Requirements:** R1, R2, R3, R4

**Dependencies:** Unit 1

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py`
- Test: `tests/unit/test_export_recovery.py`

**Approach:**

*Pre-export verify guard (lines 1465-1471):*
- When `verify_whatsapp_is_open()` fails, call `_attempt_session_recovery("Pre-export verification failed")`
- If recovery succeeds: `continue` to next iteration (the `verify_whatsapp_is_open()` at the top will re-check)
- If recovery fails OR consecutive limit reached: `break`
- Log a warning on initial failure, error only if recovery also fails

*Exception handler (lines 1547-1559):*
- Before the existing community/more check, check `_is_session_error(error_msg)`
- If session error: call `_attempt_session_recovery(f"Session error during export of '{chat_name}'")`
  - If recovery succeeds and not at consecutive limit: `continue` (skip to next chat)
  - If recovery fails OR at limit: `break`
- If not a session error: existing behavior (try navigate back, continue)

*Post-export health check (after pipeline processing, around line 1545):*
- After a successful export+pipeline, call `self.driver.is_session_active()`
- If inactive: call `_attempt_session_recovery("Post-export session check failed")`
  - If recovery fails OR at limit: `break`
  - If recovery succeeds: continue to next chat
- If active: reset `_consecutive_recovery_count` to 0 (a fully successful chat resets the counter)

**Patterns to follow:**
- `whatsapp_export.py:2491-2507` for pre-export recovery flow
- `whatsapp_export.py:2558-2565` for post-export health check

**Test scenarios:**
- Pre-export verify fails, recovery succeeds → loop continues to next chat
- Pre-export verify fails, recovery fails → batch breaks
- Exception with session error, recovery succeeds → loop continues
- Exception with "community" → normal skip, no recovery attempted
- Post-export session inactive, recovery succeeds → continues
- Post-export session inactive, recovery fails → batch breaks
- Successful chat export → consecutive counter resets to 0
- 3 consecutive recoveries without success → batch breaks with clear message

**Verification:**
- The batch loop no longer hard-breaks on a single transient failure
- All three recovery paths use the shared helper
- The consecutive failure safety valve prevents infinite recovery loops

---

- [ ] **Unit 3: Add recovery to `export_chats_with_new_workflow()`**

**Goal:** Wire the same recovery helper into `export_chats_with_new_workflow()` at the same three insertion points.

**Requirements:** R1, R2, R3, R5

**Dependencies:** Units 1-2

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py`
- Test: `tests/unit/test_export_recovery.py`

**Approach:**
- Apply the same three insertion points as Unit 2 to `export_chats_with_new_workflow()` at lines 401-412 (verify guard) and 461-473 (exception handler)
- For the post-export health check: insert after line 459 (`results[chat_name] = success`), before the exception handler
- Note: this method does NOT have inline pipeline processing, so the post-export check is simpler
- Include state manager integration: when recovery is attempted, call `state_manager.fail_chat(chat_name, "Session recovered - skipping to next chat")` if natural

**Patterns to follow:**
- The recovery code added to `export_chats()` in Unit 2

**Test scenarios:**
- Same scenarios as Unit 2 but exercised through `export_chats_with_new_workflow()`
- State manager receives appropriate status updates during recovery

**Verification:**
- Both export methods have identical resilience to session crashes
- State manager correctly reflects recovery events

## System-Wide Impact

- **Interaction graph:** `export_chats()` → `verify_whatsapp_is_open()` → `_attempt_session_recovery()` → `reconnect()` → `connect()`. The `connect()` method force-stops and relaunches WhatsApp, which resets the UI state. Any in-progress share dialog or export will be abandoned (this is the desired behavior after a crash).
- **Error propagation:** Recovery failures propagate up as a batch `break`, which is the existing behavior. No new exception types or failure modes are introduced.
- **State lifecycle risks:** After reconnect, the phone may be on any screen. The `connect()` method handles this by force-stopping WhatsApp and relaunching to main screen. The export loop then calls `navigate_to_main()` before clicking into the next chat. `navigate_to_main()` correctly detects "Already on main chats screen!" after a reconnect and proceeds without unnecessary navigation.
- **API surface parity:** Both `export_chats()` and `export_chats_with_new_workflow()` get identical recovery logic via the shared helper.
- **Google Drive interaction:** `connect()` force-stops `com.whatsapp`, not `com.google.android.apps.docs`. Once the share intent dispatches the export to Drive, the upload continues independently. If the crash happened before the upload was initiated, no file reaches Drive and `process_single_export()` is never called. If the upload was already initiated, it completes in Drive's process. Corrupt/truncated uploads are caught by `archive_extractor.py`'s zip validation (`zf.testzip()` + `BadZipFile` handling).
- **Integration coverage:** The `_attempt_session_recovery()` helper should be tested with mocked `reconnect()` and `verify_whatsapp_is_open()` — no real device needed for unit tests.

## Risks & Dependencies

- **Risk: Reconnect itself could hang** — `connect()` has a `newCommandTimeout` of 3600s (1 hour). If the Appium server is unresponsive, reconnect will block for a long time. Mitigation: this is the existing timeout behavior and hasn't been a problem. The Appium server runs independently and is resilient to UiAutomator2 crashes.
- **Risk: Wireless ADB drops during reconnect** — `reconnect()` checks ADB connection first and fails fast if ADB is gone. This is already handled.
- **Risk: WhatsApp state after crash** — After UiAutomator2 crashes, WhatsApp may be in an inconsistent state (share dialog open, export in progress). `connect()` force-stops WhatsApp before relaunching, which cleans this up.
- **Risk: Keyword false-positives in exception handler** — Using precise multi-word signatures (e.g., `"instrumentation process is not running"`) rather than single words (e.g., `"session"`) minimizes false-match risk. The extracted constant makes the keyword list auditable and maintainable.
- **Risk: Crash-interrupted upload leaves corrupt file on Drive** — Pre-existing issue (see Known Pre-Existing Issues in Scope Boundaries). The archive extractor validates zip integrity, so corrupt files are caught during extraction. With `--delete-from-drive`, the corrupt file would be deleted before extraction fails — this is a data-loss risk from the pre-existing deletion timing issue, not from this recovery change.

## Sources & References

- Old recovery pattern: `whatsapp_export.py:2491-2507` (pre-export reconnect)
- Old health check: `whatsapp_export.py:2558-2565` (post-export session check)
- Recovery infrastructure: `whatsapp_driver.py:434` (`reconnect()`), `whatsapp_driver.py:417` (`is_session_active()`)
- Session error keywords: `whatsapp_driver.py:528-534` (`safe_driver_call()` keyword list)
- Both-methods-are-live evidence: `cli/commands/export.py:301-307` (dispatch between old and new workflow)
- Crash log: `.logs/whatsapp_export.log` lines 32108-32162 (the UiAutomator2 crash event)
- Archive validation: `processing/archive_extractor.py:18-43` (`is_zip_file()` with `testzip()`)
