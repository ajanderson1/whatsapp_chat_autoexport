---
title: "refactor: Replace TUI screen-stack with navigable tab interface"
type: refactor
status: completed
date: 2026-04-01
origin: docs/brainstorms/2026-04-01-tui-tab-navigation-requirements.md
deepened: 2026-04-01
---

# Replace TUI Screen-Stack with Navigable Tab Interface

## Overview

Replace the current 2-screen model (DiscoveryScreen + SelectionScreen with 4 internal modes) with a single-screen, 4-tab interface where tabs unlock progressively and users can freely navigate between unlocked tabs. Export and processing continue running in the background regardless of which tab is focused.

## Problem Frame

The current TUI uses `switch_screen()` to transition from DiscoveryScreen to SelectionScreen, which destroys the previous screen's state. SelectionScreen then manages 4 internal modes (select/export/processing/complete) via a reactive `_mode` property, but users can't navigate backward once in export/processing/complete modes. The PipelineHeader shows 4 stages but they're purely cosmetic — not clickable or navigable. The "Discover Messages" and "Select Messages" stages are artificially split when they represent one activity.

(see origin: docs/brainstorms/2026-04-01-tui-tab-navigation-requirements.md)

## Requirements Trace

- R1. Four tabs: Connect, Discover & Select, Export, Summary
- R2. Navigate by mouse click and number hotkeys 1-4; locked tabs ignore input
- R3. Progressive unlock: Connect always → D&S after connection → Export after selection → Summary after export completes (success or partial failure)
- R4. Auto-advance to D&S tab after device connection
- R5. Background work continues regardless of focused tab
- R6. Tabs retain state when navigated away and back
- R7. Three visual states: active, unlocked, locked (dimmed)
- R8. (Nice-to-have) Background activity indicator on unfocused tabs
- R9. Connect tab: device scan, wireless ADB — NOT chat discovery
- R10. D&S tab: chat discovery + selection + settings
- R11. Export tab: per-chat export progress, pause/resume, cancel
- R12. Summary tab: processing progress + completion results

## Scope Boundaries

- Not changing export/pipeline core logic — TUI navigation only
- Not adding new export features or pipeline capabilities
- Not redesigning widget layouts within each tab — content stays similar
- Not changing headless mode or CLI flags
- Not changing modal overlays (help, cancel, secret settings) — they overlay whatever tab is active
- Not implementing re-run flow (starting a new export after one completes) — that's a separate feature

## Context & Research

### Relevant Code and Patterns

**Textual framework (v8.0.0 installed):**
- `TabbedContent` natively supports `disable_tab()` / `enable_tab()` — blocks both mouse click and keyboard navigation on disabled tabs
- `ContentSwitcher` (used internally by `TabbedContent`) toggles `display` only — **does not unmount** children, so workers keep running and widget state is preserved
- Disabled tabs render with `:disabled` CSS pseudo-class (`color: $foreground 25%`)
- Programmatic tab switching: `tabbed_content.active = "pane-id"`
- Tab IDs are auto-prefixed with `--content-tab-` for CSS targeting
- Left/right arrow keyboard nav auto-skips disabled tabs

**Current TUI architecture:**
- `WhatsAppExporterApp` (textual_app.py) holds all shared state: `_whatsapp_driver`, `_discovered_chats`, `_selected_chats`, settings, `_state_manager`, `_event_bus`
- `DiscoveryScreen` (1,090 lines) — 7 worker types for device scan, connect, chat discovery, wireless ADB
- `SelectionScreen` (1,108 lines) — 4 modes via reactive `_mode`, 2 workers (export, processing) with `thread=True`
- `PipelineHeader` (111 lines) — cosmetic only, `Static` widgets in a `Horizontal`, not interactive
- `transition_to_selection()` uses `switch_screen()` which **destroys** DiscoveryScreen
- Going back creates a **new** DiscoveryScreen, losing all state

**Workers are screen-attached:** Both screens use `self.run_worker()` where `self` is the Screen. In a single-screen model with `TabbedContent`, workers will be attached to the single screen and persist across tab changes — which is exactly what R5 requires.

### External References

- Textual `TabbedContent`: source at `textual/widgets/_tabbed_content.py` — `disable_tab()`, `enable_tab()`, `hide_tab()`, `show_tab()` methods (lines 670-716)
- Textual `ContentSwitcher`: source at `textual/widgets/_content_switcher.py` — toggles `child.display` only (lines 97-101)
- Textual `Tabs`: source at `textual/widgets/_tabs.py` — `_potentially_active_tabs` filters disabled/hidden (line 406)

