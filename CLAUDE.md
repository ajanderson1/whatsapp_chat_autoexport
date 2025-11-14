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

### Process Exported Files
```bash
# Process downloaded exports
poetry run python whatsapp_chat_autoexport/whatsapp_process.py /path/to/downloads

# With debug output
poetry run python whatsapp_chat_autoexport/whatsapp_process.py --debug /path/to/downloads
```

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
├── whatsapp_export.py    # Export automation (2225+ lines)
├── whatsapp_process.py   # Post-export processing
└── __init__.py

Project root:
├── README.md             # Full documentation
├── QUICKSTART.md         # Quick start guide with important warnings
├── pyproject.toml        # Poetry dependencies and scripts
└── poetry.lock           # Locked dependencies
```

## Testing Strategy

When testing changes to the export script:
1. Use `--limit 5` to limit to 5 chats
2. Enable `--debug` to see detailed navigation steps
3. Use `--skip-appium` if manually managing Appium server
4. Test with both `--with-media` and `--without-media`
5. Verify `--resume` functionality by running twice on same folder
6. Test wireless ADB if making connection-related changes
