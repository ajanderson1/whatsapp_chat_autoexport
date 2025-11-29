# WhatsApp Chat Auto-Export

An automated Python script that exports WhatsApp chats from your Android device to Google Drive using Appium automation. This tool provides an interactive interface to select and export multiple chats efficiently.

# Concept

WhatsApp often makes up the majority of particular correspondences. As such it provides a useful data set when paired with a LLM for scrutinizing correspondence styles, social dynamics, notable traits, memorable events, patterns, etc.


# Personal Note

Automating this process is a hack, but it's the only practical means given the encryption methodology WhatsApp uses.  As such, it's an ugly screenscraping process, but ultimately a time saver for extensive WhatsApp use. 

```
WhatsApp deliberately makes direct downloading or programmatic access to chat data extremely difficult, largely due to its end-to-end encryption (E2EE) model and internal data structure. Every message is encrypted on the sender’s device before transmission using a unique session key derived from the Signal Protocol, which combines Curve25519, AES-256, and HMAC-SHA256 algorithms. These keys are stored only on the communicating devices — not on WhatsApp’s servers — which means even WhatsApp itself cannot decrypt the contents. The message database on the phone (msgstore.db) is further encrypted locally using an AES key stored in the app’s sandbox, often bound to the device’s hardware keystore and user account, making extraction without root access nearly impossible. Backup exports (like to Google Drive or iCloud) are separately encrypted using yet another layer of keys linked to the user’s WhatsApp account credentials and device-specific identifiers. This multi-tiered cryptographic chain — server trust tokens, rotating session keys, local database encryption, and sandbox isolation — ensures that even if one layer is compromised, the chat content remains unreadable without the exact cryptographic keys held within the WhatsApp runtime environment on the legitimate user’s device. Consequently, automation or scraping tools can only access chats through simulated UI interactions, not direct data extraction.
```


## 🎯 Purpose & What We've Achieved

This project automates the tedious process of manually exporting WhatsApp chats to Google Drive. Instead of going through each chat individually in WhatsApp's interface, this script:

- **Automatically navigates** through your WhatsApp chats
- **Clears overlays automatically** by pressing home button before starting (prevents failures from settings/dialogs being open)
- **Interactively lists** all available chats for selection
- **Pre-select chat ranges** via `--range` flag (e.g., `--range 300-500`)
- **Exports chats** directly to Google Drive with or without media
- **Validates API keys early** before starting work (fail-fast approach)
- **Handles navigation** seamlessly, including scrolling through long chat lists
- **Provides detailed logging** with colored output and debug modes
- **Skips incompatible chats** (like community chats) automatically

The script uses **Appium** and **UiAutomator2** to control your Android device, performing screen scraping and UI automation to navigate WhatsApp's interface and trigger exports programmatically.

## Edge cases:

* **Chat position changes during search**: If a chat moves position (due to new messages) while the script is searching for it, the script will scroll up to 120 times in each direction (240 total scrolls maximum). This allows searching through approximately 200 chats. If a chat moves beyond this search range during the search process, it may be missed and the chat will be skipped.

* Not currently handling communities - It is probably possible to go into each chat in a community and export. 

# TODO
Handle *'Advanced Chat Privacy has been turned on.'*.  This came up in one of the scrapes and caused the script to stall. 



## 📋 Prerequisites

Before using this script, ensure you have:

1. **Python 3.13+** installed
2. **Android device** connected via USB or wireless ADB with:
   - USB debugging enabled (or wireless debugging for wireless ADB)
   - WhatsApp installed
   - Google Drive app installed and configured
3. **Appium** installed globally:
   ```bash
   npm install -g appium
   ```
4. **ADB (Android Debug Bridge)** installed and in your PATH
5. **Android SDK** installed (typically at `~/Library/Android/sdk` on macOS)

### Installing Dependencies

Using Poetry (recommended):
```bash
poetry install
```

Or using pip:
```bash
pip install appium-python-client colorama
```