## Key Technical Decisions

- **Use `TabbedContent` directly rather than custom tab bar + `ContentSwitcher`**: Textual v8.0.0 natively supports `disable_tab()` / `enable_tab()` with proper mouse/keyboard blocking and `:disabled` CSS styling. This covers R2, R3, R7 without custom widget code. The tab underline animation and left/right keyboard nav come free. Custom number hotkeys (1-4) are added via app-level bindings that call `tabbed_content.active = "pane-id"` after checking lock state.

- **Single `MainScreen` replaces both DiscoveryScreen and SelectionScreen**: A new `MainScreen(Screen)` composes a `TabbedContent` with 4 `TabPane` children. Each pane's content is extracted from the existing screens as container widgets (not rewritten). The app pushes `MainScreen` on startup instead of `DiscoveryScreen`.

- **Convert screens to container widgets, not rewrite**: `DiscoveryScreen`'s `compose()` content (minus PipelineHeader) becomes `ConnectPane(Container)`. `DiscoveryScreen`'s chat discovery section becomes part of `DiscoverSelectPane(Container)`. `SelectionScreen`'s mode-specific content is split into `ExportPane` and `SummaryPane` containers. Worker methods and event handlers move to the pane containers. This minimizes rewrite risk.

- **Tab unlock state managed by reactive properties on `MainScreen`**: `MainScreen` has reactive booleans (`_connected`, `_has_selection`, `_export_complete`) that drive `enable_tab()` / `disable_tab()` calls via watchers. The app sets these properties as workflow progresses.

- **Number hotkeys handled at app level with lock check**: Bindings `1`-`4` on the app (without `priority=True`) check the tab's disabled state before switching. If disabled, the binding is a no-op. Must NOT use `priority=True` to avoid intercepting digit input in wireless ADB IP:port and pairing code fields.

- **PipelineHeader is removed**: `TabbedContent`'s built-in tab bar replaces PipelineHeader entirely. The stage indicator becomes the tab bar itself.

- **Reactive cascade on disconnect/deselect**: `watch__connected(False)` must reset `_has_selection` and `_export_complete` to `False`. `watch__has_selection(False)` must reset `_export_complete` to `False`. This prevents stale state after re-connection.

