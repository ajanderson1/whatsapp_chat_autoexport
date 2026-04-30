# CLAUDE.md
<!-- BEGIN:PROJECT_NOTE -->
## Project Note

This project's Obsidian project note: `/Users/ajanderson/Journal/Atlas/Whatsapp Chat AutoExport.md`

Read this note at the start of every session to understand current status, decisions, and context.
Update it when you complete significant work, make architectural decisions, or change direction.
<!-- END:PROJECT_NOTE -->

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project automates the export of WhatsApp chats from Android devices to Google Drive using Appium-based UI automation. WhatsApp's end-to-end encryption prevents direct data access, so this tool uses screen scraping and UI automation to navigate WhatsApp's interface and trigger exports programmatically.

**Key limitation**: This is a fragile screen scraping process vulnerable to WhatsApp UI changes. Monitor the script as it runs to catch any issues early.

## Commands

### Setup
```bash
# Install dependencies
poetry install

# Install Appium (required)
npm install -g appium

# Verify ADB is installed
adb devices
```

### Unified `whatsapp` Command (Recommended)

There is a single entry point: `whatsapp`. It runs in three modes.

#### TUI Mode (Default) — Interactive Textual interface
```bash
# Launch the Textual TUI — full wizard flow
poetry run whatsapp

# With options passed at launch
poetry run whatsapp --output ~/whatsapp_exports --limit 5 --debug
```

#### Headless Mode — Non-interactive, structured logging
```bash
# Full export + pipeline, no TUI
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select

# With transcriptions but no media in output (RECOMMENDED)
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --no-output-media

# Resume from previous session
poetry run whatsapp --headless --output ~/whatsapp_exports --resume /path/to/drive/folder

# Wireless ADB
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --wireless-adb 192.168.1.100:37453

# Limit to 5 chats
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --limit 5

# Without transcription
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --no-transcribe

# Force re-transcribe
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --force-transcribe

# Delete from Drive after processing
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --delete-from-drive
```

**Exit codes:** 0 = success, 1 = partial failure, 2 = fatal error

#### Pipeline-Only Mode — Process already-exported files
```bash
# Complete pipeline: download → extract → transcribe → build output
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output

# Without media in output
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output --no-output-media

# Without transcription
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output --no-transcribe

# Skip Drive download (local files only)
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output --skip-drive-download
```

#### All Available Flags
```
--output DIR              Output directory (required for --headless)
--headless                Run without TUI (structured logging to stderr)
--pipeline-only SRC OUT   Run pipeline only (no device connection)
--limit N                 Limit number of chats to export
--without-media           Export without media from WhatsApp
--no-output-media         Exclude media from final output (transcriptions still work)
--force-transcribe        Re-transcribe even if transcriptions exist
--no-transcribe           Skip transcription phase
--wireless-adb [ADDR]     Use wireless ADB (TUI prompts for details if no address given)
--debug                   Enable debug output
--resume PATH             Skip already-exported chats (scans Drive folder)
--delete-from-drive       Delete exports from Drive after processing
--keep-drive-duplicates   Skip deleting Drive root duplicates after download
--transcription-provider  Choose whisper (default) or elevenlabs
--skip-drive-download     Process local files without Drive download
--auto-select             Export all chats (required for --headless without --resume)
--skip-preflight          Skip credential capacity checks at startup (default: run)
```

### Deprecated Commands

The following commands are **deprecated** and will print a migration notice:

| Old Command | Replacement |
|---|---|
| `whatsapp-export` | `whatsapp --headless --output DIR` |
| `whatsapp-pipeline` | `whatsapp --pipeline-only SOURCE OUTPUT` |
| `whatsapp-process` | `whatsapp --pipeline-only SOURCE OUTPUT` |
| `whatsapp-drive` | `whatsapp --headless --output DIR` |
| `whatsapp-logs` | `whatsapp --debug` |

### Docker (Containerized Execution) 🐳

The entire workflow can be run in a Docker container. The default entrypoint is `whatsapp --headless`, so Docker runs in headless mode automatically. For the interactive TUI, override the entrypoint.

#### Build the Docker Image
```bash
docker build -t whatsapp-export .
```

#### USB ADB Connection (Recommended)