## 🚀 Quick Start

For a quick start guide, see [QUICKSTART.md](quickstart.md).

## 🔧 How It Works

The script consists of several key components:

- **AppiumManager**: Manages the Appium server lifecycle
- **WhatsAppDriver**: Handles WhatsApp connection and navigation using Appium
- **ChatExporter**: Performs the actual export operations
- **Logger**: Provides colored, categorized logging output

The script uses UI automation to:
- Find UI elements by resource IDs, text content, and accessibility IDs
- Navigate through WhatsApp's interface
- Handle scrolling through long chat lists
- Detect and skip incompatible chats (community chats)
- Trigger Google Drive exports

## 🔄 Complete Workflow: Export → Process → Output

This project provides a complete end-to-end workflow for WhatsApp chat processing:

### Recommended: Unified Command ⭐

The simplest approach is the unified `whatsapp-export` command that handles everything:

```bash
# Complete workflow: export → download → transcribe → organize
# Transcriptions included, no media in final output (RECOMMENDED)
poetry run whatsapp-export --output ~/whatsapp_exports --no-output-media

# Same with ElevenLabs + wireless ADB + auto-delete + pre-select chats 300-500
poetry run whatsapp-export \
  --output ~/whatsapp_exports \
  --transcription-provider elevenlabs \
  --delete-from-drive \
  --no-output-media \
  --wireless-adb 192.168.1.100:5555 \
  --range 300-500

# Full archive with media files included
poetry run whatsapp-export --output ~/whatsapp_exports

# Pre-select specific chats (ranges or comma-separated)
poetry run whatsapp-export --output ~/whatsapp_exports --range 1,5,10-20,50

# Faster: skip transcription entirely
poetry run whatsapp-export --output ~/whatsapp_exports --no-transcribe

# Force re-transcribe all audio/video (overwrites existing)
poetry run whatsapp-export --output ~/whatsapp_exports --force-transcribe
```

### Alternative: Manual Export + Standalone Pipeline

If you prefer to export and process separately:

**Step 1: Export from WhatsApp**
```bash
# Export WITH media (required for voice message transcription)
poetry run whatsapp-export

# Export WITHOUT media (faster, but no transcription support)
poetry run whatsapp-export --without-media
```

**Step 2: Process Exported Files**
```bash
# Complete pipeline: download → extract → transcribe → organize
poetry run whatsapp-pipeline --output ~/whatsapp_exports

# Transcriptions only (no media in final output)
poetry run whatsapp-pipeline --output ~/whatsapp_exports --no-media

# Process local files (skip Google Drive download)
poetry run whatsapp-pipeline --skip-download --source ~/Downloads --output ~/whatsapp_exports
```

### Common Use Cases

**Use Case 1: Transcriptions Without Media ⭐ RECOMMENDED**
```bash
# Single unified command (simplest)
poetry run whatsapp-export --output ~/whatsapp_exports --no-output-media

# With ElevenLabs, wireless ADB, and auto-delete from Drive
poetry run whatsapp-export \
  --output ~/whatsapp_exports \
  --transcription-provider elevenlabs \
  --delete-from-drive \
  --no-output-media \
  --wireless-adb 192.168.1.100:5555
```
**Result**: Chat transcripts and voice message transcriptions WITHOUT keeping large media files.
**Why this works**: Media files are temporarily downloaded and used for transcription, but are not copied to the final output folder.

**Use Case 2: Full Archive (Media + Transcriptions)**
```bash
# Single unified command
poetry run whatsapp-export --output ~/whatsapp_exports

# OR use separate commands (more control)
poetry run whatsapp-export  # Export only
poetry run whatsapp-pipeline --output ~/whatsapp_exports  # Process later
```
**Result**: Complete archive with chat transcripts, all media files, and voice message transcriptions.

