# WhatsApp Chat Auto Export - Docker Guide

Run the WhatsApp export automation in a Docker container without installing Python, Node.js, Appium, or ADB on your host machine.

## Quick Start

### 1. Build the Image
```bash
docker build -t whatsapp-export .
```

### 2. Connect Your Android Device

**USB Connection (Recommended):**
- Enable USB debugging on your Android device
- Connect via USB cable
- Unlock your phone

**Wireless ADB:**
- Enable wireless debugging on your device (Android 11+)
- Get your device IP: Settings → About phone → Status → IP address
- Use `--wireless-adb <device-ip>:5555` flag (container connects automatically)

### 3. Run the Export

**Basic Export (USB):**
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output
```

**Recommended: Transcriptions without media (USB):**
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --no-output-media
```

**Test with 5 chats (USB):**
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --limit 5
```

**Wireless ADB:**
```bash
# Container establishes the connection automatically
docker run --rm --network=host \
  -v ./output:/output \
  whatsapp-export --output /output --wireless-adb 192.168.1.100:5555

# Note: No need to run 'adb connect' on the host first
# The container's ADB server will connect to the device directly
```

## Using Docker Compose

Docker Compose makes it easier to manage the container configuration.

### USB Connection
```bash
# Edit docker-compose.yml if needed, then run:
docker-compose --profile usb run --rm whatsapp-export-usb --output /output

# With custom options:
docker-compose --profile usb run --rm whatsapp-export-usb --output /output --limit 5 --no-output-media
```

### Wireless Connection
```bash
# Edit docker-compose.yml and set DEVICE_IP to your device IP
# Then run:
docker-compose --profile wireless run --rm whatsapp-export-wireless
```

## Configuration

### API Keys for Transcription

**API keys are optional at build time but required at runtime for transcription.**

The container will validate API keys if they're set, or skip validation and warn you if they're not. You can pass API keys at runtime using the `-e` flag.

#### Using OpenAI Whisper (Default)

```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY=sk-your-key-here \
  whatsapp-export --output /output
```

#### Using ElevenLabs Scribe

```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e ELEVENLABS_API_KEY=your-elevenlabs-key \
  whatsapp-export --output /output --transcription-provider elevenlabs
```

#### Using .env File with Docker Compose

Create a `.env` file in your project root:
```env
# .env file
OPENAI_API_KEY=sk-your-key-here
# Or use ElevenLabs:
# ELEVENLABS_API_KEY=your-elevenlabs-key
```

Then run:
```bash
# Docker Compose automatically loads .env file
docker-compose --profile usb run --rm whatsapp-export-usb --output /output
```

#### Skip Transcription

If you don't want transcription at all:
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --no-transcribe
```

### Available Options

All command-line options work with Docker:

```bash
--output PATH              # Output directory (required)
--limit N                  # Limit number of chats
--no-output-media          # Transcriptions only (recommended)
--no-transcribe            # Skip transcription
--force-transcribe         # Re-transcribe all files
--delete-from-drive        # Delete from Drive after download
--without-media            # Export without media (no transcription support)
--debug                    # Enable debug output
--wireless-adb IP:PORT     # Connect via wireless ADB
```

## Volume Mounts

- `-v ./output:/output` - **Required**: Where processed files will be saved
- `-v ./downloads:/downloads` - Optional: Intermediate download directory
- `-v /dev/bus/usb:/dev/bus/usb` - **Required for USB**: Device access

Use absolute paths or `./` relative paths for volume mounts.

## Troubleshooting

### Check Device Connection
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  whatsapp-export adb devices
```

### View Help
```bash
docker run --rm whatsapp-export --help
```

### Debug Mode
```bash
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  whatsapp-export --output /output --debug
```

### Common Issues

**"No Android device connected"**
- Ensure phone is unlocked
- Check USB cable is data-capable (not charge-only)
- Verify USB debugging is enabled
- For USB: Make sure `--privileged` and `/dev/bus/usb` mount are used
- For wireless: Make sure `--network=host` is used

**Permission denied on output directory**
- Make sure the output directory exists: `mkdir -p ./output`
- Check directory permissions: `chmod 755 ./output`

**Appium server failed to start**
- This is rare; usually means port conflict
- Try building image again: `docker build --no-cache -t whatsapp-export .`

**"API key validation failed" or "API key not found"**
- If you're building the image: API keys are optional at build time, you can ignore this warning
- If you're running the export WITH transcription: Pass the API key via `-e OPENAI_API_KEY=your-key`
- If you don't want transcription: Use `--no-transcribe` flag
- If you want transcriptions but no media in output: Use `--no-output-media` (still requires API key)

## How It Works

The container:
1. Starts Appium server automatically
2. Verifies ADB device connection
3. Runs the WhatsApp export workflow
4. Downloads from Google Drive (if needed)
5. Transcribes audio/video files (if enabled)
6. Organizes output into final structure
7. Cleans up temporary files
8. Stops automatically

Everything is self-contained and cleaned up after execution.

## Performance

**Build time**: ~5-10 minutes (first time)
**Image size**: ~1.5 GB (includes Python, Node.js, Android tools)
**Export time**: Same as native execution

## Security Notes

- `--privileged` flag is required for USB device access
- The container does NOT have persistent storage (everything is cleaned up)
- API keys are only used during execution (not stored in image)
- No data is sent anywhere except to Google Drive (export) and transcription APIs (if enabled)

## Next Steps

- See `CLAUDE.md` for full developer documentation
- See `README.md` for project overview
- See `QUICKSTART.md` for native installation guide
