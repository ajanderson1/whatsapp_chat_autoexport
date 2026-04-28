# WhatsApp Chat AutoExport

Automated WhatsApp chat export from Android devices to Google Drive using Appium-based UI automation.

## What It Does

WhatsApp's end-to-end encryption prevents direct data access. This tool uses screen scraping and UI automation to navigate WhatsApp's interface and trigger exports programmatically.

- **Automatically navigates** through your WhatsApp chats
- **Interactively lists** all available chats for selection
- **Exports chats** directly to Google Drive (with or without media)
- **Transcribes voice messages** using OpenAI Whisper or ElevenLabs Scribe
- **Organizes output** into structured folders with transcripts and media

## Three Modes

=== "TUI (Interactive)"

    ```bash
    poetry run whatsapp
    ```

    Full wizard flow with device connection, chat selection, export, and processing.

=== "Headless"

    ```bash
    poetry run whatsapp --headless --output ~/exports --auto-select
    ```

    Non-interactive with structured logging. Ideal for automation.

=== "Pipeline Only"

    ```bash
    poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output
    ```

    Process already-exported files without device connection.

## Recommended Command

```bash
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --no-output-media
```

Exports all chats with transcriptions but excludes large media files from the final output.

## Prerequisites

- Python 3.13+
- Android device with USB/wireless debugging enabled
- WhatsApp and Google Drive installed on the device
- [Appium](https://appium.io/) (`npm install -g appium`)
- ADB (Android Debug Bridge) in your PATH

## Quick Links

- [Quick Start](getting-started/quickstart.md) - Get running in minutes
- [Docker Guide](getting-started/docker.md) - Run in a container
- [CLI Reference](guide/cli-reference.md) - All flags and options
- [Media & Transcription](guide/media-and-transcription.md) - Understanding media flags
