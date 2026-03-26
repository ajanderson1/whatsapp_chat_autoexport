---
date: 2026-03-26
topic: textual-tui-consolidation
---

# Textual TUI Consolidation

## Problem Frame

The project has three incomplete UI layers (Rich TUI ~95%, Textual TUI ~40-50%, Typer CLI ~65%) sitting on top of production-ready core logic (export via Appium, pipeline processing). This fragmentation means none of the frontends are fully wired up, maintenance is scattered, and new users face confusing overlapping entry points (`whatsapp-export`, `whatsapp-pipeline`, `whatsapp-process`, `whatsapp-drive`, `whatsapp-logs`, `whatsapp`). The goal is to consolidate to a single Textual TUI that covers the full workflow, inspired by the architecture patterns proven in the Claude TUI Tools project.

**Note:** The existing Textual TUI has screens and widgets but pipeline integration is shallow (single blocking calls, no real-time progress). The starting point is lower than it appears — plan accordingly.

## Requirements

- R1. **Single Textual TUI app covering full workflow**: Connect device -> Export chats -> Download from Drive -> Extract -> Transcribe -> Organize output. All phases visible and controllable from one interface. See [Screen Architecture](#screen-architecture) for the navigation model and [Error Handling UX](#error-handling-ux) for failure states.
- R2. **Pipeline remains independently usable**: The pipeline logic (`pipeline.py`, `WhatsAppPipeline`) must remain importable and callable without any TUI dependency. The `whatsapp --pipeline-only` flag provides CLI access to pipeline-only processing, replacing the deprecated `whatsapp-pipeline` command. The `whatsapp --headless` flag runs the full export+pipeline workflow without TUI. See [Headless Mode](#headless-mode) for behavior spec.
- R3. **Single `whatsapp` entry point**: Replaces the current Typer subcommand app (`whatsapp export`, `whatsapp process`, `whatsapp wizard`). With no args, launches the Textual TUI. With flags (`--headless`, `--pipeline-only`), runs non-interactively. All previous entry points (`whatsapp-export`, `whatsapp-pipeline`, `whatsapp-process`, `whatsapp-drive`, `whatsapp-logs`) become thin wrappers that print a deprecation notice with the equivalent new command, then exit.
- R4. **Clean model/widget separation for new code**: New screens and widgets follow the Claude TUI Tools pattern — business logic in models/core, UI in Textual screens and widgets. Widgets receive state, emit messages, no I/O in widgets. Existing Textual code is refactored toward this pattern opportunistically, not as a blocking prerequisite.
- R5. **Deprecated code moved to `legacy/`**: Rich TUI files (`tui/app.py`, `tui/wizard.py`, `tui/screens/`, `tui/components/`), Typer CLI (`cli/`), and old entry point modules moved to `legacy/`. Textual code (`tui/textual_app.py`, `tui/textual_screens/`, `tui/textual_widgets/`, `tui/styles.tcss`) stays and becomes the active TUI. Legacy folder deleted after Textual TUI passes all success criteria and a 2-week validation period.
- R6. **Progress visibility throughout**: Each workflow phase shows progress in the TUI. Adding progress callback hooks to `pipeline.py` and export classes is in scope (interface additions, not logic changes). See [Progress Model](#progress-model) for granularity per phase.
- R7. **All existing CLI flags supported**: `--limit`, `--without-media`, `--no-output-media`, `--force-transcribe`, `--no-transcribe`, `--wireless-adb`, `--debug`, `--resume`, `--delete-from-drive`, `--transcription-provider`, `--skip-drive-download`, `--auto-select` — passed as CLI flags at launch. The TUI does not have a persistent settings screen, but the device connection screen accepts wireless ADB input interactively, and the chat selection screen accepts limit/selection interactively.

## Screen Architecture

The TUI uses a **linear wizard flow** with the ability to go back to previous completed steps:

1. **Connect** — Device detection (auto-scan USB), wireless ADB input (IP:port, pairing code), connection status. If no device found: retry button + setup instructions.
2. **Select** — Scrollable chat list with checkboxes. Search/filter. Select-all/deselect-all. Resume-skipped chats shown as greyed-out with "already exported" label. Limit input field.
3. **Export** — Per-chat progress list showing current chat name and status (pending/exporting/done/failed/skipped). Running count: "Exporting 3 of 15". Failed chats show inline error with skip/retry options.
4. **Process** — Pipeline phases shown as a stepped progress display: Download -> Extract -> Transcribe -> Organize. Per-file granularity where available. Phase-level progress bar with current item name.
5. **Summary** — Final results: counts (exported, transcribed, failed, skipped), output path, errors encountered, time elapsed.

Navigation: Forward is automatic on phase completion. Back button available to review completed steps (read-only). User can quit at any point with confirmation.

## Error Handling UX

This is a fragile screen-scraping tool — errors are expected, not exceptional.

- **Device errors** (disconnect, phone locked, WhatsApp not open): Modal alert with clear message. Options: retry, quit.
- **Per-chat export errors** (community chat, privacy restriction, UI element not found): Inline status on the chat row (red "Failed: [reason]"). Workflow continues to next chat automatically. Failed chats collected in summary.
- **Pipeline errors** (Drive download failure, transcription API error): Inline error in the processing progress display. Non-fatal errors: skip and continue. Fatal errors: stop with summary of what completed.
- **Cancellation** (Ctrl+C, q, quit button): Confirmation modal. Options: cancel current chat only, cancel entire export, continue. Partial progress is saved — the `--resume` flag can pick up where it left off.

## Headless Mode

`whatsapp --headless --output ~/exports` runs the full export+pipeline workflow without TUI:

- **Output**: Structured log lines to stderr (timestamps, phase, status). No progress bars, no interactive prompts.
- **Exit codes**: 0 = success, 1 = partial failure (some chats failed), 2 = fatal error (no chats exported).
- **Interactive prompts resolved by**: `--auto-select` exports all chats. `--resume /path` skips already-exported. `--wireless-adb <ip:port> <code>` provides connection details. If a required input is missing and can't be auto-resolved, exit with error and guidance.
- **Docker**: Dockerfile updated to use `whatsapp --headless` as entrypoint. Interactive Docker mode (`-it`) can omit `--headless` to get the TUI.

## Progress Model

Progress callback hooks are added to pipeline.py and export classes (interface additions only — no logic changes):

| Phase | Granularity | Display |
|-------|------------|---------|
| Connect | Binary (connected/not) | Status indicator |
| Export | Per-chat, per-step within chat | Chat list with status icons + current step text |
| Download | Per-file | Progress bar + filename |
| Extract | Per-archive | Progress bar + archive name |
| Transcribe | Per-file | Progress bar + filename + provider |
| Organize | Per-chat | Progress bar + chat name |

## Success Criteria

- Running `whatsapp` launches a Textual TUI that can complete a full export-to-organized-output workflow
- Running `whatsapp --headless --output ~/exports` produces the same result as the current `whatsapp-export --output ~/exports`
- Running `whatsapp --pipeline-only /downloads /output` replaces `whatsapp-pipeline`
- Old entry points print deprecation notices with the equivalent new command
- Pipeline tests pass without any TUI dependency
- No direct Rich rendering imports (Console, Progress, Panel, Table, Live) or Typer imports in TUI or CLI entry-point modules outside of `legacy/` (Textual's internal Rich dependency is fine; core modules retaining their existing Logger are fine)

## Scope Boundaries

- **Not rewriting core export logic**: AppiumManager, WhatsAppDriver, ChatExporter logic stays as-is. Adding progress callback hooks (observer pattern) is in scope.
- **Not rewriting pipeline logic**: WhatsAppPipeline phases stay as-is. Adding progress callback hooks is in scope.
- **Not building a settings/config management screen**: TUI accepts input at workflow start (device address, chat selection). No persistent config file editor.
- **Not adding new export features**: No new WhatsApp automation capabilities.
- **Docker updated for new entry point**: Dockerfile uses `whatsapp --headless`. Interactive Docker (`-it`) gets TUI.
- **Not restructuring core modules**: The in-flight refactoring (automation/, config/, core/, state/, whatsapp/ directories) is a separate effort. This work builds on whichever module structure exists when implementation begins.

## Key Decisions

- **Textual over Rich/Typer**: Textual provides async workers, CSS theming, screen navigation, and reactive state — all needed for a multi-phase workflow app. Rich is presentation-only, Typer is CLI-only.
- **Full workflow in one app**: Rather than separate tools for export and processing, one TUI covers everything. Pipeline-only users get `--pipeline-only` flag.
- **Single entry point**: Replaces Typer subcommand structure. Reduces confusion. Headless flags preserve scriptability.
- **Legacy folder over immediate deletion**: Provides reference during migration. Deleted after 2-week validation.
- **R4 as guideline, not gate**: New code follows model/widget separation. Existing code refactored opportunistically, not as a prerequisite.
- **Progress hooks are in scope**: Adding callback/observer interfaces to pipeline.py and export classes is an interface change, not a logic change. This is the minimum needed to deliver R6.
- **EventBus may be bypassed**: The existing EventBus is sync/threaded and the Textual TUI already bypasses it with `call_from_thread()`. Planning should evaluate whether to bridge it to Textual messages or replace it with Textual's native reactive system.

## Dependencies / Assumptions

- Textual framework (already in use, ~v0.94.0+)
- Existing Textual TUI code provides a partial foundation (screens, widgets, state manager exist but pipeline integration is shallow — single blocking calls, no real-time progress)
- Pipeline and export core modules are stable and well-tested
- The in-flight code restructuring (automation/, config/, core/, state/ directories) is a separate effort; this work does not depend on it

## Outstanding Questions

### Deferred to Planning

- [Affects R1][Needs research] Validate the proposed linear wizard flow against the existing Textual screens. How much can be reused vs rebuilt?
- [Affects R4][Technical] Should the EventBus be bridged to Textual messages or replaced entirely with Textual's reactive system?
- [Affects R6][Technical] What Textual worker pattern best suits long-running Appium automation with per-step progress reporting?
- [Affects R3][Technical] CLI dispatch structure — argparse with mode flags, or Textual's built-in command system?
- [Affects R5][Needs research] What is the source of truth for export logic: monolithic `whatsapp_export.py` or refactored `export/` modules? This affects what the TUI imports.
- [Affects R5][Technical] `tui/__init__.py` imports both Rich and Textual components. Needs cleanup when moving Rich code to legacy/.

## Next Steps

-> `/ce:plan` for structured implementation planning
