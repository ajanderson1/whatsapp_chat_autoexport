# CLAUDE.md

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

### Export WhatsApp Chats
```bash
# Basic export (interactive mode)
poetry run python whatsapp_chat_autoexport/whatsapp_export.py

# With debug output
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --debug

# Limit number of chats
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --limit 5

# Export without media
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --without-media

# Resume mode (skip already exported chats)
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --resume /path/to/google/drive/folder

# Wireless ADB connection
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --wireless-adb 192.168.1.100:5555
```

### Process Exported Files (Basic)
```bash
# Process downloaded exports
poetry run python whatsapp_chat_autoexport/whatsapp_process.py /path/to/downloads

# With debug output
poetry run python whatsapp_chat_autoexport/whatsapp_process.py --debug /path/to/downloads
```

### Unified Export + Pipeline (Recommended) ⭐
```bash
# Complete workflow: export → download → transcribe → organize
poetry run whatsapp-export --output ~/whatsapp_exports

# With transcriptions but WITHOUT media in final output (RECOMMENDED)
poetry run whatsapp-export --output ~/whatsapp_exports --no-output-media

# Force re-transcribe all audio/video (ignores existing transcriptions)
poetry run whatsapp-export --output ~/whatsapp_exports --force-transcribe

# Without transcription (faster)
poetry run whatsapp-export --output ~/whatsapp_exports --no-transcribe

# Delete from Drive after processing
poetry run whatsapp-export --output ~/whatsapp_exports --delete-from-drive

# Limit to 5 chats
poetry run whatsapp-export --output ~/whatsapp_exports --limit 5
```

### Standalone Pipeline (For Already-Exported Files)
```bash
# Complete pipeline: download → extract → transcribe → build output
poetry run whatsapp-pipeline /path/to/downloads /path/to/output

# Pipeline with transcriptions but WITHOUT media in final output
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --no-media

# Pipeline without transcription
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --no-transcribe

# Pipeline with minimal output (no media, no transcriptions)
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --no-media --no-transcribe

# Skip Google Drive download (process local files only)
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --skip-drive-download
```

### Docker (Containerized Execution) 🐳

The entire workflow can be run in a Docker container for easier setup and portability. This eliminates the need to install Python, Node.js, Appium, and ADB on your host machine.

#### Build the Docker Image
```bash
# Build the image
docker build -t whatsapp-export .

# Or use docker-compose
docker-compose build
```

#### USB ADB Connection (Recommended)
```bash
# Basic export with USB connection
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output

# With transcriptions but no media in output (RECOMMENDED)
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --no-output-media

# Limit to 5 chats for testing
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --limit 5

# Using docker-compose (USB)
docker-compose --profile usb run --rm whatsapp-export-usb --output /output --limit 5
```

#### Wireless ADB Connection
```bash
# Container establishes connection automatically - no need to connect from host
docker run --rm --network=host \
  -v ./output:/output \
  whatsapp-export --output /output --wireless-adb 192.168.1.100:5555

# Using docker-compose (wireless)
# Edit docker-compose.yml to set your DEVICE_IP first
docker-compose --profile wireless run --rm whatsapp-export-wireless

# Note: The container's ADB server connects directly to the device
# No need to run 'adb connect' on the host beforehand
```

#### Docker Environment Variables

**API keys are optional at build time but required at runtime for transcription.**

The tool will validate API keys if they're set, or skip validation with a warning if they're not. Pass API keys at runtime:

```bash
# OpenAI Whisper (default)
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY=your_key_here \
  whatsapp-export --output /output

# ElevenLabs Scribe
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e ELEVENLABS_API_KEY=your_key_here \
  whatsapp-export --output /output --transcription-provider elevenlabs
```

#### Important Docker Notes

**Device Access:**
- USB connection requires `--privileged` and mounting `/dev/bus/usb`
- Wireless ADB requires `--network=host` for container to reach device
- Phone must be unlocked before running and remain unlocked throughout