**Headless mode (default):**
```bash
# Basic export (headless is automatic in Docker)
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  whatsapp-export --output /output --auto-select

# With transcriptions but no media in output (RECOMMENDED)
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  whatsapp-export --output /output --auto-select --no-output-media

# Limit to 5 chats for testing
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  whatsapp-export --output /output --auto-select --limit 5
```

**Interactive TUI mode** (override entrypoint with `-it`):
```bash
docker run -it --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  --entrypoint whatsapp \
  whatsapp-export
```

#### Wireless ADB Connection

```bash
# Headless with wireless ADB (all details provided)
docker run --rm --network=host \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  whatsapp-export --output /output --auto-select \
  --wireless-adb 192.168.1.100:37453

# Interactive TUI with wireless ADB
docker run -it --rm --network=host \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  --entrypoint whatsapp \
  whatsapp-export
```

**Setup steps for wireless debugging:**
1. On Android: Settings → Developer Options → Wireless Debugging
2. Tap "Pair device with pairing code"
3. Note the **Pairing IP:PORT** (e.g., `192.168.1.100:37453`) and **6-digit code** (e.g., `123456`)

**Common issues:**
- Pairing codes expire after a few minutes
- Use the **pairing port** (shown in "Pair device" dialog), NOT port 5555
- Device must remain on the wireless debugging screen during pairing

#### Docker Environment Variables

Pass API keys at runtime:

```bash
# OpenAI Whisper (default)
-e OPENAI_API_KEY=your_key_here

# ElevenLabs Scribe
-e ELEVENLABS_API_KEY=your_key_here
```

#### Important Docker Notes

- **USB**: requires `--privileged` and `-v /dev/bus/usb:/dev/bus/usb`
- **Wireless**: requires `--network=host`
- **TUI**: requires `-it` and `--entrypoint whatsapp` (overrides default headless mode)
- Phone must be unlocked and remain unlocked throughout
- Container auto-cleans up with `--rm` flag

## Common Workflows

### Workflow 1: Interactive TUI (Recommended)
```bash
# Launch the TUI — walks you through connect, select, export, process
poetry run whatsapp
```
The TUI guides you through device connection, chat selection, export, and pipeline processing in a single interface.

### Workflow 2: Headless — Full Export with Transcriptions (No Media in Output) ⭐
```bash
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --no-output-media
```
**Result**: Chat transcripts + audio/video transcriptions. Media used for transcription but not kept in output.

### Workflow 3: Headless — Full Export (Media + Transcriptions)
```bash
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select
```
**Result**: Chat transcripts, media files, and transcriptions.

### Workflow 4: Pipeline-Only (Process Already-Exported Files)
```bash
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output
```
**Result**: Processes existing WhatsApp export zips through extract → transcribe → organize.

### Workflow 5: Minimal Export (No Transcriptions, No Media)
```bash
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --without-media --no-transcribe
```
**Result**: Chat transcripts only (text).

## Understanding Media Flags

**IMPORTANT**: There are THREE different media flags that serve different purposes:

### Export Flag: `--without-media`
- **Purpose**: Controls what WhatsApp exports to Google Drive
- **When to use**: Only use if you want minimal exports and don't need transcriptions
- **WARNING**: If you use this flag, voice message transcription will NOT work (no audio files to transcribe)
- **Default**: Exports WITH media (recommended for transcription support)

### Output Flag: `--no-output-media`
- **Purpose**: Controls what gets copied to the FINAL output folder
- **When to use**: When you want transcriptions but don't want to keep large media files
- **Benefit**: Transcriptions still work (media exists during processing, just not in final output)
- **Default**: Copies media to final output
- **Example**: `whatsapp --headless --output ~/exports --auto-select --no-output-media`

**Key Insight**: Always export WITH media (default), then use `--no-output-media` or `--no-media` to exclude media from final output while preserving transcription functionality.

## Drive Duplicate Cleanup

By default, after each successful per-chat download the pipeline deletes any
`WhatsApp Chat with <chat>` and `WhatsApp Chat with <chat> (N)` siblings from
Drive root so duplicates don't accumulate across runs.

- Default: **ON** — no flag needed.
- Opt out: `--keep-drive-duplicates` (leaves all Drive files alone).
- Orthogonal to `--delete-from-drive`: that flag only removes the
  just-downloaded file; duplicate cleanup removes the whole sibling group.
- Only affects Drive root. Does not touch subfolders.
- Cleanup failures never fail a chat — worst case, the next run retries.

