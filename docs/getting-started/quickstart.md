# Quick Start

Get started exporting and processing WhatsApp chats in minutes.

!!! warning "Fragile Process"
    This is a screen scraping process vulnerable to WhatsApp UI changes. Monitor the script as it runs.

## Prerequisites

1. **Python 3.13+** installed
2. **Android device** with:
    - USB debugging enabled (Settings > Developer Options > USB debugging)
    - WhatsApp installed
    - Google Drive app installed and configured
3. **Appium** installed:
    ```bash
    npm install -g appium
    ```

## Install

```bash
poetry install
```

## Run

### Interactive TUI (Recommended for First Use)

```bash
poetry run whatsapp
```

The TUI guides you through device connection, chat selection, export, and processing.

### Headless Mode

```bash
# Export all chats with transcriptions, no media in output
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --no-output-media

# Limit to 5 chats for testing
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --limit 5
```

### Pipeline Only (Process Existing Files)

```bash
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output
```

## Before You Run

!!! tip "Phone Setup"
    - Keep your phone **unlocked** throughout execution
    - **Do not interact** with the phone while the script runs
    - Ensure Google Drive is installed and logged in on the device

!!! info "API Keys (for Transcription)"
    ```bash
    # OpenAI Whisper (default)
    export OPENAI_API_KEY="your-key"

    # Or ElevenLabs Scribe
    export ELEVENLABS_API_KEY="your-key"
    ```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Partial failure (some chats failed) |
| `2` | Fatal error |