**Volume Mounts:**
- `-v ./output:/output` - Maps local output directory to container
- `-v ./downloads:/downloads` - Optional: for intermediate downloads
- Use absolute paths or `./` relative paths for volume mounts

**Container Lifecycle:**
- Container runs the export and stops automatically (`--rm` flag removes it)
- Appium server starts/stops automatically inside container
- All temporary files are cleaned up on exit

**Troubleshooting:**
```bash
# Check if device is visible to Docker
docker run --rm --privileged -v /dev/bus/usb:/dev/bus/usb whatsapp-export adb devices

# View help inside container
docker run --rm whatsapp-export --help

# Run with debug output
docker run --rm --privileged -v /dev/bus/usb:/dev/bus/usb -v ./output:/output \
  whatsapp-export --output /output --debug
```

## Common Workflows

### Workflow 1: Full Export (Media + Transcriptions)
```bash
# Step 1: Export WITH media (default - required for transcription)
poetry run python whatsapp_chat_autoexport/whatsapp_export.py

# Step 2: Process with full pipeline
poetry run whatsapp-pipeline /path/to/downloads /path/to/output
```
**Result**: Final output includes chat transcripts, media files, and transcriptions.

### Workflow 2: Transcriptions Only (No Media in Final Output) ⭐ RECOMMENDED

**Option A: Using unified export command (simpler)**
```bash
# Single command: export → download → transcribe → organize (no output media)
poetry run whatsapp-export --output ~/whatsapp_exports --no-output-media
```

**Option B: Using separate commands**
```bash
# Step 1: Export WITH media (default - required for transcription)
poetry run python whatsapp_chat_autoexport/whatsapp_export.py

# Step 2: Process with --no-media flag
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --no-media
```

**Result**: Final output includes chat transcripts and transcriptions, but NO media files.
**Why this works**: Media files are temporarily extracted and used for transcription (Phase 3), but are not copied to the final output (Phase 4).

### Workflow 3: Minimal Export (No Transcriptions, No Media)
```bash
# Step 1: Export WITHOUT media (faster, smaller files)
poetry run python whatsapp_chat_autoexport/whatsapp_export.py --without-media

# Step 2: Process without transcription
poetry run whatsapp-pipeline /path/to/downloads /path/to/output --no-transcribe --no-media
```
**Result**: Final output includes only chat transcripts (text only).

## Understanding Media Flags

**IMPORTANT**: There are THREE different media flags that serve different purposes:

### Export Flag: `--without-media` (whatsapp-export command)
- **Purpose**: Controls what WhatsApp exports to Google Drive
- **When to use**: Only use if you want minimal exports and don't need transcriptions
- **⚠️ WARNING**: If you use this flag, voice message transcription will NOT work (no audio files to transcribe)
- **Default**: Exports WITH media (recommended for transcription support)

### Unified Command Flag: `--no-output-media` (whatsapp-export with --output) ⭐ NEW
- **Purpose**: Controls what gets copied to the FINAL output folder when using integrated pipeline
- **When to use**: When you want transcriptions but don't want to keep large media files
- **✅ BENEFIT**: Transcriptions still work (media exists during processing, just not in final output)
- **Default**: Copies media to final output
- **Example**: `whatsapp-export --output ~/exports --no-output-media`

### Standalone Pipeline Flag: `--no-media` (whatsapp-pipeline command)
- **Purpose**: Same as `--no-output-media` but for standalone pipeline command
- **When to use**: When processing already-exported files separately
- **Example**: `whatsapp-pipeline /downloads /output --no-media`

**Key Insight**: Always export WITH media (default), then use `--no-output-media` or `--no-media` to exclude media from final output while preserving transcription functionality.

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
# Unified command
poetry run whatsapp-export --output ~/exports --force-transcribe

