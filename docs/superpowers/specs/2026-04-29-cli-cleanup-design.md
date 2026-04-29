# CLI Cleanup & Subcommand Restructure — Design

**Date:** 2026-04-29
**Status:** Draft (pending user review)
**Author:** AJ Anderson + Claude (brainstorming session)

## Problem

The `whatsapp` CLI has accreted flags and entry points over many feature waves and is now laborious to use day-to-day. Specific symptoms:

- The recommended invocation in the project note is **7 flags long** — strong signal that defaults no longer match real usage.
- **Two overlapping format flags** (`--format` and `--format-version`) with different internal meanings produce a confusing `--help`.
- **`--without-media`** is a footgun (silently breaks transcription) and CLAUDE.md actively warns against it.
- **Six phantom flags** are read via `getattr` in `headless.py` (`skip_appium`, `google_drive_folder`, `poll_interval`, `poll_timeout`, `transcription_language`, `skip_opus_conversion`) but **do not exist in the parser**. Dead defaulting code.
- **Five deprecated entry points** still ship in `pyproject.toml` (`whatsapp-export`, `-pipeline`, `-process`, `-drive`, `-logs`) printing migration notices.
- Modes are flag-triggered (`--headless`, `--pipeline-only`), forcing one parser to handle three disjoint surfaces and producing a busy `--help`.

## Goals

1. Make the daily headless invocation short — ideally `whatsapp run --wireless-adb IP:PORT` or just `whatsapp run`.
2. Give each mode (TUI, headless, pipeline-only) a focused `--help`.
3. Remove dead, redundant, and confusing flags.
4. Keep TUI usage frictionless — same defaults pick-up as headless.
5. Reversible. Hand-edited config beats hardcoded surprises.

## Non-Goals

- MCP sync CLI consolidation (`whatsapp-sync`, `-ingest`, `-migrate`, `-rebuild`) — out of scope, possible future fold-in under `whatsapp <subcommand>`.
- TUI screen redesign — purely a defaults-loading change at the entry point.
- Output format (`v2` vs `legacy`) migration decision — separate concern.
- Testing strategy — being revised under a parallel effort; this spec stays silent on test changes.

## Design

### 1. Subcommand-Based CLI

Replace flag-based mode selection with subcommands.

```
whatsapp                           # Launch TUI (default, no args)
whatsapp run --output DIR          # Headless export + pipeline
whatsapp pipeline SRC OUT          # Pipeline-only on existing files
```

Top-level `whatsapp --help` lists subcommands and global flags only (`--debug`, `--config`, `--version`). Each subcommand has its own focused `--help`.

**Migration window:** The flags `--headless` and `--pipeline-only` continue to dispatch correctly for **one release** with a one-line deprecation warning to stderr pointing to `run` / `pipeline`. Removed in the following release.

### 2. Config File

User-level defaults live in a TOML config file, loaded with a clear precedence chain.

**Location (in resolution order):**
1. `$XDG_CONFIG_HOME/whatsapp-autoexport/config.toml` (if `XDG_CONFIG_HOME` set)
2. `~/.config/whatsapp-autoexport/config.toml` (default)
3. `./.whatsapp-autoexport.toml` (project-local override, loaded *after* user config)

**Format:**

```toml
[defaults]
transcription_provider = "elevenlabs"
output_media           = false   # equivalent to --no-output-media
delete_from_drive      = true
wireless_adb           = true    # uses last known IP:PORT, or prompts
auto_select            = true

[paths]
output = "/Users/ajanderson/Journal/People/Correspondence/Whatsapp"
```

**Precedence (low → high):**
1. Parser defaults — conservative; match what a fresh user would expect
2. User config (`~/.config/whatsapp-autoexport/config.toml`)
3. Project config (`./.whatsapp-autoexport.toml`)
4. Environment variables — existing API key vars stay where they are; not duplicated in config
5. Explicit CLI flags

