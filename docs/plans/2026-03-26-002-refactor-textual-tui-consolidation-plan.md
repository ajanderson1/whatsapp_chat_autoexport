---
title: "refactor: Consolidate to single Textual TUI with unified entry point"
type: refactor
status: active
date: 2026-03-26
origin: docs/brainstorms/2026-03-26-textual-tui-consolidation-requirements.md
deepened: 2026-03-26
---

# Consolidate to Single Textual TUI with Unified Entry Point

## Overview

Replace three incomplete UI layers (Rich TUI, Textual TUI, Typer CLI) and six entry points with a single Textual TUI app and a single `whatsapp` CLI command. The Textual TUI covers the full workflow: device connection, chat export, and pipeline processing. Headless and pipeline-only modes provide non-interactive alternatives. All deprecated code moves to `legacy/`.

## Problem Frame

The project has a production-ready core (Appium export, pipeline processing) but three competing, partially-wired frontends and six confusing entry points. Users don't know which command to use. No single frontend can run the full workflow end-to-end. This consolidation picks the Textual TUI as the winner, wires it fully to the core, and deprecates everything else.

(see origin: docs/brainstorms/2026-03-26-textual-tui-consolidation-requirements.md)

## Requirements Trace

- R1. Single Textual TUI covering full workflow (Connect → Export → Process → Summary)
- R2. Pipeline remains independently importable; `--headless` and `--pipeline-only` flags for non-interactive use
- R3. Single `whatsapp` entry point; deprecated commands print migration notices
- R4. Clean model/widget separation for new code; existing code refactored opportunistically
- R5. Rich TUI, Typer CLI, old entry points moved to `legacy/`
- R6. Progress visibility throughout via callback hooks on pipeline and export classes
- R7. All existing CLI flags supported via CLI flags at launch + interactive TUI inputs

## Scope Boundaries

- Core export logic (AppiumManager, WhatsAppDriver, ChatExporter) stays as-is; only progress callback interfaces added
- Pipeline logic (WhatsAppPipeline phases) stays as-is; only progress callback interfaces added
- No persistent settings/config editor screen
- No new WhatsApp automation capabilities
- Docker updated for new entry point (`whatsapp --headless`)
- In-flight code restructuring (automation/, config/, core/, state/ dirs) is separate; this plan builds on current module structure

## Context & Research

### Relevant Code and Patterns

**Existing Textual TUI (partial foundation):**
- `tui/textual_app.py` — `WhatsAppExporterApp(App)` with reactive `current_stage`, theme support, event subscriptions
- `tui/textual_screens/discovery_screen.py` — Device scanning, Appium start, WhatsApp connect, chat collection via workers
- `tui/textual_screens/selection_screen.py` — **Unified screen** handling 4 modes (select/export/processing/complete) with internal mode transitions. This is the most substantial piece of existing code
- `tui/textual_screens/export_screen.py` — **Dead code**, superseded by SelectionScreen
- `tui/textual_screens/processing_screen.py` — **Dead code**, superseded by SelectionScreen
- `tui/textual_widgets/` — 10 widgets: PipelineHeader, ChatListWidget, SettingsPanel, ProgressPane, ActivityLog, QueueWidget, ProgressDisplay, CancelModal, SecretSettingsModal, ColorSchemeModal
- `tui/styles.tcss` — 916-line comprehensive stylesheet