## Credential Preflight

Before each run, the tool checks that configured API keys are valid and have sufficient capacity. This avoids wasted time when a key is missing, expired, or over-quota.

### Probes

| Provider | Check | WARN threshold | HARD FAIL threshold |
|---|---|---|---|
| OpenAI (Whisper) | `GET /v1/models` | — | No key / invalid key |
| ElevenLabs | `GET /v1/user/subscription` | < 50 000 chars remaining | 0 chars remaining |
| Google Drive | `about().get()` storage quota | < 5 GB free | < 500 MB free |

### Behaviour

- **HARD FAIL**: run is blocked. Fix the credential issue and retry.
- **WARN**: run continues with a warning logged.
- **SKIPPED**: no key configured for that provider — probe is skipped.
- **TUI**: `PreflightPanel` is the first widget on the Connect tab. Pressing `p` re-runs the check.
- **Headless / pipeline-only**: report printed to stderr before chat selection. Exit code 2 on hard fail.

### Opting out

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --skip-preflight
```

Use `--skip-preflight` to bypass all checks (e.g. offline testing, known-good credentials).

## Transcription Behavior

### Skip Existing Transcriptions (Default)

By default, the pipeline **skips re-transcribing** files that already have transcriptions. This saves time and API costs.

**How it works:**
- Before transcribing a media file, checks if `[filename]_transcription.txt` exists
- If found and valid (non-empty), skips transcription and reuses existing file
- User sees clear feedback: `⏭️  Skipping (exists): Chat Name/PTT-001.opus`
- Summary shows count and list of skipped files

**Example output:**
```
Transcribing 10 file(s) for: Chat Name

⏭️  Skipping (exists): Chat Name/PTT-001.opus
⏭️  Skipping (exists): Chat Name/VID-002.mp4
🎤 Transcribing: PTT-003.opus

======================================================================
Transcription Summary
======================================================================
Total files: 10
Successful: 2 (newly transcribed)
Skipped (existing): 7

Skipped files (existing transcriptions found):
  - Chat Name/PTT-001.opus
  - Chat Name/VID-002.mp4
  - Chat Name/PTT-005.opus
  ... and 4 more
======================================================================
```

### Force Re-Transcription

Use `--force-transcribe` to re-transcribe ALL audio/video files, even if transcriptions exist:

```bash
# Headless mode
poetry run whatsapp --headless --output ~/exports --auto-select --force-transcribe