- **Two ChatListWidget instances with distinct IDs and parameterized internal IDs**: The D&S pane uses `ChatListWidget(id="chat-select-list")` for selection. The Export pane uses `ChatListWidget(id="chat-status-list")` for status display. **Critical**: `ChatListWidget.compose()` currently hardcodes `ListView(id="chat-listview")`. With two instances mounted simultaneously, this causes a `DuplicateIds` crash. The internal `ListView` ID must be parameterized (e.g., derive from the parent widget's ID: `f"{self.id}-listview"`). All existing `query_one("#chat-listview")` calls must be updated to use the parameterized ID or query by type instead.

- **ActivityLog queried via `self.screen.query_one()`**: Since `ActivityLog` is a sibling of `TabbedContent` (not inside any pane), panes must use `self.screen.query_one(ActivityLog)` instead of `self.query_one(ActivityLog)`. Note: there are 14+ instances of `self.query_one(ActivityLog)` in the current `DiscoveryScreen` alone that all need updating. This is mechanical but pervasive — implementer should grep for all `query_one(ActivityLog)` and `query_one("#activity-log")` calls.

- **Escape binding behavior**: MainScreen delegates Escape to the active pane. If a modal is open, Textual's modal handling closes it (existing behavior). If on Export tab during export, show CancelModal. Otherwise, Escape is a no-op (no screen to pop back to). The current `action_go_back` on the app needs rework — it should only pop modal screens, not the main screen.

- **Each pane handles its own `on_worker_state_changed`**: MainScreen does NOT implement this handler. Worker state events bubble from the worker's owning pane, and each pane dispatches on `worker.name` as the current screens do. This prevents double-handling via message bubbling.

- **Cancel-and-return-to-selection flow**: When CancelModal returns "return to selection", MainScreen handles it by: switching to D&S tab, re-enabling selection on the D&S pane's ChatListWidget, resetting ExportPane state, and re-disabling the Export tab (setting `_has_selection` temporarily to `False` and back to `True` so the user can re-select and re-export).

## Open Questions

### Resolved During Planning

- **TabbedContent vs custom tab bar?** → `TabbedContent` — native disable/enable support confirmed in v8.0.0 source. No custom tab bar needed.
- **Workers survive tab switching?** → Yes — `ContentSwitcher` toggles `display` only; no unmount, no worker cancellation. Confirmed in Textual source (`_content_switcher.py` lines 97-101, `widget.py` line 4799).
- **Can existing screens be converted to containers?** → Yes — both screens' `compose()` methods build widget trees that are pure layout. Extracting these into `Container` subclasses preserves the widget hierarchy. Worker methods become methods on the container.
- **Auto-advance to Summary on export completion?** → Yes, but only if the user is currently on the Export tab. If they've navigated elsewhere, just unlock Summary without stealing focus.

### Deferred to Implementation

- **Exact split point in DiscoveryScreen for Connect vs Discover content**: The discovery section (`#discovery-section`) and its workers (`collect_chats`, `_add_discovered_chat`, `_handle_chat_collection`) need to move to DiscoverSelectPane. The exact extraction boundary depends on how tightly coupled the discovery UI callbacks are to the surrounding screen state.
- **`_discovery_generation` counter placement**: This counter protects against stale discovery callbacks. It should live on the DiscoverSelectPane (not the app) since it is a pane-internal concern. Verify during implementation.
- **CSS refactoring**: `styles.tcss` has screen-level selectors (`DiscoveryScreen`, `SelectionScreen`) that will need updating to target pane containers. Some dead CSS for removed `ExportScreen` / `ProcessingScreen` can be cleaned up simultaneously.
- **ChatListWidget population timing**: `ChatListWidget` does NOT currently support incremental population after mount. The D&S pane uses a separate `ListView(id="discovery-inventory")` for live-streaming discovered chats (matching the current DiscoveryScreen pattern), then populates `ChatListWidget` with the full list when discovery completes.
- **ExportPane ChatListWidget initialization**: When `start_export()` is called, ExportPane must populate its `ChatListWidget(id="chat-status-list")` from the selected chat names. This is a new initialization path since the current code uses a single widget that switches modes.
- **SettingsPanel.SettingsChanged handling**: The D&S pane should handle `on_settings_panel_settings_changed()` internally and write to `self.app`, matching the current `SelectionScreen` pattern.
- **ExportComplete message payload**: Must include a `cancelled` flag and the `export_results` dict. MainScreen should preserve the conditional check (`if self.app.transcribe_audio or self.app.output_dir`) before starting processing — if neither is configured, Summary shows results directly without processing.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
MainScreen (single Screen, replaces DiscoveryScreen + SelectionScreen)
├── TabbedContent
│   ├── TabPane "connect" (initially enabled)
│   │   └── ConnectPane (Container)
│   │       ├── Device list, wireless ADB inputs, action buttons
│   │       └── Workers: scan_devices, start_appium, connect_device, wireless_*
│   │
│   ├── TabPane "discover-select" (initially disabled)
│   │   └── DiscoverSelectPane (Container)
│   │       ├── Discovery inventory ListView (live-streams chats during discovery)
│   │       ├── ChatListWidget(id="chat-select-list") + SettingsPanel (horizontal split)
│   │       │   (populated from completed discovery results)
│   │       └── Workers: collect_chats; Start Export button
│   │
│   ├── TabPane "export" (initially disabled)
│   │   └── ExportPane (Container)
│   │       ├── ChatListWidget(id="chat-status-list") + ProgressPane
│   │       ├── Pause/Resume, Cancel controls
│   │       └── Worker: export_worker (thread=True)
│   │
│   └── TabPane "summary" (initially disabled)
│       └── SummaryPane (Container)
│           ├── Processing phases (ProgressPane in processing mode)
│           ├── Completion results
│           └── Worker: processing_worker (thread=True)
│
└── ActivityLog (below TabbedContent, always visible)

State flow:
  ConnectPane.on_connected → MainScreen._connected = True
    → enable_tab("discover-select"), auto-switch to it (R4)

  DiscoverSelectPane.on_selection_changed → MainScreen._has_selection = True/False
    → enable/disable_tab("export")

  DiscoverSelectPane.on_start_export → switch to Export tab
    → ExportPane starts export_worker

  ExportPane.on_export_complete → MainScreen._export_complete = True
    → enable_tab("summary")
    → if current tab is "export": auto-switch to "summary"
    → SummaryPane starts processing_worker

Tab lock enforcement:
  App bindings 1-4 → check tab disabled state → TabbedContent.active = pane_id
  Mouse/keyboard → handled natively by TabbedContent disable_tab()
```

## Implementation Units

- [ ] **Unit 1: Create MainScreen with TabbedContent skeleton**

  **Goal:** Replace the app's screen setup with a single `MainScreen` that contains a `TabbedContent` with 4 empty `TabPane` placeholders and an `ActivityLog`.

  **Requirements:** R1, R7

  **Dependencies:** None

  **Files:**
  - Create: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_app.py` — replace `switch_screen(DiscoveryScreen())` with `push_screen(MainScreen())`; remove `transition_to_selection()`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — add `MainScreen` and tab styling rules
  - Test: `tests/unit/test_main_screen.py`

  **Approach:**
  - `MainScreen(Screen)` composes `TabbedContent` with 4 `TabPane` children: `connect`, `discover-select`, `export`, `summary`
  - All tabs except `connect` start disabled via `on_mount()` calling `disable_tab()`
  - Reactive properties `_connected: bool`, `_has_selection: bool`, `_export_complete: bool` with watchers that call `enable_tab()` / `disable_tab()`. Cascade logic: `watch__connected(False)` resets `_has_selection` and `_export_complete`; `watch__has_selection(False)` resets `_export_complete`
  - `ActivityLog` widget mounted below the `TabbedContent`, always visible regardless of active tab
  - App bindings for `1`-`4` (without `priority=True`) check disabled state before switching: `if not tab.disabled: tabbed_content.active = pane_id`

  **Patterns to follow:**
  - Existing `WhatsAppExporterApp` reactive property pattern
  - `TabbedContent.disable_tab()` / `enable_tab()` API from Textual v8.0.0
  - Existing `styles.tcss` design token usage (`$primary`, `$surface`, etc.)

  **Test scenarios:**
  - Happy path: MainScreen mounts with 4 tab panes; only Connect tab is enabled; other 3 are disabled
  - Happy path: Setting `_connected = True` enables the discover-select tab
  - Happy path: Setting `_has_selection = True` enables the export tab
  - Happy path: Setting `_export_complete = True` enables the summary tab
  - Edge case: Setting `_connected = False` after it was `True` re-disables discover-select, export, and summary tabs
  - Edge case: Setting `_has_selection = False` re-disables export tab but not discover-select
  - Happy path: Number key `2` switches to discover-select when enabled
  - Edge case: Number key `2` does nothing when discover-select is disabled
  - Happy path: ActivityLog is visible regardless of which tab is active

  **Verification:**
  - App launches and shows MainScreen with Connect tab active
  - Tab bar displays 4 tabs with correct visual states (active, disabled)
  - Number hotkeys work for enabled tabs and are ignored for disabled tabs

- [ ] **Unit 2: Extract ConnectPane from DiscoveryScreen**

  **Goal:** Move device connection UI and logic (device scan, wireless ADB pairing, Appium lifecycle) from `DiscoveryScreen` into a `ConnectPane(Container)` that lives inside the Connect tab.

  **Requirements:** R9, R6

  **Dependencies:** Unit 1

  **Files:**
  - Create: `whatsapp_chat_autoexport/tui/textual_panes/connect_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py` — mount `ConnectPane` inside the connect `TabPane`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — migrate DiscoveryScreen selectors to ConnectPane
  - Test: `tests/unit/test_connect_pane.py`

  **Approach:**
  - Extract DiscoveryScreen's `compose()` content (device list, wireless ADB section, action buttons) minus the `#discovery-section` (that goes to Unit 3) and minus `PipelineHeader` (removed)
  - Move worker methods: `_scan_devices`, `_update_device_list`, `_start_appium`, `_connect_to_device`, `_wireless_connect`, `_wireless_finish_connect`
  - Move corresponding `on_worker_state_changed` dispatch branches
  - Move key bindings: `r` (refresh), `enter` (connect), `d` (dry run)
  - On successful connection, emit a custom message `ConnectPane.Connected(driver)` that `MainScreen` handles to set `_connected = True` and auto-switch to D&S tab (R4)
  - ConnectPane reads/writes shared state via `self.app` (same pattern as current screens)

  **Patterns to follow:**
  - DiscoveryScreen's existing widget composition and worker patterns
  - Textual `Message` pattern for pane-to-screen communication (like `ChatListWidget.SelectionChanged`)

  **Test scenarios:**
  - Happy path: ConnectPane mounts with device list, wireless ADB inputs, Refresh and Connect buttons
  - Happy path: Pressing `r` triggers device scan worker
  - Happy path: Successful connection emits `ConnectPane.Connected` message with driver
  - Happy path: Dry run mode (`d` key) emits Connected with mock driver
  - Edge case: Connection failure shows error in activity log, does not emit Connected
  - Happy path: Wireless ADB pairing flow works (input IP:port, pairing code, connect)
  - Happy path: ConnectPane retains connection status when navigated away and back (R6)
  - Happy path: ConnectPane retains `_appium_started` state across tab switches

  **Verification:**
  - Connect tab shows device list and wireless ADB section
  - Device scan populates list
  - Successful connection triggers tab unlock and auto-advance to D&S tab

- [ ] **Unit 3: Extract DiscoverSelectPane from DiscoveryScreen + SelectionScreen**

  **Goal:** Combine chat discovery (from DiscoveryScreen's `#discovery-section`) with chat selection and settings (from SelectionScreen's "select" mode) into a single `DiscoverSelectPane(Container)`.

  **Requirements:** R10, R3, R6

  **Dependencies:** Unit 1, Unit 2

  **Files:**
  - Create: `whatsapp_chat_autoexport/tui/textual_panes/discover_select_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py` — mount `DiscoverSelectPane` inside the discover-select `TabPane`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — migrate relevant selectors
  - Test: `tests/unit/test_discover_select_pane.py`

  **Approach:**
  - Top section: discovery inventory (`ListView(id="discovery-inventory")`, discovery count, Refresh Chats button) — moved from DiscoveryScreen's `#discovery-section`. This is a separate widget from `ChatListWidget` — it receives live-streamed chat names during discovery via `call_from_thread`. `ChatListWidget` does NOT support incremental population after mount, so the existing two-widget pattern (discovery ListView + ChatListWidget) must be preserved
  - When discovery completes, populate `ChatListWidget(id="chat-select-list")` with the full list and pre-select all
  - Bottom section: `ChatListWidget` + `SettingsPanel` in horizontal split — moved from SelectionScreen's "select" mode layout
  - `SettingsPanel.SettingsChanged` handled internally by the pane (writes to `self.app`, matching current `SelectionScreen` pattern)
  - "Start Export" button at bottom — validates API key via `SettingsPanel` before emitting
  - Worker: `collect_chats` (moved from DiscoveryScreen) — auto-starts on first show if driver is connected and chats haven't been collected yet. Uses `_first_show: bool` flag to distinguish first vs subsequent tab focuses (since `on_show` fires every time the tab is selected, not just the first time)
  - `_discovery_generation` counter lives on this pane
  - Selection changes emit `DiscoverSelectPane.SelectionChanged(count)` — MainScreen uses this to set `_has_selection = (count > 0)` which controls Export tab unlock
  - "Start Export" click emits `DiscoverSelectPane.StartExport(selected_chats)` — MainScreen handles by switching to Export tab and triggering export. Message carries selected chat names; settings are already on `self.app`
  - Key bindings: `Space` (toggle), `A` (select all), `N` (deselect all), `I` (invert), `Enter` (start export), `f` (refresh chats)
  - Error handling: Discovery failure (device disconnected, WhatsApp not open) shows error in the pane's status area and emits `DiscoverSelectPane.ConnectionLost` — MainScreen resets `_connected = False` to cascade-lock downstream tabs

  **Patterns to follow:**
  - DiscoveryScreen's live-streaming chat discovery with `call_from_thread`
  - SelectionScreen's "select" mode widget layout
  - ChatListWidget's existing `SelectionChanged` message pattern

  **Test scenarios:**
  - Happy path: DiscoverSelectPane mounts with discovery inventory, chat list, and settings panel
  - Happy path: Chat discovery auto-starts when pane first becomes visible and driver is connected
  - Happy path: Discovered chats populate both the inventory and the chat list widget
  - Happy path: Selecting at least one chat emits `SelectionChanged` with count > 0
  - Edge case: Deselecting all chats emits `SelectionChanged` with count = 0 (disables Export tab)
  - Happy path: "Start Export" button emits `StartExport` message
  - Edge case: "Start Export" disabled when no chats selected
  - Happy path: Re-scanning chats (`f` key) clears and repopulates the list
  - Happy path: Pane retains selections when navigated away and back (R6)
  - Integration: Discovery generation counter prevents stale callbacks from overwriting current results

  **Verification:**
  - D&S tab shows discovery results and selection UI
  - Chat selection enables/disables the Export tab
  - Starting export switches to Export tab

- [ ] **Unit 4: Extract ExportPane from SelectionScreen**

  **Goal:** Move export progress display, pause/resume, and cancel controls from SelectionScreen's "export" mode into an `ExportPane(Container)`.

  **Requirements:** R11, R5, R6

  **Dependencies:** Unit 1, Unit 3

  **Files:**
  - Create: `whatsapp_chat_autoexport/tui/textual_panes/export_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py` — mount `ExportPane` inside the export `TabPane`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — migrate relevant selectors
  - Test: `tests/unit/test_export_pane.py`

  **Approach:**
  - Contains: `ChatListWidget(id="chat-status-list")` (in status display mode), `ProgressPane` (in export mode), Pause/Resume button, Cancel button
  - Worker: `export_worker` (thread=True) — moved from SelectionScreen
  - `start_export(chats, settings)` method called by MainScreen when StartExport is received. Must populate `ChatListWidget` with selected chat names and initial pending statuses
  - Progress callbacks use `call_from_thread` to update ChatListWidget status and ProgressPane — these updates happen regardless of whether the Export tab is visible (R5)
  - On export completion (all chats done or cancelled), emits `ExportPane.ExportComplete(results, cancelled)` — MainScreen sets `_export_complete = True`, unlocks Summary tab. The `cancelled` flag tells MainScreen whether to start processing or skip to results
  - Cancel triggers existing CancelModal overlay. CancelModal "return to selection" result emits `ExportPane.CancelledReturnToSelection` — MainScreen handles by switching to D&S tab, resetting ExportPane state, and re-enabling D&S pane selection
  - Tracks `_export_results`, `_consecutive_failures`, `_cancel_after_current`, `_paused` — moved from SelectionScreen
  - `reset()` method clears all export state, resets ChatListWidget, for use when returning to selection after cancel

  **Patterns to follow:**
  - SelectionScreen's existing `_run_export` worker method and progress callback wiring
  - SelectionScreen's `_update_ui_for_mode("export")` visibility logic
  - CancelModal push/callback pattern

  **Test scenarios:**
  - Happy path: ExportPane mounts with chat list in status mode and progress pane
  - Happy path: `start_export()` begins export worker and updates progress
  - Happy path: Per-chat status updates reflect in ChatListWidget (pending → in-progress → completed/failed)
  - Happy path: Pause button pauses export; Resume button resumes
  - Happy path: Cancel shows CancelModal; "cancel after current" waits for current chat
  - Edge case: Export continues running when user navigates to a different tab (R5)
  - Edge case: Navigating back to Export tab shows current progress state (R6)
  - Happy path: Export completion emits `ExportComplete` with results dict
  - Edge case: Partial failure (some chats fail) still emits ExportComplete
  - Error path: All chats fail — still emits ExportComplete so Summary can show error summary
  - Happy path: CancelModal "return to selection" emits CancelledReturnToSelection, resets export state
  - Edge case: `reset()` clears ChatListWidget statuses and all tracking state for a fresh re-export

  **Verification:**
  - Export runs to completion with per-chat progress visible
  - Navigating away and back preserves progress state
  - Export completion unlocks Summary tab
  - Cancel-and-return resets to a clean state for re-export

- [ ] **Unit 5: Extract SummaryPane from SelectionScreen**

  **Goal:** Move processing progress and completion display from SelectionScreen's "processing" and "complete" modes into a `SummaryPane(Container)`.

  **Requirements:** R12, R5, R6

  **Dependencies:** Unit 1, Unit 4

  **Files:**
  - Create: `whatsapp_chat_autoexport/tui/textual_panes/summary_pane.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py` — mount `SummaryPane` inside the summary `TabPane`
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — migrate relevant selectors
  - Test: `tests/unit/test_summary_pane.py`

  **Approach:**
  - Contains: `ProgressPane` (in processing mode, then complete mode), results display
  - Worker: `processing_worker` (thread=True) — moved from SelectionScreen
  - `start_processing(export_results, settings)` method called by MainScreen when ExportComplete is received
  - Two internal phases: "processing" (pipeline running) → "complete" (results shown)
  - "Open Output Folder" button and "Done" button in complete phase
  - `O` hotkey to open output folder

  **Patterns to follow:**
  - SelectionScreen's existing `_run_processing` worker method and progress callback wiring
  - SelectionScreen's `_update_ui_for_mode("processing")` and `_update_ui_for_mode("complete")` logic

  **Test scenarios:**
  - Happy path: SummaryPane mounts with processing progress display
  - Happy path: `start_processing()` begins processing worker with phase-level progress
  - Happy path: Processing phases display in order (download → extract → transcribe → organize)
  - Happy path: Processing completion transitions to results display
  - Happy path: Results show counts (exported, transcribed, failed, skipped), output path
  - Edge case: Processing continues when user navigates away (R5)
  - Edge case: Navigating back shows current progress or final results (R6)
  - Happy path: "Open Output Folder" button works
  - Error path: Processing failure shows error details in results

  **Verification:**
  - Summary tab shows processing progress and final results
  - Output folder can be opened from results view

- [ ] **Unit 6: Wire MainScreen orchestration and auto-advance**

  **Goal:** Connect all pane messages to MainScreen handlers that manage tab unlock state, auto-advance, and cross-pane data flow.

  **Requirements:** R3, R4, R5

  **Dependencies:** Units 2-5

  **Files:**
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/main_screen.py`
  - Modify: `whatsapp_chat_autoexport/tui/textual_app.py` — remove old screen transition logic, old `PipelineStage` enum usage
  - Test: `tests/integration/test_tab_navigation.py`

  **Approach:**
  - MainScreen message handlers:
    - `on_connect_pane_connected(msg)` → store driver on app, set `_connected = True`, switch to D&S tab (R4)
    - `on_discover_select_pane_selection_changed(msg)` → set `_has_selection = (count > 0)`
    - `on_discover_select_pane_start_export(msg)` → switch to Export tab, call `export_pane.start_export()`
    - `on_export_pane_export_complete(msg)` → set `_export_complete = True`, if current tab is export then switch to summary, call `summary_pane.start_processing()`
  - Remove `WhatsAppExporterApp.transition_to_selection()` method
  - Remove `PipelineStage` enum and `current_stage` reactive from app (no longer needed — tab bar replaces it)
  - Clean up app-level bindings: keep global Q/H/?/Escape//, add 1-4 for tab navigation

  **Patterns to follow:**
  - Textual `on_<widget>_<message>` handler naming convention
  - Existing `TabbedContent.active = "pane-id"` API

  **Test scenarios:**
  - Integration: Full dry-run flow — app launches → Connect tab → dry-run connect → auto-advance to D&S → select chats → Export tab unlocks
  - Integration: Tab lock cascade — disconnecting re-locks D&S, Export, Summary
  - Happy path: Auto-advance to D&S after connection (R4)
  - Happy path: Auto-advance to Summary after export completion (when on Export tab)
  - Edge case: No auto-advance to Summary when user is on Connect or D&S tab during export completion
  - Happy path: Number hotkeys 1-4 navigate between unlocked tabs
  - Edge case: Number hotkey for locked tab is a no-op

  **Verification:**
  - Complete workflow from Connect through Summary works via tab navigation
  - Auto-advance triggers at correct points
  - Tab lock state is always consistent with workflow progress

- [ ] **Unit 7: Update tests and remove old screens**

  **Goal:** Update integration tests and unit tests for the new tab model. Remove `DiscoveryScreen` and `SelectionScreen` classes. Clean up dead code.

  **Requirements:** Success criteria: existing tests pass or are updated

  **Dependencies:** Unit 6

  **Files:**
  - Delete: `whatsapp_chat_autoexport/tui/textual_screens/discovery_screen.py`
  - Delete: `whatsapp_chat_autoexport/tui/textual_screens/selection_screen.py`
  - Delete: `whatsapp_chat_autoexport/tui/textual_widgets/pipeline_header.py`
  - Modify: `tests/integration/test_textual_tui.py` — update 28 tests for tab-based navigation
  - Delete: `tests/unit/test_discovery_screen.py` — replaced by `test_connect_pane.py` + `test_discover_select_pane.py` (created in Units 2-3)
  - Delete: `tests/unit/test_selection_screen_export.py` — replaced by `test_export_pane.py` (created in Unit 4)
  - Delete: `tests/unit/test_selection_screen_processing.py` — replaced by `test_summary_pane.py` (created in Unit 5)
  - Modify: `tests/conftest.py` — update `tui_app` fixture if MainScreen changes mount behavior
  - Modify: `whatsapp_chat_autoexport/tui/styles.tcss` — remove DiscoveryScreen/SelectionScreen/PipelineHeader/ExportScreen/ProcessingScreen selectors, clean up dead CSS
  - Modify: `whatsapp_chat_autoexport/tui/textual_screens/__init__.py` — update exports

  **Approach:**
  - Integration tests: Replace `isinstance(app.screen, DiscoveryScreen)` assertions with tab-based assertions (query `TabbedContent`, check `active` pane, check tab disabled state)
  - Integration tests: Replace `press("d"), press("c")` navigation with dry-run connect + tab auto-advance
  - Unit tests: Rename test files to match new pane names, update class references
  - Unit tests: Worker method tests (which test methods directly without pilot) should need minimal changes — just update the class being tested
  - Remove `PipelineHeader` widget and all its CSS
  - Remove dead CSS for `ExportScreen`, `ProcessingScreen` (remnants from pre-consolidation)

  **Patterns to follow:**
  - Existing Textual pilot test patterns in `test_textual_tui.py`
  - Existing unit test patterns that mock workers and test methods directly

  **Test scenarios:**
  - Happy path: All 28 integration tests pass with updated navigation
  - Happy path: All discovery screen unit tests pass against ConnectPane + DiscoverSelectPane
  - Happy path: All selection screen export unit tests pass against ExportPane
  - Happy path: All selection screen processing unit tests pass against SummaryPane
  - Happy path: No import errors after old screens are deleted
  - Edge case: `tui_app` fixture works correctly with MainScreen

  **Verification:**
  - `poetry run pytest` passes with 0 failures
  - No references to deleted classes remain in non-test, non-legacy code
  - CSS has no orphaned selectors for removed widgets/screens

## System-Wide Impact

- **Interaction graph:** Modal overlays (HelpScreen, CancelModal, SecretSettingsModal) are pushed via `app.push_screen()` and are unaffected — they overlay whatever is below. The `Escape` binding behavior is resolved: if a modal is open, Textual's modal handling closes it. If on Export tab during export, Escape shows CancelModal. Otherwise, Escape is a no-op. The app's `action_go_back` only pops modal screens, never the main screen.
- **Error propagation:** Export/processing errors currently flow through worker state change handlers. These move to pane-level handlers but the pattern is identical. Errors surface in the ActivityLog (global) and in pane-specific UI.
- **State lifecycle risks:** The main risk is the Connect → D&S handoff: the driver and discovered chats must be available to DiscoverSelectPane before it starts discovery. Since both are stored on the app object (existing pattern), this is safe. The pane reads `self.app._whatsapp_driver` on first show.
- **API surface parity:** Headless mode (`headless.py`) is completely unaffected — it doesn't use TUI screens at all. CLI flags are unaffected.
- **Integration coverage:** The integration tests in `test_textual_tui.py` cover the full dry-run flow and will validate the end-to-end tab navigation works correctly.
- **Unchanged invariants:** The `whatsapp` CLI entry point, all CLI flags, headless mode, pipeline-only mode, Docker entrypoint, and all core export/pipeline logic remain unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Worker methods tightly coupled to Screen lifecycle (`on_worker_state_changed`) | Workers move to pane Container classes which also receive worker state events. Textual dispatches `Worker.StateChanged` to the widget that started the worker. |
| CSS selectors break when screens become panes | Unit 7 explicitly cleans up CSS. New selectors target pane Container classes instead of Screen classes. |
| `TabbedContent` tab underline animation may not match current PipelineHeader aesthetic | CSS customization via `Tab`, `Tabs`, `TabbedContent` selectors. The `:disabled` pseudo-class handles locked state styling natively. |
| Test churn — 28 integration tests + ~86 unit tests need updates | Tests are updated in Unit 7 after all panes are working. Worker method unit tests (which test methods directly) need minimal changes. |
| Number key hotkeys conflict with text input widgets | Bindings `1`-`4` must NOT use `priority=True`. Without priority, Textual Input widgets capture focus and consume digit key events. Number bindings on the app will only fire when no input widget has focus. |
| Vertical space division between TabbedContent and ActivityLog | MainScreen CSS must explicitly set heights (e.g., `TabbedContent { height: 1fr; }` and `ActivityLog { height: auto; max-height: 30%; }`). Without this, one widget may push the other off-screen. Match the current DiscoveryScreen pattern (`grid-rows: auto 1fr auto`). |

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-01-tui-tab-navigation-requirements.md](docs/brainstorms/2026-04-01-tui-tab-navigation-requirements.md)
- Related plan: [docs/plans/2026-03-26-002-refactor-textual-tui-consolidation-plan.md](docs/plans/2026-03-26-002-refactor-textual-tui-consolidation-plan.md) (completed — established current architecture)
- Textual TabbedContent source: `.venv/lib/python3.13/site-packages/textual/widgets/_tabbed_content.py`
- Textual ContentSwitcher source: `.venv/lib/python3.13/site-packages/textual/widgets/_content_switcher.py`
