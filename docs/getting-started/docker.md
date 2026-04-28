# Docker

Run the entire workflow in a Docker container without installing Python, Node.js, Appium, or ADB on your host machine.

## Build

```bash
docker build -t whatsapp-export .
```

## USB Connection (Recommended)

```bash
# Basic headless export
docker run --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  whatsapp-export --output /output --auto-select

# With transcriptions, no media in output (recommended)
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

## Interactive TUI in Docker

Override the entrypoint with `-it`:

```bash
docker run -it --rm --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -v ./output:/output \
  -e OPENAI_API_KEY='your-key-here' \
  --entrypoint whatsapp \
  whatsapp-export
```

## Wireless ADB

```bash
# Headless with wireless ADB
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

## Environment Variables

| Variable | Provider | Notes |
|----------|----------|-------|
| `OPENAI_API_KEY` | OpenAI Whisper (default) | $0.006/min |
| `ELEVENLABS_API_KEY` | ElevenLabs Scribe | 99 languages, diarization |

## Important Notes

| Requirement | Flag |
|-------------|------|
| USB connection | `--privileged` and `-v /dev/bus/usb:/dev/bus/usb` |
| Wireless connection | `--network=host` |
| Interactive TUI | `-it` and `--entrypoint whatsapp` |

- Phone must be unlocked and remain unlocked throughout
- Container auto-cleans with `--rm` flag
- Default entrypoint is `whatsapp --headless`