# Pipeline-only mode
poetry run whatsapp --pipeline-only /downloads /output --force-transcribe
```

**When to use:**
- Poor quality transcriptions from previous run
- Language detection was incorrect
- Want to re-process with different settings
- Testing transcription improvements

**Note**: This will overwrite existing transcription files.

## Architecture

### Core Components

**whatsapp_export.py** - Main export automation script with four key classes:

1. **Logger** (line 143): Colored, categorized logging with debug mode support
   - `info()`, `success()`, `warning()`, `error()`, `debug_msg()`
   - Automatically handles presence/absence of colorama library

2. **AppiumManager** (line 267): Manages Appium server lifecycle
   - Starts/stops Appium server on port 4723
   - Can skip startup if `--skip-appium` flag is used
   - Handles graceful shutdown on script exit

3. **WhatsAppDriver** (line 327): Core UI automation driver using Appium + UiAutomator2
   - Connects to Android device via ADB (USB or wireless)
   - Manages WhatsApp connection and navigation
   - **CRITICAL SAFETY**: Includes robust WhatsApp verification to prevent accidental system UI interaction
   - Key methods:
     - `verify_whatsapp_is_open()`: **CRITICAL** - Verification that WhatsApp is the foregrounded app before ANY UI interaction. Checks:
       - Current package is com.whatsapp (not system settings or other apps)
       - Current activity is safe (not lock screen, system UI, or settings)
       - Phone is not locked
       - Called automatically by `connect()`, `interactive_mode()`, and before each export
       - **Note (#27):** the legacy resource-ID probe was removed — package + activity + lock-check are sufficient and resilient to WhatsApp UI redesigns.
     - `check_if_phone_locked()`: Detects if phone is locked by checking activity, package, and UI elements
     - `detect_phone_lock_state()`: User-friendly wrapper that provides clear error messages if phone is locked
     - `find_element()` / `find_elements()`: Locate UI elements by resource ID, text, or accessibility ID
     - `scroll_to_find_chat()`: Bidirectional scrolling with position change detection
     - `navigate_to_main_screen()`: Returns to main chat list
     - `restart_app_to_top()`: Restarts WhatsApp to reliably return to the top of the chat list. Faster and more reliable than scrolling (which would require 20-30 swipes from the bottom vs ~4-6s for restart). Used by `collect_all_chats()` before and after collection.
     - Handles chat collection using app restart to ensure consistent starting position

4. **ChatExporter** (line 934): Executes the export workflow
   - Opens chat → menu → "More" → "Export chat" → media option → Google Drive selection
   - Handles Google Drive "My Drive" vs "Drive" variations
   - Detects and skips incompatible chats (community chats)
   - Resume functionality: skips chats already present in specified Google Drive folder

**whatsapp_process.py** - Post-export file processor
- Finds files matching "WhatsApp Chat with ..." pattern
- Validates files are actual zip archives (checks magic bytes)
- Moves to "WhatsApp Chats Processed" folder
- Extracts and organizes into:
  - `transcripts/` - Chat text files (.txt)
  - `media/[chat name]/` - Media files organized by chat
- Uses parallel processing (ThreadPoolExecutor) for file operations
- Optional cleanup of zip files and extraction folders

**pipeline.py** - Orchestrates complete processing workflow
- **Phase 1**: Download from Google Drive (optional, uses `google_drive/drive_manager.py`)
- **Phase 2**: Extract and organize archives (uses `export/archive_extractor.py`)
- **Phase 3**: Transcribe audio/video files (uses `transcription/transcription_manager.py`)
  - Scans `media/[chat name]/` directories for transcribable files
  - **Pluggable Architecture**: Uses factory pattern (`transcription/transcriber_factory.py`) to select provider
    - **Whisper** (default): OpenAI Whisper API (`transcription/whisper_transcriber.py`)
    - **ElevenLabs**: ElevenLabs Scribe API (`transcription/elevenlabs_transcriber.py`)
  - Both providers implement `base_transcriber.py` interface
  - Creates `*_transcription.txt` files alongside media
  - **Skip Logic**: Checks both temp directory AND final output directory from previous runs
  - **Critical**: Requires media files to exist (runs on temporary extraction directory)
- **Phase 4**: Build final output structure (uses `output/output_builder.py`)
  - Creates organized output with merged transcripts
  - Optionally copies media files (`copy_media` parameter)
  - Optionally copies transcription files (`include_transcriptions` parameter)
  - **Key behavior**: Media copying can be disabled while preserving transcriptions
- **Phase 5**: Cleanup temporary files

**CLI Entry Point**: `cli_entry.py` provides the unified `whatsapp` command with three modes:
- **TUI mode** (default): Launches `WhatsAppExporterApp` Textual TUI
- **Headless mode** (`--headless`): Runs full export+pipeline with structured stderr logging
- **Pipeline-only mode** (`--pipeline-only`): Runs pipeline without device connection

**headless.py** - Non-interactive orchestrator for `--headless` and `--pipeline-only` modes:
- `run_headless(args)`: AppiumManager → WhatsAppDriver → ChatExporter → Pipeline, with structured logging and exit codes (0/1/2)
- `run_pipeline_only(args)`: Pipeline-only with upfront API key validation

**Progress Callbacks**: Pipeline and export classes accept optional `on_progress` callbacks:
- Signature: `on_progress(phase, message, current, total, item_name)`
- TUI callbacks use `call_from_thread()` for thread-safe UI updates
- Headless callbacks log to stderr

### Key Design Patterns

**Fragile UI Automation**: The script navigates WhatsApp by finding UI elements using resource IDs (e.g., `com.whatsapp:id/menuitem_search`) and text matching. These selectors are brittle and may break with WhatsApp updates.

**Bidirectional Scrolling**: When searching for a chat, the script scrolls both up and down (max 120 scrolls each direction, ~240 total) to handle chat position changes due to new messages during the search.

**Resume Functionality**: When `--resume` is used with a Google Drive folder path, the script:
1. Scans the folder for existing "WhatsApp Chat with ..." files
2. Extracts chat names from filenames
3. Skips exporting chats that already exist in the folder

**Google Drive Selection**: The script handles variations in Google Drive UI:
- Looks for both "My Drive" and "Drive" options (different Android versions)
- Uses helper function `_is_my_drive_option()` to detect correct option
- Implements multiple verification strategies for upload button

## Edge Cases & Known Issues

1. **CRITICAL SAFETY - WhatsApp Verification**: The script now includes comprehensive verification to prevent accidentally interacting with system settings or other non-WhatsApp UI:
   - **Multi-layer verification** runs at multiple checkpoints:
     - After initial connection to WhatsApp
     - Before collecting chat list
     - Before each individual chat export
   - **Verification checks**:
     - Current package is exactly `com.whatsapp` (not system settings or other apps)
     - Current activity is safe (not lock screen, system UI, or settings)
     - Phone is not locked (via multiple lock detection strategies)
     - **Cascade-halt (#27):** if `verify_whatsapp_is_open()` returns False three times in a row, the batch halts via `MAX_CONSECUTIVE_VERIFY_FAILURES = 3` to prevent a regressed verifier from poisoning the entire batch.
   - **Fail-fast behavior**: Script immediately exits with detailed error message if verification fails
   - **Action required**: Phone must be unlocked before running the script and remain unlocked throughout execution

2. **Chat position changes during search**: If a chat moves beyond the 240-scroll search range due to new messages, it will be skipped.

3. **Community chats**: Not supported - automatically skipped (WhatsApp doesn't allow export).

4. **"Advanced Chat Privacy has been turned on"**: Handling logic implemented in `_handle_advanced_chat_privacy_error()` method.

5. **Google Drive setup**: Script assumes "My Drive" or "Drive" is available. Not tested for missing Google Drive setup.

6. **Duplicate exports**: To avoid "WhatsApp Chat with ... (1)" naming, either:
   - Remove previous exports from Google Drive before running
   - Use `--resume` flag to skip already exported chats

## Important Notes for Development

- **CRITICAL SAFETY**: The script now includes robust verification (`verify_whatsapp_is_open()`) at multiple checkpoints to prevent accidentally interacting with system settings or other apps. This is called:
  - After connection
  - Before collecting chats
  - Before each export
- **Android SDK**: Must be installed (typically at `~/Library/Android/sdk` on macOS)
- **Python version**: Requires Python 3.13+
- **Device requirements**: USB debugging enabled (or wireless debugging for wireless ADB)
- **Phone must be unlocked**: The script includes comprehensive lock detection and will immediately exit if the phone is locked or WhatsApp is not accessible. Keep the phone unlocked throughout execution.
- **Do not interfere**: Script requires exclusive control of the device during operation
- **Timeout behavior**: Interactive prompts will timeout after a period; answer promptly
- **Limit flag**: Use `--limit` flag to limit chat processing during development
- **Fail-fast design**: If WhatsApp verification fails at any checkpoint, the script stops immediately to prevent unintended actions

## File Organization

```
whatsapp_chat_autoexport/
├── cli_entry.py                  # Unified CLI entry point (whatsapp command)
├── headless.py                   # Headless + pipeline-only orchestrators
├── deprecated_entry.py           # Deprecation wrappers for old commands
├── pipeline.py                   # Main pipeline orchestrator (with progress callbacks)
├── tui/
│   ├── textual_app.py            # WhatsAppExporterApp (Textual)
│   ├── textual_screens/
│   │   ├── discovery_screen.py   # Device connection (USB + wireless ADB)
│   │   ├── selection_screen.py   # Chat selection + export + processing + summary
│   │   └── help_screen.py        # Help overlay
│   ├── textual_widgets/          # 10 Textual widgets (progress, chat list, settings, etc.)
│   └── styles.tcss               # Textual stylesheet
├── export/
│   ├── whatsapp_driver.py        # WhatsApp UI automation (Appium)
│   ├── chat_exporter.py          # Export workflow (with progress callbacks)
│   └── appium_manager.py         # Appium server lifecycle
├── google_drive/
│   └── drive_manager.py          # Google Drive operations (with progress callbacks)
├── transcription/
│   ├── transcription_manager.py  # Batch transcription (with progress callbacks)
│   ├── whisper_transcriber.py    # OpenAI Whisper
│   └── elevenlabs_transcriber.py # ElevenLabs Scribe
├── output/
│   └── output_builder.py         # Final output builder (with progress callbacks)
├── state/
│   ├── state_manager.py          # Session/chat state tracking
│   ├── models.py                 # Pydantic state models
│   └── checkpoint.py             # Checkpoint save/restore
├── core/
│   ├── events.py                 # EventBus (sync pub/sub)
│   ├── errors.py                 # Structured error hierarchy
│   └── interfaces.py             # Protocol definitions
├── config/                       # Settings, themes, API key management
├── legacy/                       # Deprecated Rich TUI + Typer CLI (reference only)
└── __init__.py

