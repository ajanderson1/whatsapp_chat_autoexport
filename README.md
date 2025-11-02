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
- **Interactively lists** all available chats for selection
- **Exports chats** directly to Google Drive with or without media
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
2. **Android device** connected via USB with:
   - USB debugging enabled
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

## ⚠️ Important Notes

### Before Running

1. **Google Drive must be set up** on your device:
   - Ensure Google Drive app is installed
   - You must be logged into your Google account
   - "My Drive" option must be available in the share dialog

2. **Do not interfere with the phone** while the script is running:
   - The script is busy screen scraping and automating interactions
   - Any manual interference may cause the script to fail
   - Keep your phone unlocked and connected via USB

3. **Allow time for exports**:
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

## 🐛 Troubleshooting

### Device Connection Issues

If you see "No device found":
```bash
# Check if device is connected
adb devices

# If device appears as "unauthorized", check your phone for USB debugging authorization prompt
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

