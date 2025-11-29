# Quick Start Guide

Get started exporting and processing WhatsApp chats in minutes.

⚠️ **IMPORTANT**: This is a fragile screen scraping process. Monitor as it runs and follow these tips:

* Keep your phone unlocked (the script automatically clears overlays by pressing home button)
* Do not interact with the phone while the script is running
* Set up your API key before running (script validates it early)
* Ensure Google Drive app is installed and configured on your device
* For wireless ADB, ensure device and computer are on the same Wi-Fi network

## Prerequisites

1. **Python 3.13+** installed
2. **Android device** with:
   - USB debugging enabled (Settings → Developer Options → USB debugging)
   - WhatsApp installed
   - Google Drive app installed and configured
3. **Install Appium**:
   ```bash
   npm install -g appium
   ```
4. **Install dependencies**:
   ```bash
   poetry install
   ```

## Recommended Command ⭐

The simplest workflow uses the unified `whatsapp-export` command:

```bash
# Set your transcription API key first
export ELEVENLABS_API_KEY="your-api-key-here"

# Complete workflow: export → download → transcribe → organize
# (Transcriptions included, no media in final output, pre-select chats 300-500)
poetry run whatsapp-export \
  --output ~/whatsapp_exports \
  --transcription-provider elevenlabs \
  --delete-from-drive \
  --no-output-media \
  --wireless-adb 192.168.1.100:5555 \
  --range 300-500
```

### What This Does

1. **Validates** API key early (fails fast if invalid)
2. **Clears overlays** automatically by pressing home button
3. **Exports** chats 300-500 from WhatsApp to Google Drive (with media)
4. **Downloads** exported files from Google Drive
5. **Transcribes** voice messages using ElevenLabs
6. **Organizes** output: transcripts with embedded transcriptions
7. **Cleans up**: Deletes from Google Drive and discards media files

### Flags Explained

| Flag | Purpose |
|------|---------|
| `--output` | Where to save final organized output |
| `--transcription-provider elevenlabs` | Use ElevenLabs for transcription (alternative: `whisper`) |
| `--delete-from-drive` | Auto-delete from Google Drive after processing |
| `--no-output-media` | Don't include media in final output (saves space, keeps transcriptions) |
| `--wireless-adb 192.168.1.100:5555` | Connect via wireless ADB (no USB cable needed) |
| `--range 300-500` | Pre-select chats 300-500 (also becomes default on 30s timeout) |

## First-Time Wireless ADB Setup

If using `--wireless-adb`, connect via USB once to set up:

```bash
# 1. Enable "Wireless debugging" on your Android device
#    (Settings → Developer Options → Wireless debugging)

# 2. Note the IP:PORT shown (e.g., 192.168.1.100:5555)

# 3. On Android 11+, pair first:
adb pair <IP>:<PAIRING_PORT>  # Use pairing code from device

# 4. Connect
adb connect 192.168.1.100:5555

# 5. Verify connection
adb devices

# Now you can run the script with --wireless-adb flag
```

## Alternative: Simple Export Only

If you just want to export chats without processing:

```bash
# Export WITH media (default - required for transcription later)
poetry run whatsapp-export

# Export WITHOUT media (faster, no transcription support)
poetry run whatsapp-export --without-media
```

## During Export

The script will:
1. Connect to your Android device
2. Launch WhatsApp
3. Scroll through and list all chats
4. Prompt you to select which chats to export:
   - Enter chat numbers (comma-separated, e.g., `1,3,5`)
   - Enter `all` to export all chats
   - Enter `q` to quit

## Output Structure

After processing, your output folder will contain:

```
~/whatsapp_exports/
├── Chat Name 1/
│   ├── transcript.txt          # Main chat with transcriptions embedded
│   └── transcript_raw.txt      # Original export (no transcriptions)
├── Chat Name 2/
│   ├── transcript.txt
│   └── transcript_raw.txt
└── ...
```

Voice message transcriptions are embedded in the main transcript like this:
```
[2025-01-15, 10:30:45] John: [Voice message transcription]
This is what was said in the voice message.
```

## Troubleshooting

### Device Not Found
```bash
# Check if device is connected
adb devices

# For wireless ADB, reconnect
adb connect 192.168.1.100:5555
```

### Appium Issues
```bash
# Check if Appium is installed
appium --version

# Start Appium manually in another terminal
appium -a 127.0.0.1 -p 4723

# Then run script with --skip-appium flag
poetry run whatsapp-export --output ~/exports --skip-appium
```

### Export Failures
- Verify Google Drive is logged in on your device
- Check that "My Drive" appears in share options
- Try manually exporting one chat to verify setup
- Use `--debug` flag for detailed output:
  ```bash
  poetry run whatsapp-export --output ~/exports --debug
  ```

## Advanced Options

```bash
# Pre-select specific chat ranges
poetry run whatsapp-export --output ~/exports --range 300-500
poetry run whatsapp-export --output ~/exports --range 1,5,10-20,50

# Limit to 5 chats (useful for testing)
poetry run whatsapp-export --output ~/exports --limit 5

# Force re-transcribe everything (overwrite existing)
poetry run whatsapp-export --output ~/exports --force-transcribe

# Skip transcription (faster, text only)
poetry run whatsapp-export --output ~/exports --no-transcribe

# Keep media files in final output
poetry run whatsapp-export --output ~/exports
# (omit --no-output-media flag)

# Process already-downloaded files (skip export and download)
poetry run whatsapp-pipeline \
  --skip-download \
  --source ~/Downloads \
  --output ~/exports
```

## API Keys

For transcription to work, set the appropriate API key:

```bash
# For Whisper (default)
export OPENAI_API_KEY="your-openai-key"

# For ElevenLabs
export ELEVENLABS_API_KEY="your-elevenlabs-key"
```

Add to your `~/.bashrc` or `~/.zshrc` to make permanent.

**Note**: The script validates your API key early (before any work begins). If the key is missing or invalid, you'll get a clear error message immediately instead of discovering issues later in the process.

---

**For more details**, see the full [README.md](README.md).