Project root:
├── Dockerfile            # Docker config (entrypoint: whatsapp --headless)
├── docker-compose.yml    # Docker Compose profiles
├── CLAUDE.md             # Developer documentation (this file)
├── pyproject.toml        # Poetry dependencies and scripts
├── docs/
│   ├── brainstorms/      # Requirements documents
│   └── plans/            # Implementation plans
└── tests/
    ├── unit/             # 622 unit tests
    └── integration/      # 28 Textual pilot integration tests
```

## Testing Strategy

This project uses **pytest** for all testing. Tests are organized in the `tests/` directory with separate subdirectories for unit and integration tests.

### Test Organization

```
tests/
├── conftest.py                         # Shared fixtures (includes tui_app fixture)
├── unit/                               # Unit tests (fast, isolated) — 622 tests
│   ├── test_cli_entry.py               # CLI entry point mode dispatch (42 tests)
│   ├── test_deprecated_entry.py        # Deprecation wrappers (11 tests)
│   ├── test_pipeline_progress.py       # Pipeline progress callbacks (13 tests)
│   ├── test_export_progress.py         # Export progress callbacks (4 tests)
│   ├── test_discovery_screen.py        # Wireless ADB + device scanning (37 tests)
│   ├── test_selection_screen_export.py # Export progress wiring (24 tests)
│   ├── test_selection_screen_processing.py # Pipeline progress wiring (25 tests)
│   ├── test_headless.py               # Headless mode orchestrator (20 tests)
│   ├── test_pipeline_only.py          # Pipeline-only mode (9 tests)
│   ├── test_legacy_migration.py       # Legacy code migration (12 tests)
│   ├── test_state.py                  # State manager + models
│   ├── test_core.py                   # Events, interfaces, result types
│   ├── test_config.py                 # Settings, themes, API keys
│   ├── test_tui.py                    # Legacy Rich TUI tests
│   ├── test_transcription.py          # Transcription system
│   ├── test_transcript_parser.py      # Message parsing
│   ├── test_output_builder.py         # Output generation
│   └── test_archive_extractor.py      # Archive processing
├── integration/                        # Integration tests — 28 tests
│   ├── test_textual_tui.py            # Textual pilot tests (28 tests)
│   └── test_cli.py                    # CLI argument parsing
└── fixtures/                           # Test data and sample files
    └── sample_export/                  # Real WhatsApp export
