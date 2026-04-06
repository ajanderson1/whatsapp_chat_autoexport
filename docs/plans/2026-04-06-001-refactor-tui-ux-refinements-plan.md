---
title: "refactor: TUI UX refinements — discovery timing, tab rename, summary cancel"
type: refactor
status: completed
date: 2026-04-06
origin: docs/brainstorms/2026-04-06-tui-ux-refinements-requirements.md
---

# refactor: TUI UX refinements — discovery timing, tab rename, summary cancel

## Overview

Three targeted UX improvements to the tabbed TUI shipped in PR #15:

1. **Discovery timing** — Move the chat discovery trigger from Tab 2's `on_show` to Tab 1's connection handler, so discovery auto-starts on connection and streams results into Tab 2 in real time.
2. **Tab rename** — Rename "Discover & Select" to "Select" since discovery is now auto-triggered.
3. **Summary cancel** — Add a Cancel button to Tab 4 (Summary) that stops the processing pipeline and shows partial results.

## Problem Frame

After PR #15, the TUI workflow timing is off. Discovery only starts when Tab 2 becomes visible, creating a perceptible delay after connection. The tab name "Discover & Select" is misleading since discovery will be automatic. The Summary tab has no way to cancel a long-running pipeline. (see origin: docs/brainstorms/2026-04-06-tui-ux-refinements-requirements.md)

## Requirements Trace

- R1. Auto-start discovery on connection, advance to Tab 2
- R2. Stream discovered chats into Tab 2 in real time, interactive during discovery
- R3. Refresh button remains on Tab 2
- R4. Start Export cancels discovery if running, exports selected subset
- R5. Export advances to Tab 3, runs in background (existing, no change)
- R6. Export completion auto-advances to Tab 4 (existing, no change)
- R7. Export cancel returns to Tab 2 (existing, no change)
- R8. Cancel button on Tab 4 stops pipeline processing
- R9. After cancel, stay on Tab 4 with partial results
- R10. Rename tab "Discover & Select" → "Select"

## Scope Boundaries

- Not changing the 4-tab structure or navigation model
- Not changing export logic, pipeline logic, or Appium automation
- Not changing headless mode or CLI flags
- Not redesigning widget layouts within tabs

## Context & Research

### Relevant Code and Patterns

- **Message pattern**: Panes define nested `Message` subclasses, post via `self.post_message()`, handled in `MainScreen` via `on_<pane>_<message>` naming convention
- **Worker pattern**: `self.run_worker(callable, thread=True)` with `self.app.call_from_thread()` for thread-safe UI updates. Worker completion routed via `on_worker_state_changed` dispatching on `worker.name`
- **Cancel pattern in ExportPane**: `CancelModal` pushed via `self.app.push_screen(modal, callback)`. Modal returns button IDs. Cooperative cancellation via `_cancel_after_current` flag checked in per-item loop. Direct cancellation via `worker.cancel()`
- **Reactive cascade**: `_connected` → `_has_selection` → `_export_complete` in MainScreen, each watcher cascades resets downward
- **Discovery live-streaming**: `_collect_chats` uses `call_from_thread(self._add_discovered_chat, name, generation)` with `_discovery_generation` counter for stale callback protection
- **Tab label pattern**: Labels defined in `MainScreen.compose()` as `TabPane("1 Connect", id="connect")` etc.

### Institutional Learnings

No `docs/solutions/` directory exists in this repo.

## Key Technical Decisions

- **MainScreen triggers discovery via direct method call**: After storing the driver and setting `_connected = True`, `MainScreen.on_connect_pane_connected` calls `discover_select_pane.start_discovery()` directly, then switches to the tab. This is simpler than adding a new Message type and follows the existing pattern where MainScreen calls `export_pane.start_export()` and `summary_pane.start_processing()` directly. The DiscoverSelectPane's `on_show` / `_first_show` auto-trigger is removed.

- **Worker.cancel() for pipeline cancellation**: The processing pipeline runs as a single `asyncio.to_thread(pipeline.run, ...)` call — there's no per-item loop to check a cooperative flag. `worker.cancel()` raises `CancelledError`, which the existing `on_worker_state_changed` handler can catch. Partial results are captured from whatever state variables were updated before cancellation.