**Discoverability:** when a config file is loaded, `whatsapp --help` (and each subcommand's `--help`) displays `(from config)` next to defaulted values so help output never lies about actual behaviour.

**New global flag:** `--config PATH` for one-off runs against an alternate config.

**Bootstrap:** `whatsapp config init` subcommand — **in scope** — scaffolds a config file at `~/.config/whatsapp-autoexport/config.toml` with sensible defaults and inline comments. Idempotent; refuses to overwrite an existing file unless `--force` is passed.

### 3. Flag Cleanup

#### Removed

- `--format` (legacy/spec) — overlaps with `--format-version`; `output_format == "spec"` branch (`pipeline.py:638`) is unused.
- 5 deprecated entry points from `pyproject.toml`:
  - `whatsapp-export`
  - `whatsapp-pipeline`
  - `whatsapp-process`
  - `whatsapp-drive`
  - `whatsapp-logs`
- `whatsapp_chat_autoexport/deprecated_entry.py` — deleted with the entry points.

#### Renamed

- `--format-version` → `--format` (after the old `--format` is gone). Choices stay `v2` (default) / `legacy`.

#### Kept with explicit warning

- `--without-media` — stays. Help text and a runtime stderr warning at startup make clear it disables audio/video transcription. Warning fires once when the flag is set.

#### Phantom `getattr` defaults — cleaned up in `headless.py`

| Symbol | Decision | Reason |
|---|---|---|
| `skip_appium` | Hardcode `False` | Appium always required for export |
| `google_drive_folder` | Delete | No surface, no docs, no use |
| `poll_interval` | Hardcode in pipeline | Already adaptive backoff per project note |
| `poll_timeout` | Hardcode in pipeline | Same |
| `transcription_language` | Hardcode `None` (auto-detect) | Auto-detection works; flag unused |
| `skip_opus_conversion` | Hardcode `False` | Conversion required for transcription |

### 4. TUI Defaults Pick-Up

The TUI today reads from `argparse.Namespace` via `cli_entry.run_tui()` (`cli_entry.py:226-244`). Three changes:

1. **TUI reads the same config** — launching `whatsapp` with no args picks up user defaults (e.g. ElevenLabs as default provider in the settings widget, output path pre-filled).
2. **"Edit config" affordance** — small footer link / `c` keybinding opens the config file in `$EDITOR`.
3. **No structural changes** to screens, widgets, or pilot tests.

`WhatsAppExporterApp` constructor signature, all screens, and all widgets remain unchanged.

## Architecture & Code Touchpoints

### New modules

- `whatsapp_chat_autoexport/cli/config.py` — TOML loader, precedence resolver, `--help` annotation hook.
- `whatsapp_chat_autoexport/cli/subcommands/__init__.py` — subcommand dispatch.
- `whatsapp_chat_autoexport/cli/subcommands/run.py` — `whatsapp run` (current headless path).
- `whatsapp_chat_autoexport/cli/subcommands/pipeline.py` — `whatsapp pipeline` (current pipeline-only path).
- `whatsapp_chat_autoexport/cli/subcommands/tui.py` — `whatsapp` default (current TUI path).
- `whatsapp_chat_autoexport/cli/subcommands/config_init.py` — optional `whatsapp config init`.

### Modified modules

- `whatsapp_chat_autoexport/cli_entry.py` — replaced with subcommand dispatcher; thin shim that resolves `--headless` / `--pipeline-only` to `run` / `pipeline` for the deprecation window.
- `whatsapp_chat_autoexport/headless.py` — phantom `getattr` calls replaced with explicit attributes from the subcommand's parsed args; six removed-flag defaults inlined as constants in pipeline config.
- `pyproject.toml` — five deprecated entry points removed.

### Deleted modules

- `whatsapp_chat_autoexport/deprecated_entry.py`

## Migration Plan

1. **Implementation release** — ships subcommands, config file support, flag cleanup. Old `--headless` / `--pipeline-only` flags still dispatch with stderr deprecation notice.
2. **User action** — drop `~/.config/whatsapp-autoexport/config.toml` matching current project-note defaults; daily invocation shrinks to `whatsapp run --wireless-adb IP:PORT` or `whatsapp run`.
3. **Project note update** — replace 7-flag "Recommended command" block with the new short form.
4. **Follow-up release** — remove `--headless` / `--pipeline-only` flag aliases entirely.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Existing scripts break on subcommand transition | One-release deprecation window for `--headless` / `--pipeline-only` |
| Config file shadows surprising behaviour | `(from config)` annotation in `--help`; `--config` flag for one-off override |
| TOML library not in deps | `tomllib` is in stdlib (Python 3.11+); project requires 3.13+ |
| Removing phantom flags breaks an undocumented user | None of the six are referenced in docs, tests, or git history beyond their introduction; safe to remove |
| MCP sync CLI drift | Out of scope; flagged as future fold-in opportunity |

## Open Questions

None outstanding from brainstorming. Testing strategy is being revised under a parallel effort and will be defined there.

## Out of Scope (Captured)

- Folding MCP sync CLI under `whatsapp <subcommand>` — leave for a future spec.
- Output format (`v2` vs `legacy`) end-of-life decision — separate concern.
- Test refactor — handled by parallel testing-revision effort.