# Standalone pipeline
poetry run whatsapp-pipeline /downloads /output --force-transcribe
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
     - `verify_whatsapp_is_open()`: **CRITICAL** - Comprehensive verification that WhatsApp is accessible before ANY UI interaction. Checks:
       - Current package is com.whatsapp (not system settings or other apps)
       - Current activity is safe (not lock screen, system UI, or settings)
       - WhatsApp UI elements are actually visible and accessible
       - Phone is not locked
       - Called automatically by `connect()`, `interactive_mode()`, and before each export
     - `check_if_phone_locked()`: Detects if phone is locked by checking activity, package, and UI elements
     - `detect_phone_lock_state()`: User-friendly wrapper that provides clear error messages if phone is locked
     - `find_element()` / `find_elements()`: Locate UI elements by resource ID, text, or accessibility ID
     - `scroll_to_find_chat()`: Bidirectional scrolling with position change detection
     - `navigate_to_main_screen()`: Returns to main chat list
     - Handles chat collection, scrolling through long lists (up to ~200 chats)

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

**CLI Entry Point**: `pipeline_cli/cli.py` provides `whatsapp-pipeline` command with flags:
- `--transcription-provider {whisper,elevenlabs}`: Choose transcription service (default: whisper)
- `--no-media`: Skip copying media to final output (transcriptions still work!)
- `--no-transcribe`: Skip transcription phase entirely
- `--force-transcribe`: Re-transcribe even if transcriptions exist
- `--skip-drive-download`: Process local files only

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
     - WhatsApp UI elements (toolbar, action bar, chat list) are actually visible and accessible
     - Phone is not locked (via multiple lock detection strategies)
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
├── export/
│   ├── cli.py                    # Export CLI entry point
│   ├── whatsapp_driver.py        # WhatsApp UI automation
│   └── chat_exporter.py          # Export workflow
├── transcription/
│   ├── base_transcriber.py       # Abstract transcriber interface
│   ├── whisper_transcriber.py    # OpenAI Whisper implementation
│   ├── elevenlabs_transcriber.py # ElevenLabs Scribe implementation
│   ├── transcriber_factory.py    # Factory for provider selection
│   └── transcription_manager.py  # Batch transcription orchestration
├── output/
│   └── output_builder.py         # Final output structure builder
├── pipeline_cli/
│   └── cli.py                    # Pipeline CLI entry point
├── pipeline.py                   # Main pipeline orchestrator
└── __init__.py

Project root:
├── README.md             # Full documentation
├── QUICKSTART.md         # Quick start guide with important warnings
├── CLAUDE.md             # Developer documentation (this file)
├── pyproject.toml        # Poetry dependencies and scripts
└── poetry.lock           # Locked dependencies
```

## Testing Strategy

This project uses **pytest** for all testing. Tests are organized in the `tests/` directory with separate subdirectories for unit and integration tests.

### Test Organization

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── unit/                          # Unit tests (fast, isolated)
│   ├── test_transcription.py      # Transcription system tests
│   ├── test_transcript_parser.py  # Message parsing tests
│   ├── test_output_builder.py     # Output generation tests
│   └── test_archive_extractor.py  # Archive processing tests
├── integration/                   # Integration tests (slower, end-to-end)
│   └── test_cli.py                # CLI argument parsing tests
└── fixtures/                      # Test data and sample files
    └── sample_export/             # Real WhatsApp export for testing
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

### Testing Export Script (Manual Testing)

For the WhatsApp export automation script (requires device):

1. Use `--limit 5` to limit to 5 chats
2. Enable `--debug` to see detailed navigation steps
3. Use `--skip-appium` if manually managing Appium server
4. Test with both `--with-media` (default) and `--without-media`
5. Verify `--resume` functionality by running twice on same folder
6. Test wireless ADB if making connection-related changes

### Testing Pipeline (Manual Testing)

For the complete pipeline workflow:

1. Test default behavior (full pipeline with media + transcriptions)
2. Test `--no-media` flag (verify transcriptions still created)
3. Test `--no-transcribe` flag (verify media still copied)
4. Test `--no-media --no-transcribe` (minimal output)
5. Verify output structure matches expectations
6. Check that temporary files are cleaned up properly

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