- **No CancelModal for Summary**: The ExportPane's CancelModal offers "wait for current chat" and "return to selection" options that don't apply to pipeline processing. A simple confirmation dialog or direct cancel (with the button changing to "Cancelling...") is sufficient. Pipeline phases are fast enough that "cancel after current phase" isn't meaningfully different from immediate cancel.

## Open Questions

### Resolved During Planning

- **Discovery trigger mechanism** (from origin doc): Resolved as direct method call from MainScreen, matching the existing `start_export()` and `start_processing()` patterns.
- **Pipeline cancel mechanism** (from origin doc): Resolved as `worker.cancel()` with `CANCELLED` state handling in `on_worker_state_changed`.

### Deferred to Implementation

- **Partial results granularity**: The exact structure of partial results after pipeline cancellation depends on which pipeline phases set which result keys. Implementer should trace the `_run_processing` method to identify what's available at each phase.

## Implementation Units

- [x] **Unit 1: Rename tab and update references**

  **Goal:** Rename "Discover & Select" tab to "Select" and update all references.

  **Requirements:** R10

  **Dependencies:** None

  **Files:**
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss`
  - Modify: `tests/unit/test_main_screen.py`
  - Modify: `tests/integration/test_tab_navigation.py`
  - Modify: `tests/integration/test_textual_tui.py`

  **Approach:**
  - Change `TabPane("2 Discover & Select", id="discover-select")` to `TabPane("2 Select", id="discover-select")` — keep the ID unchanged to avoid cascading ID updates across all handlers and tests
  - Update the `BINDINGS` description from `"Discover"` to `"Select"` for key `2`
  - Update any test assertions that check tab label text

  **Patterns to follow:**
  - Existing tab label format: `"N Label"` where N is the hotkey number

  **Test scenarios:**
  - Happy path: Tab 2 label displays "2 Select" after mount
  - Happy path: Hotkey 2 description shows "Select"

  **Verification:**
  - All existing tests pass with updated label assertions
  - Tab ID `"discover-select"` unchanged, so no handler updates needed

- [x] **Unit 2: Move discovery trigger to connection handler**

  **Goal:** Auto-start chat discovery from MainScreen when connection succeeds, removing the on_show trigger from DiscoverSelectPane.

  **Requirements:** R1, R2, R3

  **Dependencies:** None (parallel with Unit 1)

  **Files:**
  - Modify: `whatsapp_chat_autoexport/tui/textual_panes/discover_select_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py`
  - Test: `tests/unit/test_discover_select_pane.py`
  - Test: `tests/unit/test_main_screen.py`
  - Test: `tests/integration/test_tab_navigation.py`

  **Approach:**
  - **DiscoverSelectPane**: Rename `_start_discovery()` to `start_discovery()` (public). Store the worker reference: `self._discovery_worker = self.run_worker(...)` so it can be cancelled later (Unit 3). Remove the `on_show` method and `_first_show` flag — discovery is no longer self-triggered. The `_collect_chats` worker, `_add_discovered_chat` live callback, `_discovery_generation` counter, and Refresh button handler all stay unchanged.
  - **MainScreen.on_connect_pane_connected**: After storing driver and setting `_connected = True`, call `self.query_one(DiscoverSelectPane).start_discovery()` before switching to the discover-select tab. This ensures the worker starts before the tab is visible, so results begin streaming immediately.
  - **Refresh button (R3)**: Already calls `_start_discovery()` internally — just update it to call the now-public `start_discovery()`. No other changes needed.

  **Patterns to follow:**
  - `MainScreen.on_discover_select_pane_start_export` calls `export_pane.start_export(chats)` directly — same pattern
  - `MainScreen.on_export_pane_export_complete` calls `summary_pane.start_processing(results)` directly — same pattern

  **Test scenarios:**
  - Happy path: `start_discovery()` is a public method on DiscoverSelectPane
  - Happy path: DiscoverSelectPane no longer has `on_show` or `_first_show` attribute
  - Happy path: MainScreen `on_connect_pane_connected` triggers discovery (integration: post `ConnectPane.Connected`, verify discovery-related state changes on the pane)
  - Edge case: Calling `start_discovery()` while already scanning is a no-op (existing `_scanning_chats` guard)
  - Edge case: Refresh button still works after initial discovery completes (calls `start_discovery()`)

  **Verification:**
  - Discovery starts immediately on connection without waiting for tab show
  - DiscoverSelectPane has no self-triggering logic
  - Refresh button continues to work for re-discovery

- [x] **Unit 3: Cancel discovery on export start**

  **Goal:** Stop a running discovery worker when the user starts an export.

  **Requirements:** R4

  **Dependencies:** Unit 2 (discovery must be public/triggerable)

  **Files:**
  - Modify: `whatsapp_chat_autoexport/tui/textual_panes/discover_select_pane.py`
  - Test: `tests/unit/test_discover_select_pane.py`

  **Approach:**
  - Add a `stop_discovery()` public method to DiscoverSelectPane that cancels the stored `_discovery_worker` (guarded by `if self._discovery_worker is not None`) and sets `_scanning_chats = False`. Increment `_discovery_generation` so any in-flight callbacks are ignored.
  - Call `stop_discovery()` at the start of the "Start Export" button handler, before posting `StartExport`.
  - The existing `_discovery_generation` stale-callback protection ensures no late-arriving chat names contaminate the selection after export starts.

  **Patterns to follow:**
  - ExportPane stores `self._export_worker` and calls `self._export_worker.cancel()` for direct cancellation
  - DiscoverSelectPane already uses `exclusive=True` on `run_worker` which auto-cancels previous workers of the same type — but explicit cancellation is clearer for this use case

  **Test scenarios:**
  - Happy path: `stop_discovery()` is a public method on DiscoverSelectPane
  - Happy path: `stop_discovery()` sets `_scanning_chats = False` and increments `_discovery_generation`
  - Edge case: Calling `stop_discovery()` when no discovery is running is a safe no-op
  - Integration: Start Export button handler calls `stop_discovery()` before posting `StartExport`

  **Verification:**
  - Discovery worker is cancelled when export begins
  - Stale callbacks from a cancelled discovery are safely ignored
  - Already-discovered chats remain in the selection list

- [x] **Unit 4: Add Cancel button to SummaryPane**

  **Goal:** Add a Cancel button to the Summary tab that stops pipeline processing and shows partial results.

  **Requirements:** R8, R9

  **Dependencies:** None (parallel with Units 1-3)

  **Files:**
  - Modify: `whatsapp_chat_autoexport/tui/textual_panes/summary_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss`
  - Test: `tests/unit/test_summary_pane.py`

  **Approach:**
  - **Compose**: Add a `Button("Cancel", id="btn-cancel-processing", variant="error")` to the bottom bar alongside "Open Output" and "Done". The cancel button is visible during processing and hidden after completion or cancellation.
  - **Cancel handler**: On press, call `self._processing_worker.cancel()` and update the button label to "Cancelling..." with `disabled=True` to prevent double-clicks.
  - **Worker state handling**: Modify the existing `on_worker_state_changed` handler's `CANCELLED` branch to set `self._cancelled = True` and call `_handle_processing_complete` with whatever partial results are available (from the `results` dict built up during processing phases). `_handle_processing_complete` should check `self._cancelled` and pass it to `show_results` so the UI can indicate partial completion (e.g., "Processing cancelled" instead of "Processing complete").
  - **UI after cancel**: Hide the Cancel button, show the bottom bar with "Open Output" and "Done". The ProgressPane shows completed phases with a "Cancelled" indicator for the interrupted phase.
  - **No modal needed**: Unlike ExportPane's multi-option cancel, pipeline cancel is straightforward — just stop processing. No CancelModal.

  **Patterns to follow:**
  - ExportPane's `on_button_pressed` dispatches by `event.button.id`
  - ExportPane stores `self._export_worker` and calls `.cancel()` on it
  - SummaryPane already stores `self._processing_worker`

  **Test scenarios:**
  - Happy path: Cancel button exists in SummaryPane compose with id `"btn-cancel-processing"`
  - Happy path: Cancel button has variant `"error"`
  - Happy path: `_cancelled` flag exists on SummaryPane, initially `False`
  - Edge case: Cancel button is disabled after being clicked (prevents double-click)
  - Edge case: Cancel button is hidden after processing completes normally
  - Error path: Cancelling when no worker is running is a safe no-op (guard on `_processing_worker is not None` and worker state)
  - Integration: Cancel button press sets `_cancelled = True` and calls worker cancel

  **Verification:**
  - Cancel button is visible during processing
  - Clicking Cancel stops the pipeline and shows partial results
  - After cancellation, user stays on Summary tab
  - "Open Output" and "Done" buttons appear after cancellation

- [x] **Unit 5: Update tests for all changes**

  **Goal:** Ensure comprehensive test coverage for the new behavior across unit and integration tests.

  **Requirements:** R1-R4, R8-R10

  **Dependencies:** Units 1-4

  **Files:**
  - Modify: `tests/unit/test_main_screen.py`
  - Modify: `tests/unit/test_discover_select_pane.py`
  - Modify: `tests/unit/test_summary_pane.py`
  - Modify: `tests/integration/test_tab_navigation.py`
  - Modify: `tests/integration/test_textual_tui.py`

  **Approach:**
  - **test_main_screen.py**: Add test that `on_connect_pane_connected` calls `start_discovery()` on the DiscoverSelectPane. Verify tab label "2 Select".
  - **test_discover_select_pane.py**: Remove tests for `_first_show` / `on_show` auto-trigger. Add tests for public `start_discovery()` and `stop_discovery()` methods. Add test that Start Export calls `stop_discovery()`.
  - **test_summary_pane.py**: Add tests for Cancel button presence, `_cancelled` flag, cancel-when-no-worker guard.
  - **test_tab_navigation.py**: Add integration test for the full flow: connect → auto-discovery starts → select chats → export → summary → cancel pipeline.
  - **test_textual_tui.py**: Update any assertions that reference the old tab label.

  **Patterns to follow:**
  - Existing structural tests: verify widget presence, message classes, initial state
  - Integration tests: post messages, check tab state, use `pilot.pause()` between state changes
  - Use `size=(120, 40)` for mounted tests

  **Test scenarios:**
  - Happy path: MainScreen connection handler triggers discovery on DiscoverSelectPane
  - Happy path: Tab 2 label is "2 Select"
  - Happy path: Cancel button present in SummaryPane
  - Happy path: `stop_discovery()` exists and is callable
  - Integration: Full connect → discover → select → export → summary → cancel flow
  - Edge case: Discovery no longer auto-starts on tab show (removed behavior)

  **Verification:**
  - All existing tests pass (updated as needed)
  - New tests cover the changed behaviors
  - `poetry run pytest` passes with zero failures

## System-Wide Impact

- **Interaction graph:** ConnectPane → MainScreen → DiscoverSelectPane is a new call path (MainScreen already calls ExportPane and SummaryPane this way). No new message types needed.
- **Error propagation:** Discovery errors still bubble as `ConnectionLost` from DiscoverSelectPane — unchanged. Pipeline cancellation via `worker.cancel()` raises `CancelledError` which Textual's worker infrastructure handles.
- **State lifecycle risks:** Cancelling discovery mid-stream could leave `_scanning_chats = True` if not properly reset — Unit 3's `stop_discovery()` must reset this flag.
- **API surface parity:** Headless mode is unaffected — it doesn't use the TUI panes. CLI flags unchanged.
- **Integration coverage:** The connect → auto-discovery → stream results flow is the key cross-pane integration to test.
- **Unchanged invariants:** Tab IDs (`connect`, `discover-select`, `export`, `summary`) remain the same. Reactive cascade logic unchanged. Export and pipeline logic unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `worker.cancel()` on pipeline may leave temp files | Pipeline already has cleanup phase; incomplete runs leave files in temp dir which is acceptable |
| Discovery worker may not cancel cleanly if mid-Appium-call | `_discovery_generation` counter already handles stale callbacks; worst case is one extra chat appearing |
| Tab rename breaks test assertions | Unit 1 handles this explicitly; tab ID stays the same |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-06-tui-ux-refinements-requirements.md](docs/brainstorms/2026-04-06-tui-ux-refinements-requirements.md)
- Related code: `MainScreen` at `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py`
- Related code: `DiscoverSelectPane` at `whatsapp_chat_autoexport/tui/textual_panes/discover_select_pane.py`
- Related code: `SummaryPane` at `whatsapp_chat_autoexport/tui/textual_panes/summary_pane.py`
- Related code: `ExportPane` cancel pattern at `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py`
- Related PR: #15 (tab navigation refactor)