**Use Case 3: Text-Only Archive**
```bash
# Export without media, skip transcription
poetry run whatsapp-export --output ~/whatsapp_exports --without-media --no-transcribe
```
**Result**: Chat transcripts only, no media, no transcriptions.

### Understanding the Media Flags

**Two main flags control media at different stages:**

| Flag | Command | Stage | Purpose |
|------|---------|-------|---------|
| `--without-media` | whatsapp-export | Export | Controls what WhatsApp exports to Drive |
| `--no-output-media` ⭐ | whatsapp-export | Processing | Controls what gets copied to final output |
| `--no-media` | whatsapp-pipeline | Processing | Controls what gets copied to final output (standalone) |

**Key Insights**:
- **Always export WITH media (default)** for voice message transcription support
- Use `--no-output-media` to get transcriptions WITHOUT keeping large media files
- The `--no-output-media` flag is the recommended approach for most users
- Media files are temporarily downloaded for transcription, then optionally discarded

### Voice Message Transcription

**Automatic Skip (Default)**:
By default, the pipeline skips re-transcribing files that already have transcriptions, saving time and API costs.

When you run the pipeline, you'll see clear feedback:
```
⏭️  Skipping (exists): Chat Name/PTT-001.opus
🎤 Transcribing: PTT-003.opus
```

Summary shows which files were skipped:
```
Transcription Summary
======================================================================
Total files: 10
Successful: 2 (newly transcribed)
Skipped (existing): 7

Skipped files (existing transcriptions found):
  - Chat Name/PTT-001.opus
  - Chat Name/VID-002.mp4
  ... and 5 more
```

**Force Re-Transcription**:
Use `--force-transcribe` to re-transcribe everything:
```bash
poetry run whatsapp-export --output ~/exports --force-transcribe
```

Use this when:
- Previous transcriptions were poor quality
- You want to try different language settings
- You're testing transcription improvements

**Transcription Providers**:

The pipeline supports multiple transcription service providers:

| Provider | Model | API Key | Notes |
|----------|-------|---------|-------|
| **Whisper** (default) | OpenAI Whisper API | `OPENAI_API_KEY` | $0.006 per minute, widely used, good quality |
| **ElevenLabs** | Scribe v1 | `ELEVENLABS_API_KEY` | Supports up to 32 speakers, diarization, 99 languages |

**Setting up API keys**:
```bash
# For Whisper (default)
export OPENAI_API_KEY="your-openai-key"

# For ElevenLabs
export ELEVENLABS_API_KEY="your-elevenlabs-key"
```

**Using a specific provider**:
```bash
# Use Whisper (default)
poetry run whatsapp-export --output ~/exports

# Use ElevenLabs
poetry run whatsapp-export --output ~/exports --transcription-provider elevenlabs

# Standalone pipeline with ElevenLabs
poetry run whatsapp-pipeline --output ~/exports --transcription-provider elevenlabs
```

## ⚠️ Important Notes

### Before Running

1. **Set up API key for transcription** (if using transcription):
   - For Whisper: `export OPENAI_API_KEY="your-key"`
   - For ElevenLabs: `export ELEVENLABS_API_KEY="your-key"`
   - The script will validate your API key before starting work (fail-fast)

2. **Google Drive must be set up** on your device:
   - Ensure Google Drive app is installed
   - You must be logged into your Google account
   - "My Drive" option must be available in the share dialog

3. **Phone setup**:
   - Keep your phone unlocked during the entire process
   - The script automatically clears overlays (presses home button before starting)
   - No need to close settings or other apps manually - this is handled automatically

4. **Do not interfere with the phone** while the script is running:
   - The script is busy screen scraping and automating interactions
   - Any manual interference may cause the script to fail
   - Keep your phone connected via USB or wireless ADB

5. **Allow time for exports**:
   - Large chats with media can take significant time to upload
   - The script initiates the export, but Google Drive handles the actual upload
   - You may need to wait for uploads to complete after the script finishes

### Known Limitations