```

### Running Tests

```bash
# Install test dependencies
poetry install --with dev

# Run all tests
poetry run pytest

# Run with coverage report
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=html

# Run only unit tests
poetry run pytest tests/unit/

# Run only integration tests
poetry run pytest tests/integration/

# Run specific test file
poetry run pytest tests/unit/test_transcription.py

# Run tests matching a pattern
poetry run pytest -k "transcription"

# Run fast tests only (exclude slow tests)
poetry run pytest -m "not slow"

# Run with verbose output
poetry run pytest -v

# Run with extra debugging info
poetry run pytest -vv

# Show print statements
poetry run pytest -s
```

### Test Markers

Tests are categorized using pytest markers:

- `@pytest.mark.unit`: Fast, isolated unit tests (no external dependencies)
- `@pytest.mark.integration`: Integration tests (may use subprocess, CLI)
- `@pytest.mark.slow`: Slow-running tests (large data, batch operations)
- `@pytest.mark.requires_api`: Tests requiring API keys (OpenAI, ElevenLabs)
- `@pytest.mark.requires_device`: Tests requiring Android device connection

Run specific categories:
```bash
# Run only unit tests
poetry run pytest -m unit

# Skip slow tests
poetry run pytest -m "not slow"

# Run tests that don't require API keys
poetry run pytest -m "not requires_api"
```

### Test Fixtures

Common fixtures available in all tests (defined in `conftest.py`):

- `project_root`: Path to project root directory
- `sample_data_dir`: Path to sample_data directory
- `sample_export_dir`: Path to real WhatsApp export (3,151 messages, 191 media files)
- `sample_transcript_file`: Path to sample transcript file
- `temp_output_dir`: Temporary output directory (auto-cleaned)
- `temp_working_dir`: Temporary working directory (auto-cleaned)
- `mock_transcriber`: Mock transcriber for testing without API calls
- `sample_messages`: Sample message data for parser testing
- `sample_media_files`: Sample media files in temp directory
- `mock_api_key`: Sets mock API keys for testing
- `tui_app`: WhatsAppExporterApp in dry-run mode with StateManager and temp output (for Textual pilot tests)

### Coverage

Target: **90% code coverage**

View coverage report:
```bash
# Generate HTML coverage report
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=html