**Core modules (the TUI's backend):**
- `export/whatsapp_driver.py` — `WhatsAppDriver`: sync, blocking, methods like `connect()`, `collect_all_chats()`, `click_chat()`, `verify_whatsapp_is_open()`, `quit()`
- `export/chat_exporter.py` — `ChatExporter.export_chat_to_google_drive()`: sync, blocking, no progress callback
- `export/appium_manager.py` — `AppiumManager.start_appium()`, `stop_appium()`
- `pipeline.py` — `WhatsAppPipeline.run(source_dir) -> Dict`: sync, blocking, no progress callback. 5 phases
- `state/state_manager.py` — `StateManager`: sync, thread-safe (RLock), manages `SessionState` with per-chat `ChatState`
- `state/checkpoint.py` — `CheckpointManager`: atomic JSON save/restore, interval-based saving
- `core/events.py` — `EventBus`: sync, thread-safe (Lock), pub/sub. Already bypassed by Textual TUI
- `utils/logger.py` — `Logger` with `on_message` callback. TUI uses this to forward log messages to UI

**Current entry points (pyproject.toml):**
- `whatsapp` → `cli.main:main` (Typer app with subcommands)
- `whatsapp-export` → `export.cli:main` (argparse, unified export+pipeline)
- `whatsapp-pipeline` → `pipeline_cli.cli:main` (argparse, standalone pipeline)
- `whatsapp-process` → `processing.cli:main`
- `whatsapp-drive` → `google_drive.cli:main`
- `whatsapp-logs` → `cli.logs:main`

**Patterns to follow (Claude TUI Tools reference):**
- Single CLI entry point dispatching to TUI (default) or headless via flags
- Pre-mount all widgets, toggle visibility for navigation
- Reactive properties for state propagation
- Workers for background I/O
- CSS theming with Textual design tokens

### Institutional Learnings

- TUI test coverage is ~20% — the lowest in the codebase. Plan for testing from the start.
- `chat_exporter.py` has 40+ bare `except:` clauses — error handling integration must account for swallowed exceptions
- Logger has class-level mutable state (`_shutdown = False`) causing test isolation issues
- Recovery building blocks exist: `reconnect()`, `is_session_active()`, `safe_driver_call()`, `restart_app_to_top()` in WhatsAppDriver
- Both `export_chats()` and `export_chats_with_new_workflow()` are actively used

## Key Technical Decisions

- **Keep 2-screen architecture**: The existing DiscoveryScreen + SelectionScreen (4 internal modes) is pragmatic and avoids complex screen-stack state management. Do NOT rebuild as 5 separate screens. "Back to review" is a mode transition within SelectionScreen that preserves (not clears) historical state.
- **Bypass EventBus for TUI**: Continue using `call_from_thread()` to bridge sync workers to Textual's async UI. The EventBus remains for StateManager integration but is not the primary progress channel. New progress hooks use callback functions, not EventBus events. Note: EventBus.emit() with zero subscribers is safe — it's fire-and-forget, appending to a capped history list (100 events). In headless mode, StateManager emits events that go to history-only with no listeners. This is harmless but pure waste; a low-priority cleanup could pass a no-op EventBus to StateManager in headless mode.
- **Argparse for CLI dispatch**: Simple argparse in a new entry module — not Typer, not Textual's command system. Three modes: TUI (default), headless (`--headless`), pipeline-only (`--pipeline-only`).
- **Progress via callback hooks**: Add optional `on_progress` callback parameters to `WhatsAppPipeline.run()` and `ChatExporter.export_chat_to_google_drive()`. Callers pass a callback; the callback is invoked at phase transitions and per-item progress. TUI callbacks use `call_from_thread()` to update widgets. Headless callbacks log to stderr. Note: `core/events.py` already defines `PipelineProgressEvent` with `phase`, `current`, `total`, `item_name`, `message` fields — the callback signature should mirror this shape.
- **TUI uses batch export method, not its own loop**: The current SelectionScreen has a custom export loop (`_export_single_chat`) that lacks session recovery, StateManager integration, and resume logic — creating a third code path divergent from both `export_chats()` and `export_chats_with_new_workflow()`. The TUI should call `export_chats_with_new_workflow()` (which already provides step-level granularity via `WorkflowResult.step_results` and calls `StateManager.record_step()`), passing progress callbacks for TUI updates. This eliminates the parity gap and inherits all recovery logic.
- **Dual resume mechanisms**: Checkpoint resume for mid-session recovery (cancellation, crash). Google Drive scan for cross-session resume. TUI combines both on the Select screen.
- **Consecutive failure detection for device disconnect**: Reference `ChatExporter.MAX_CONSECUTIVE_RECOVERIES` (currently 3) rather than hardcoding a separate threshold. The TUI should detect when the batch export method stops due to recovery exhaustion and show a modal: "Device may be disconnected — Retry / Skip remaining / Exit". This avoids maintaining a parallel failure counter with identical semantics.
- **Hardcoded output dir removed**: Replace `/Users/ajanderson/Journal/...` with `Path.home() / 'whatsapp_exports'` as default. `--output` flag overrides.

## Open Questions

### Resolved During Planning

- **Screen architecture (5 screens vs 2)?** Keep 2 screens. The unified SelectionScreen with 4 modes is simpler and already works. Refactoring to 5 screens adds complexity without user benefit.
- **EventBus bridge or bypass?** Bypass. The TUI already works around it. New code uses Textual's native reactive system + callbacks.
- **CLI framework?** Argparse. Typer adds a dependency for no benefit when there are no subcommands — just mode flags.
- **Source of truth for export logic?** The refactored `export/` modules. The Textual TUI already imports from there.
- **Which resume mechanism?** Both. Checkpoint for mid-session, Drive scan for cross-session. Not in conflict.

### Resolved During Deepening

- **Callback signature for progress hooks**: Mirror the existing `PipelineProgressEvent` shape from `core/events.py`: `on_progress(phase: str, message: str, current: int, total: int, item_name: str = "")`. Pipeline phases have natural insertion points: Phase 1 (per-file in `drive_manager.batch_download_exports` loop), Phase 2 (per-sub-step, 5 total — find/move/zip/extract/organize), Phase 3 (per-file in `transcription_manager.batch_transcribe` loop), Phase 4 (per-chat in `output_builder.batch_build_outputs` loop), Phase 5 (cleanup start/finish only).
- **Export code path**: TUI should call `export_chats_with_new_workflow()` rather than maintaining its own loop. This method already provides step-level granularity via `WorkflowResult.step_results` and calls `StateManager.record_step()`, eliminating the need for a custom TUI export loop.

### Deferred to Implementation

- Whether `tui/__init__.py` needs intermediate cleanup or can be replaced wholesale
- How the CancelModal's "Wait for current chat to finish" checkbox should integrate with the worker cancellation flow
- Final TCSS adjustments for new/modified widgets

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
CLI Entry (argparse)
  |
  |-- no flags ---------> WhatsAppExporterApp.run()  [Textual TUI]
  |                            |
  |                            DiscoveryScreen
  |                              → scan devices, start Appium, connect, collect chats
  |                            SelectionScreen (4 modes)
  |                              → select: chat checkboxes, settings
  |                              → export: per-chat Appium automation via workers
  |                              → processing: pipeline via workers
  |                              → complete: summary display
  |
  |-- --headless -------> run_headless()  [No TUI]
  |                            |
  |                            Same core: AppiumManager → WhatsAppDriver → ChatExporter → Pipeline
  |                            Structured log lines to stderr
  |                            Exit codes: 0/1/2
  |
  |-- --pipeline-only --> run_pipeline_only()  [No TUI]
                               |
                               Validate API keys upfront
                               WhatsAppPipeline.run() with log callbacks
                               Exit codes: 0/1/2

Progress flow (TUI mode):
  Worker thread                          UI thread
  ─────────────                          ─────────
  ChatExporter.export_chat(
    on_progress=callback
  )
  callback("step", "Opening menu...")  → call_from_thread(progress_pane.update_step, ...)
  callback("chat_done", "Chat Name")   → call_from_thread(chat_list.mark_done, ...)

  Pipeline.run(
    on_progress=callback
  )
  callback("phase", "Transcribing")    → call_from_thread(progress_pane.update_phase, ...)
  callback("item", "PTT-001.opus")     → call_from_thread(progress_pane.update_item, ...)
```

## Implementation Units

### Phase 1: Foundation (Progress hooks + CLI entry point)

- [ ] **Unit 1: Add progress callback hooks to pipeline and export classes**

**Goal:** Enable callers to receive granular progress updates from pipeline phases and per-chat export steps without changing core logic.

**Requirements:** R6

**Dependencies:** None

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py`
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py`
- Test: `tests/unit/test_pipeline_progress.py`
- Test: `tests/unit/test_export_progress.py`

**Approach:**
- Add optional `on_progress: Optional[Callable]` parameter to `WhatsAppPipeline.run()` and `WhatsAppPipeline.process_single_export()`. Signature mirrors existing `PipelineProgressEvent`: `on_progress(phase, message, current, total, item_name)`
- **Phase 1 (Download)**: Insert callback in `google_drive/drive_manager.py` `batch_download_exports()` loop — already iterates `for i, file in enumerate(files, 1)` with `file_name` available
- **Phase 2 (Extract)**: Insert callback between sub-calls in `_phase2_extract_and_organize()` (5 sub-steps: find → move → zip → extract → organize). Per-archive granularity requires wrapping `extract_zip_files()` since it's a delegated function
- **Phase 3 (Transcribe)**: Insert callback in `transcription_manager.py` `batch_transcribe()` loop — already iterates `for i, media_file in enumerate(media_files, 1)` with file name and total. Also outer loop in `_phase3_transcribe()` for per-chat level
- **Phase 4 (Build)**: Insert callback in `output/output_builder.py` `batch_build_outputs()` loop — iterates `for i, (transcript_path, media_dir) in enumerate(transcript_files, 1)`
- **Phase 5 (Cleanup)**: Callback at start/finish only — no iteration
- Add optional `on_progress: Optional[Callable]` to `ChatExporter.export_chat_to_google_drive()` for per-step updates. Note: `export_with_new_workflow()` already has step-level granularity via `WorkflowResult.step_results` — prefer hooking into that path
- Default is `None` — no callback, no behavior change. Existing callers unaffected

**Patterns to follow:**
- Logger `on_message` callback pattern already used in the codebase
- Keep callbacks optional with `if on_progress: on_progress(...)` guard

**Test scenarios:**
- Pipeline run with callback receives phase start/end events for all 5 phases
- Pipeline run with callback receives per-item events during transcription phase
- Pipeline run without callback behaves identically to current behavior
- ChatExporter with callback receives step events during export
- ChatExporter without callback behaves identically to current behavior
- Callback exceptions do not crash the pipeline or export

**Verification:**
- Existing pipeline tests still pass unchanged
- New tests confirm callback receives expected events in expected order

---

- [ ] **Unit 2: Create unified CLI entry point with mode dispatch**

**Goal:** Single `whatsapp` command that dispatches to TUI (default), headless, or pipeline-only mode.

**Requirements:** R2, R3, R7

**Dependencies:** None (can run in parallel with Unit 1)

**Files:**
- Create: `whatsapp_chat_autoexport/cli_entry.py`
- Modify: `pyproject.toml` (change `whatsapp` script entry)
- Test: `tests/unit/test_cli_entry.py`

**Approach:**
- Argparse-based. No subcommands — mode flags instead
- `whatsapp` (no flags) → imports and runs `WhatsAppExporterApp`
- `whatsapp --headless --output DIR` → calls `run_headless()` (stub initially, wired in Unit 7)
- `whatsapp --pipeline-only SOURCE OUTPUT` → calls `run_pipeline_only()` (stub initially, wired in Unit 8)
- All R7 flags parsed: `--limit`, `--without-media`, `--no-output-media`, `--force-transcribe`, `--no-transcribe`, `--wireless-adb`, `--debug`, `--resume`, `--delete-from-drive`, `--transcription-provider`, `--skip-drive-download`, `--auto-select`, `--output`
- Parsed args passed to whichever mode is selected
- TUI-only imports guarded behind `if mode == 'tui'` to avoid importing Textual in headless mode

**Patterns to follow:**
- Claude TUI Tools' `cli.py` dispatch pattern: parse args → branch to TUI or headless
- Existing `pipeline_cli/cli.py` for argparse style and flag definitions

**Test scenarios:**
- `whatsapp` with no args selects TUI mode
- `whatsapp --headless --output /tmp/test` selects headless mode with output dir
- `whatsapp --pipeline-only /downloads /output` selects pipeline-only mode with positional args
- `whatsapp --headless` without `--output` exits with error
- `whatsapp --pipeline-only` without positional args exits with error
- All R7 flags are parsed and accessible on the args namespace
- Invalid flag combinations (e.g., `--headless --pipeline-only`) produce clear error

**Verification:**
- `whatsapp --help` shows all flags organized by mode
- Mode detection works correctly for all three modes
- Args are correctly forwarded to the selected mode function

---

- [ ] **Unit 3: Create deprecation wrappers for old entry points**

**Goal:** Old commands (`whatsapp-export`, `whatsapp-pipeline`, etc.) print a deprecation notice with the equivalent new command and exit.

**Requirements:** R3

**Dependencies:** Unit 2 (need new entry point to reference)

**Files:**
- Create: `whatsapp_chat_autoexport/deprecated_entry.py`
- Modify: `pyproject.toml` (point old scripts to deprecation wrappers)

**Approach:**
- Single module with one function per deprecated command
- Each prints: `⚠️  'whatsapp-export' is deprecated. Use: whatsapp --headless --output DIR` (or equivalent)
- Exits with code 0 after printing
- Map of old → new command in a dict for maintainability

**Patterns to follow:**
- Claude TUI Tools' deprecation approach (archived old repos with redirect notices)

**Test scenarios:**
- Each deprecated command prints the correct migration notice
- Each deprecated command exits with code 0
- Notice includes the exact equivalent new command

**Verification:**
- Running any old command shows clear guidance to the new command

---

### Phase 2: Wire TUI to progress hooks + fix existing issues

- [ ] **Unit 4: Wire DiscoveryScreen for wireless ADB input**

**Goal:** Add interactive wireless ADB input fields to the Connect screen so users can pair without CLI flags.

**Requirements:** R1, R7

**Dependencies:** None

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_screens/discovery_screen.py`
- Modify: `whatsapp_chat_autoexport/tui/styles.tcss`
- Test: `tests/unit/test_discovery_screen.py`

**Approach:**
- Add a "Wireless ADB" section below the device list: IP:port Input, pairing code Input, Connect button
- On Connect: run `adb pair <ip:port> <code>` then `adb connect <ip>:5555` via worker
- Show connection status (pairing... connected... failed with reason)
- If `--wireless-adb` was passed via CLI, pre-fill the fields and auto-connect on mount
- Existing USB device scan continues to work alongside

**Patterns to follow:**
- Existing DiscoveryScreen worker pattern for device scanning
- SettingsPanel Input widget pattern for text fields

**Test scenarios:**
- Wireless ADB section renders with IP:port and pairing code fields
- Successful pair + connect transitions to chat collection
- Failed pairing shows error message with "codes expire" hint
- Pre-filled fields from CLI args auto-connect on mount
- USB and wireless paths work independently

**Verification:**
- Device connection works via both USB scan and wireless ADB input
- Error messages are clear and actionable

---

- [ ] **Unit 5: Wire SelectionScreen export mode to progress callbacks**

**Goal:** Per-chat export progress shows real-time step updates in the TUI via the new progress callback hooks.

**Requirements:** R1, R6

**Dependencies:** Unit 1 (progress hooks on ChatExporter)

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_screens/selection_screen.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/progress_pane.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/chat_list.py`
- Test: `tests/unit/test_selection_screen_export.py`

**Approach:**
- **Critical: Replace the TUI's custom export loop.** The current `_export_single_chat()` / `_run_export()` is a third code path that lacks session recovery, StateManager integration, and resume logic. Refactor to call `ChatExporter.export_chats_with_new_workflow()` instead, which provides: step-level granularity via `WorkflowResult.step_results`, automatic `StateManager.record_step()` calls, consecutive recovery tracking via `MAX_CONSECUTIVE_RECOVERIES`, and session recovery via `_attempt_session_recovery()`
- Pass `on_progress` callback to the batch method. Callback uses `self.app.call_from_thread()` to update ProgressPane with current step text and ChatListWidget with per-chat status
- Detect when batch export stops due to recovery exhaustion (`MAX_CONSECUTIVE_RECOVERIES` reached) and show CancelModal with "Device may be disconnected" message. Reference the constant from `ChatExporter` rather than maintaining a parallel counter
- Wire up CancelModal's "Wait for current chat to finish" checkbox to actually defer cancellation until the current chat's worker completes
- Preserve export state when navigating back from complete mode (don't clear `_export_results` in `_return_to_selection()`)

**Patterns to follow:**
- Existing `on_message` callback on Logger used in SelectionScreen
- `call_from_thread()` pattern already used throughout

**Test scenarios:**
- Export progress updates appear in ProgressPane during per-chat export
- ChatListWidget shows per-chat status transitions (pending → exporting → done/failed)
- Three consecutive failures trigger device disconnect modal
- Successful export after failure resets the consecutive counter
- CancelModal "Wait for current chat" defers cancellation
- Back navigation from complete mode preserves export results (read-only)

**Verification:**
- User can see which step each chat is on during export
- Device disconnect is detected and actionable
- Cancel modal respects the wait checkbox

---

- [ ] **Unit 6: Wire SelectionScreen processing mode to pipeline progress callbacks**

**Goal:** Pipeline processing shows per-phase, per-file progress in the TUI via the new progress callback hooks.

**Requirements:** R1, R6

**Dependencies:** Unit 1 (progress hooks on WhatsAppPipeline)

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_screens/selection_screen.py`
- Modify: `whatsapp_chat_autoexport/tui/textual_widgets/progress_pane.py`
- Test: `tests/unit/test_selection_screen_processing.py`

**Approach:**
- In `_run_processing()`, pass `on_progress` callback to `pipeline.run()`
- Callback uses `call_from_thread()` to update ProgressPane with current phase, current item, and progress bar position
- ProgressPane shows stepped display: Download → Extract → Transcribe → Organize with active phase highlighted
- Each phase shows progress bar + current item name
- Pipeline errors shown inline. Non-fatal: skip and continue. Fatal: stop with summary

**Patterns to follow:**
- Unit 5's callback + `call_from_thread()` pattern
- Existing ProgressPane has `update_processing_step()` — extend for per-file granularity

**Test scenarios:**
- Processing progress shows all pipeline phases in order
- Per-file progress updates during transcription phase
- Non-fatal transcription error shows inline, processing continues
- Fatal error stops processing and shows summary of what completed
- Progress bar advances correctly based on current/total counts

**Verification:**
- User can see which pipeline phase is active and which file is being processed
- Errors are visible without stopping the entire pipeline (for non-fatal)

---

### Phase 3: Headless and pipeline-only modes

- [ ] **Unit 7: Implement headless mode orchestrator**

**Goal:** `whatsapp --headless --output DIR` runs the full export+pipeline workflow without TUI, with structured logging and proper exit codes.

**Requirements:** R2, R7

**Dependencies:** Unit 1 (progress hooks), Unit 2 (CLI entry point)

**Files:**
- Create: `whatsapp_chat_autoexport/headless.py`
- Test: `tests/unit/test_headless.py`

**Approach:**
- `run_headless(args)` function: creates AppiumManager, WhatsAppDriver, ChatExporter, WhatsAppPipeline
- Structured log lines to stderr: `[TIMESTAMP] [PHASE] [STATUS] message`
- Chat selection: `--auto-select` → all chats. `--resume /path` → skip exported. `--limit N` → cap. Missing required input → exit code 2 with guidance
- Progress callbacks log to stderr (same interface as TUI callbacks, different implementation)
- Appium lifecycle managed internally: start on enter, stop on exit (context manager pattern)
- Exit codes: 0 = all success, 1 = partial failure (some chats failed or pipeline had non-fatal errors), 2 = fatal (no device, no chats exported, pipeline crash)
- API key validation upfront if transcription enabled

**Patterns to follow:**
- Existing `export/cli.py` for the overall orchestration flow (it already does export + pipeline)
- Logger with `on_message` for structured output

**Test scenarios:**
- Headless with `--auto-select` exports all collected chats
- Headless with `--resume /path` skips already-exported chats
- Headless without `--output` exits code 2 with error message
- Headless without device connection exits code 2 with guidance
- Headless with partial export failures returns code 1
- Headless with full success returns code 0
- Appium server is cleaned up on normal exit and on failure
- API key validated upfront when transcription enabled

**Verification:**
- Headless produces structured, parseable log output
- Exit codes reflect the actual outcome
- No Textual imports in this module

---

- [ ] **Unit 8: Implement pipeline-only mode**

**Goal:** `whatsapp --pipeline-only SOURCE OUTPUT` runs the pipeline without device connection or TUI.

**Requirements:** R2, R7

**Dependencies:** Unit 1 (progress hooks), Unit 2 (CLI entry point)

**Files:**
- Modify: `whatsapp_chat_autoexport/headless.py` (add `run_pipeline_only()`)
- Test: `tests/unit/test_pipeline_only.py`

**Approach:**
- `run_pipeline_only(args)` function: creates WhatsAppPipeline with PipelineConfig from args
- Validate API keys upfront if transcription enabled (not `--no-transcribe`)
- Structured log output via progress callbacks
- Same exit code scheme as headless
- Replaces `whatsapp-pipeline` functionality — same flags, same behavior

**Patterns to follow:**
- Existing `pipeline_cli/cli.py` for PipelineConfig construction and flag mapping

**Test scenarios:**
- Pipeline-only with valid source/output runs all phases
- Pipeline-only with `--no-transcribe` skips transcription phase
- Pipeline-only with missing API key and transcription enabled exits code 2
- Pipeline-only with invalid source path exits code 2
- Progress output shows phase transitions

**Verification:**
- Produces identical results to current `whatsapp-pipeline` command
- No Textual or Appium imports in this code path

---

### Phase 4: Legacy migration + cleanup

- [ ] **Unit 9: Move deprecated code to legacy/ and clean up imports**

**Goal:** Rich TUI, Typer CLI, and dead Textual screens moved to `legacy/`. Active Textual code cleaned of Rich-TUI imports.

**Requirements:** R5

**Dependencies:** Units 2-8 complete (new TUI fully functional)

**Files:**
- Move to `legacy/`: `tui/app.py`, `tui/wizard.py`, `tui/screens/`, `tui/components/`, `cli/` (entire directory), `tui/textual_screens/export_screen.py` (dead code), `tui/textual_screens/processing_screen.py` (dead code)
- Modify: `tui/__init__.py` (remove Rich TUI exports, keep only Textual exports)
- Modify: `pyproject.toml` (verify entry points point to new modules)
- Test: `tests/unit/test_legacy_migration.py`

**Approach:**
- Create `legacy/` directory at package root
- Move files preserving directory structure under `legacy/`
- Update `tui/__init__.py` to only export Textual app and screens
- Verify no imports from `legacy/` remain in active code
- Update test imports if any tests reference moved modules
- Remove hardcoded output dir (`/Users/ajanderson/Journal/...`) from `textual_app.py` and `settings_panel.py` — replace with `Path.home() / 'whatsapp_exports'`

**Patterns to follow:**
- Claude TUI Tools' clean separation: archived old code, no lingering imports

**Test scenarios:**
- No import errors when running the Textual TUI after migration
- No import errors when running headless or pipeline-only modes
- Legacy code is present in `legacy/` for reference
- `tui/__init__.py` exports only Textual components
- Hardcoded output dir replaced with generic default

**Verification:**
- `python -c "from whatsapp_chat_autoexport.tui import WhatsAppExporterApp"` succeeds
- `python -c "from whatsapp_chat_autoexport.headless import run_headless"` succeeds with no Textual/Rich imports
- No Rich Console/Progress/Panel/Table/Live or Typer imports in active code (outside `legacy/`)

---

- [ ] **Unit 10: Update Docker configuration**

**Goal:** Dockerfile uses `whatsapp --headless` as entrypoint. Interactive Docker mode (`-it`) gets TUI.

**Requirements:** R2 (Docker scope boundary from origin)

**Dependencies:** Unit 7 (headless mode)

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

**Approach:**
- Change ENTRYPOINT from `whatsapp-export` to `whatsapp --headless`
- Interactive Docker (`-it`) can override with `whatsapp` (no `--headless`) to get TUI
- Verify `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` env var passthrough still works

**Test scenarios:**
- `docker run whatsapp-export --output /output` uses headless mode
- `docker run -it whatsapp-export` can launch TUI
- API key env vars are passed through correctly

**Verification:**
- Docker build succeeds
- Non-interactive Docker runs use headless mode by default

---

### Phase 5: Testing

- [ ] **Unit 11: Textual TUI integration tests**

**Goal:** Textual pilot-based tests covering the full wizard flow with mocked backend.

**Requirements:** R1 (all phases), R6 (progress visibility)

**Dependencies:** Units 4-6 (TUI wiring complete)

**Files:**
- Create: `tests/integration/test_textual_tui.py`
- Modify: `tests/conftest.py` (add Textual-specific fixtures)

**Approach:**
- Use Textual's `pilot` test harness (`async with app.run_test() as pilot`)
- Mock `AppiumManager`, `WhatsAppDriver`, `ChatExporter`, `WhatsAppPipeline` — tests should not need a real device
- Test full flow: mount → DiscoveryScreen → mock device → SelectionScreen → select chats → export mode → processing mode → complete mode
- Test error flows: no device found, export failure with retry, pipeline failure with summary
- Test cancellation: cancel during export, verify modal appears, verify state preservation
- Test wireless ADB input flow

**Patterns to follow:**
- Existing `test_tui_flow.py` at project root (untracked) for pilot pattern reference
- Textual's official testing docs for pilot API

**Test scenarios:**
- Full happy path: connect → select → export → process → summary
- No device found: retry button visible, setup instructions shown
- Export failure: failed chat shown inline, export continues to next chat
- Three consecutive failures: device disconnect modal appears
- Cancel during export: modal shown, "Return to Selection" preserves state
- Wireless ADB: input fields, pairing flow, error messages
- Processing progress: all phases shown, per-item updates visible
- Pipeline error: inline error, partial completion summary

**Verification:**
- All pilot tests pass with mocked backends
- Coverage for DiscoveryScreen, SelectionScreen (all 4 modes), ProgressPane, ChatListWidget, CancelModal

## System-Wide Impact

- **Interaction graph:** CLI entry point → TUI app or headless orchestrator → AppiumManager + WhatsAppDriver + ChatExporter + WhatsAppPipeline. Progress callbacks flow from core classes → TUI widgets (via `call_from_thread`) or → stderr (headless). StateManager continues to track session state independently.
- **Error propagation:** Core classes raise/return errors as they do today. The TUI calls `export_chats_with_new_workflow()` which handles per-chat errors and session recovery internally. Consecutive recovery exhaustion (`MAX_CONSECUTIVE_RECOVERIES`) surfaces to the TUI as a batch-level result. Pipeline errors are caught per-phase with partial-completion reporting.
- **State lifecycle risks:** Cancellation during export must save checkpoint before cleanup. Cancellation during pipeline is coarser — pipeline phases are not individually checkpointed. The 1-second delay between export completion and pipeline start is preserved. In headless mode, EventBus has zero subscribers (StateManager still works, events go to history-only).
- **API surface parity:** The `--headless` and `--pipeline-only` flags must support all R7 flags. The TUI must accept the same configuration via CLI flags at launch + interactive inputs.
- **Multi-surface parity verification:** "Identical results" means same output directory structure, same files, same transcription outputs — NOT same log output or progress reporting. Parity test: run the same scenario through headless and pipeline-only modes on `sample_data/` fixture and diff the output directories against the current `whatsapp-pipeline` output. Intentional behavioral differences: TUI shows modal on recovery exhaustion; headless logs and exits code 1. Document these explicitly to prevent false parity concerns.
- **Export code path convergence:** By switching the TUI to call `export_chats_with_new_workflow()`, all three modes (TUI, headless, pipeline-only) share the same export and pipeline code paths. Bug fixes to session recovery, StateManager, or ChatExporter automatically propagate to all surfaces.
- **Integration coverage:** Textual pilot tests with mocked backends cover the TUI integration layer. Existing pipeline and export unit tests cover the core. Parity diff test covers output equivalence. The gap is end-to-end with a real device — this remains manual testing.

## Risks & Dependencies

- **Risk: Export loop divergence** — The current TUI has its own export loop (`_export_single_chat`) that lacks session recovery, StateManager integration, and resume logic. If Unit 5 doesn't successfully refactor this to use `export_chats_with_new_workflow()`, any bug fix to ChatExporter's recovery logic won't propagate to the TUI. Mitigation: Unit 5 explicitly requires this refactor. If the batch method's interface doesn't support the TUI's pause/cancel needs, extend the interface rather than maintaining a parallel loop.
- **Risk: Bare `except:` clauses in ChatExporter** — Progress callbacks may not fire for silently swallowed exceptions. Mitigation: Wrap callbacks in try/except so they don't interfere, and log when export steps complete without progress events.
- **Risk: Logger `_shutdown` class-level state** — Affects test isolation for TUI tests. Mitigation: Reset Logger state in test fixtures.
- **Risk: Textual version compatibility** — The project pins `>=0.94.0`. Pilot testing API may vary. Mitigation: Pin to a specific version in dev dependencies if issues arise.
- **Dependency: In-flight restructuring** — The automation/, config/, core/, state/ directories in git status are untracked. If these are committed before this work starts, file paths may change. Mitigation: This plan references the current module structure. If restructuring lands first, file paths in Units 4-6 and 9 need updating.

## Documentation / Operational Notes

- CLAUDE.md needs updating after completion: new entry point documentation, deprecation notices, updated file organization section
- Docker documentation in CLAUDE.md needs updating for `whatsapp --headless` entrypoint
- README.md commands section needs updating (if it exists beyond CLAUDE.md)

## Sources & References

- **Origin document:** [docs/brainstorms/2026-03-26-textual-tui-consolidation-requirements.md](docs/brainstorms/2026-03-26-textual-tui-consolidation-requirements.md)
- **Claude TUI Tools architecture:** /Users/ajanderson/Journal/Atlas/Claude TUI Tools.md — hub-and-spoke UX, model/widget separation, single CLI dispatch
- **Existing Textual TUI:** `tui/textual_app.py`, `tui/textual_screens/`, `tui/textual_widgets/`
- **Pipeline:** `pipeline.py`, `pipeline_cli/cli.py`
- **Export core:** `export/whatsapp_driver.py`, `export/chat_exporter.py`, `export/appium_manager.py`
- **State:** `state/state_manager.py`, `state/models.py`, `state/checkpoint.py`
- **Events:** `core/events.py`
- **Session recovery plan:** `docs/plans/2026-03-26-001-fix-export-batch-session-recovery-plan.md`
