# Troubleshooting

## Device Connection

If you see "No device found":

```bash
# Check if device is connected
adb devices

# If "unauthorized", check your phone for the USB debugging prompt

# For wireless ADB
adb connect <IP>:<PORT>
adb devices
```

## Appium

If Appium fails to start:

```bash
# Verify installation
appium --version

# Start manually
appium -a 127.0.0.1 -p 4723

# Then run with --skip-appium
poetry run whatsapp --skip-appium
```

## WhatsApp Navigation

If the script can't navigate WhatsApp:

- Ensure WhatsApp is installed and up to date
- Close WhatsApp completely before running
- Use `--debug` for detailed navigation info
- The script verifies WhatsApp is open at multiple checkpoints -- if verification fails, it exits immediately

## Export Failures

If exports fail:

- Verify Google Drive is installed and logged in
- Check that "My Drive" appears in your share options
- Try manually exporting one chat to verify Drive setup
- Use `--debug` for detailed error info

## Known Limitations

- **Community chats** are automatically skipped (WhatsApp doesn't support export)
- **Chat position changes** during search: if a chat moves beyond the 240-scroll search range, it will be skipped
- **Google Drive setup** must be complete -- the script assumes "My Drive" or "Drive" is available
- **Duplicate exports**: use `--resume` to skip already-exported chats, or remove previous exports from Drive first