# Open in browser (macOS)
open htmlcov/index.html

# View coverage in terminal
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing
```

Coverage is configured in `pyproject.toml` to:
- Exclude test files and cache directories
- Show missing line numbers
- Fail if coverage drops below 90%

### Writing New Tests

When adding new tests:

1. **Choose the right location**:
   - `tests/unit/` for isolated functionality
   - `tests/integration/` for end-to-end workflows

2. **Use descriptive names**:
   ```python
   def test_transcription_skips_existing_files():
       """Test that transcription manager skips already-transcribed files."""
   ```

3. **Use fixtures from conftest.py**:
   ```python
   def test_parse_transcript(sample_transcript_file):
       parser = TranscriptParser()
       messages, media = parser.parse_transcript(sample_transcript_file)
       assert len(messages) > 0
   ```

4. **Add appropriate markers**:
   ```python
   @pytest.mark.unit
   def test_fast_function():
       pass

   @pytest.mark.slow
   @pytest.mark.integration
   def test_full_pipeline():
       pass
   ```

5. **Use clear assertions**:
   ```python
   # Good: Descriptive assertion messages
   assert len(results) == 5, f"Expected 5 results, got {len(results)}"

   # Better: Use pytest's assertion rewriting
   assert result.success is True
   assert "expected text" in output
   ```

### Testing TUI (Manual Testing)

1. `poetry run whatsapp` — verify TUI launches with DiscoveryScreen
2. Test dry-run mode (press 'd' on DiscoveryScreen) to verify screen flow without device
3. Test wireless ADB input fields on DiscoveryScreen
4. With device: verify full flow through connect → select → export → process → summary

### Testing Headless Mode (Manual Testing)

1. `poetry run whatsapp --headless --output /tmp/test --auto-select --limit 2` — verify 2 chats export
2. Verify structured log output to stderr
3. Verify exit codes: 0 for success, 1 for partial failure, 2 for fatal error
4. Test `--resume` functionality by running twice on same folder
5. Test without `--auto-select` or `--resume` — should exit code 2 with guidance

### Testing Pipeline-Only (Manual Testing)

1. `poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output` — full pipeline
2. Test `--no-output-media` flag (verify transcriptions still created)
3. Test `--no-transcribe` flag
4. Verify output structure matches expectations

### CI/CD Integration

The pytest setup is ready for CI/CD:

**Example GitHub Actions workflow**:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install Poetry
        run: pip install poetry
      - name: Install dependencies
        run: poetry install --with dev
      - name: Run tests
        run: poetry run pytest --cov --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### Test Data

The project includes real sample data in `sample_data/WhatsApp Chat with Example/`:
- **Transcript**: 3,151 lines spanning 2017-2025
- **Media**: 191 files (116 PTT audio, 70 images, 1 video, 1 audio, 1 document)
- **Transcription**: 1 sample transcription file

This data is used by tests to ensure realistic testing conditions.

### Troubleshooting Tests

**Tests fail to find sample data**:
```bash
# Verify sample data exists
ls -la sample_data/

# Run with verbose output to see fixture paths
poetry run pytest -vv tests/unit/test_transcript_parser.py
```

**Import errors**:
```bash
# Reinstall dependencies
poetry install --with dev

# Verify package is installed in editable mode
poetry run pip list | grep whatsapp
```

**Coverage too low**:
```bash
# See which lines are missing coverage
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing

# Focus on specific module
poetry run pytest --cov=whatsapp_chat_autoexport.transcription tests/unit/test_transcription.py
```

<!-- Run `claude-tui-settings` to reconfigure. -->
