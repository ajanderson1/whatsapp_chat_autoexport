# Quick Start Guide

This guide will help you get started with exporting WhatsApp chats to Google Drive and processing the exported files.

⚠️ **IMPORTANT**: This is a fragile screen scraping process which may be vulnerable to changes in the WhatsApp UI. As such, it's recommended to monitor as it runs. Follow these tips to avoid unintended behaviors:

* Connect an Android device with WhatsApp installed and Google Drive app installed and configured
* To avoid `WhatsApp Chat with ... (1)` appearing, ensure that you remove previous exports from Google Drive or set the `--resume <google home dir> flag.
* Ensure your phone is unlocked and on the home screen
* Do not interact with the phone while the script is running
* Answer all interactive prompts in a timely manner, otherwise the session will time out

## Prerequisites

Before starting, make sure you have:

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

## Installation

Install dependencies using Poetry:

```bash
poetry install
```

## Step 1: Export WhatsApp Chats

Run the export script:

```bash
poetry run python whatsapp_export.py
```

The script will:
1. Start Appium server (unless you use `--skip-appium`)
2. Connect to your Android device
3. Launch WhatsApp
4. Navigate to the main chats screen
5. Scroll through and collect all available chats
6. Display them in a numbered list

### Selecting Chats

When prompted, you can:
- Enter chat numbers (comma-separated, e.g., `1,3,5`)
- Enter `all` to export all chats
- Enter `q`, `quit`, or `exit` to quit

### Export Options

The script supports several options:

```bash
# Enable debug mode (verbose output)
poetry run python whatsapp_export.py --debug

# Skip starting Appium (assume it's already running)
poetry run python whatsapp_export.py --skip-appium

# Limit to 10 chats (default limit)
poetry run python whatsapp_export.py --limit

# Limit to specific number of chats
poetry run python whatsapp_export.py --limit 5

# Export with media (default)
poetry run python whatsapp_export.py --with-media

# Export without media
poetry run python whatsapp_export.py --without-media

# Show chats in original WhatsApp order
poetry run python whatsapp_export.py --sort-order original

# Show chats alphabetically (default)
poetry run python whatsapp_export.py --sort-order alphabetical

# Connect via wireless ADB (device must be on same network)
poetry run python whatsapp_export.py --wireless-adb 192.168.1.100:5555
```

### What Happens During Export

For each selected chat, the script will:
1. Navigate into the chat
2. Open the three-dot menu
3. Select "More" → "Export chat"
4. Choose media option (with/without media)
5. Select "My Drive" (Google Drive)
6. Return to main screen for the next chat

The script initiates the export to Google Drive. The actual upload is handled by Google Drive and may take time depending on chat size, media content, and network speed.

## Step 2: Process Exported Files

After exporting chats to Google Drive, download them to your computer. Then process them with:

```bash
poetry run python whatsapp_process.py /path/to/downloaded/chats
```

For example:
```bash
poetry run python whatsapp_process.py ~/Downloads/WhatsApp
```

The processor will:
1. Find all WhatsApp chat export files (matching "WhatsApp Chat with ..." pattern)
2. Move them to a "WhatsApp Chats Processed" folder
3. Add .zip extension if needed
4. Extract the zip files
5. Organize content into:
   - `transcripts/` - All chat transcript files (.txt)
   - `media/[chat name]/` - Media files organized by chat
6. Optionally clean up zip files and extracted folders (prompts for confirmation)

### Example Output Structure

```
WhatsApp Chats Processed/
├── transcripts/
│   ├── WhatsApp Chat with Alice.txt
│   ├── WhatsApp Chat with Bob.txt
│   └── ...
└── media/
    ├── WhatsApp Chat with Alice/
    │   ├── image1.jpg
    │   ├── video1.mp4
    │   └── ...
    └── WhatsApp Chat with Bob/
        └── ...
```

## Wireless ADB Setup

To use wireless ADB instead of USB:

1. **First-time setup (requires USB connection):**
   - Connect your device via USB
   - Enable "Wireless debugging" in Developer Options on your Android device
   - Note the IP address and port shown (e.g., `192.168.1.100:5555`)
   - On Android 11+, you may need to pair first:
     ```bash
     # Get pairing code from your device's wireless debugging settings
     adb pair <IP>:<PAIRING_PORT>
     # Then connect
     adb connect <IP>:<PORT>
     ```

2. **Using wireless ADB:**
   ```bash
   poetry run python whatsapp_export.py --wireless-adb 192.168.1.100:5555
   ```

3. **Important notes:**
   - Your device and computer must be on the same Wi-Fi network
   - You can disconnect USB after the initial pairing
   - The IP address may change if your device reconnects to Wi-Fi

## Troubleshooting

### Device Not Found

If you see "No device found":
```bash
# Check if device is connected
adb devices

# If device appears as "unauthorized", check your phone for USB debugging authorization prompt

# For wireless ADB, verify connection:
adb connect <IP>:<PORT>
adb devices
```

### Appium Issues

If Appium fails to start:
```bash
# Check if Appium is installed
appium --version

# Try starting Appium manually
appium -a 127.0.0.1 -p 4723

# Then run script with --skip-appium flag
poetry run python whatsapp_export.py --skip-appium
```

### Export Failures

If exports fail:
- Verify Google Drive is installed and logged in on your device
- Check that "My Drive" appears in your share options
- Try manually exporting one chat to verify Google Drive setup
- Use `--debug` flag to see detailed error information

## Next Steps

For more detailed information, see the main [README.md](README.md).