- **Not tested for**:
  - What happens if there are no chats
  - What happens if "My Drive" option is not available
  - Very large numbers of chats (thousands)

- **Community chats**: Automatically skipped (they don't support export)

- **Export initiation only**: The script initiates the export to Google Drive. The actual upload is handled by Google Drive and may take time depending on:
  - Chat size
  - Media content
  - Network speed

## 📡 Wireless ADB Support

This tool supports connecting to your Android device via wireless ADB, allowing you to run the script without a USB cable.

### Setting Up Wireless ADB

1. **First-time pairing (requires USB connection):**
   - Connect your device via USB
   - On your Android device, go to **Settings → Developer Options → Wireless debugging**
   - Enable "Wireless debugging"
   - Note the IP address and port shown (e.g., `192.168.1.100:5555`)
   - On Android 11+, you may need to pair first:
     ```bash
     # Get pairing code from your device's wireless debugging settings
     adb pair <IP>:<PAIRING_PORT>
     # Then connect
     adb connect <IP>:<PORT>
     ```

2. **Using wireless ADB with the script:**
   ```bash
   poetry run python whatsapp_export.py --wireless-adb 192.168.1.100:5555
   ```

3. **Important notes:**
   - Your device and computer must be on the same Wi-Fi network
   - You can disconnect USB after the initial pairing
   - The IP address may change if your device reconnects to Wi-Fi
   - For best results, keep your device on the same network throughout the export process

## 🐛 Troubleshooting

### Device Connection Issues

If you see "No device found":
```bash
# Check if device is connected
adb devices

# If device appears as "unauthorized", check your phone for USB debugging authorization prompt

# For wireless ADB, verify connection:
adb connect <IP>:<PORT>
adb devices
```

### Appium Connection Issues

If Appium fails to start:
```bash
# Check if Appium is installed
appium --version

# Try starting Appium manually
appium -a 127.0.0.1 -p 4723

# Then run script with --skip-appium flag
python whatsapp_export.py --skip-appium
```

### WhatsApp Navigation Issues

If the script can't navigate WhatsApp:
- Ensure WhatsApp is installed and up to date
- Try closing WhatsApp completely before running the script
- Use `--debug` flag to see detailed navigation information

### Export Failures

If exports fail:
- Verify Google Drive is installed and logged in
- Check that "My Drive" appears in your share options
- Try manually exporting one chat to verify Google Drive setup
- Use `--debug` flag to see detailed error information

## 📝 Example Output

```
======================================================================
🚀 WhatsApp Chat Auto-Export
======================================================================
🔍 STEP 1: Setting up Android environment...
✅ Device connected
✅ WhatsApp is open!
📋 INTERACTIVE MODE
======================================================================
Loading all chats...
✅ Finished scrolling! Found 47 total chats

Found 47 chats:
----------------------------------------------------------------------
  1. Alice
  2. Bob
  3. Charlie
  ...

Select chats to export:
  - Chats are listed alphabetically
  - Enter chat numbers (comma-separated, e.g., 1,3,5)
  - Enter 'all' to export all chats
  - Enter 'q', 'quit', or 'exit' to quit
======================================================================

Your selection: 1,2,3

📤 Exporting 3 chat(s) with media...

======================================================================
📤 EXPORTING CHAT: 'Alice' (with media)
======================================================================
🔍 STEP 1: Opening menu...
✅ Menu opened
🔍 STEP 2: Looking for 'More' option...
✅ 'More' clicked
...
✅ SUCCESS: Export initiated for 'Alice'

======================================================================
✅ EXPORT COMPLETE
======================================================================

📊 FINAL STATISTICS:
   Total chats processed: 3
   Successfully exported: 3
   Skipped: 0
```

## 📄 License

This project is provided as-is for personal use.

## 🤝 Contributing

Feel free to submit issues or pull requests for improvements!

---

**Remember**: Keep your phone connected and don't interfere with it while the script is running. The script handles all navigation automatically!

