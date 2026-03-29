# CLI Reference

The unified `whatsapp` command supports three modes: TUI, headless, and pipeline-only.

## Usage

```
whatsapp [OPTIONS]
whatsapp --headless --output DIR [OPTIONS]
whatsapp --pipeline-only SOURCE OUTPUT [OPTIONS]
```

## Flags

| Flag | Description |
|------|-------------|
| `--output DIR` | Output directory (required for `--headless`) |
| `--headless` | Run without TUI (structured logging to stderr) |
| `--pipeline-only SRC OUT` | Run pipeline only (no device connection) |
| `--limit N` | Limit number of chats to export |
| `--without-media` | Export without media from WhatsApp |
| `--no-output-media` | Exclude media from final output (transcriptions still work) |
| `--force-transcribe` | Re-transcribe even if transcriptions exist |
| `--no-transcribe` | Skip transcription phase |
| `--wireless-adb [ADDR]` | Use wireless ADB (TUI prompts if no address given) |
| `--debug` | Enable debug output |
| `--resume PATH` | Skip already-exported chats (scans Drive folder) |
| `--delete-from-drive` | Delete exports from Drive after processing |
| `--transcription-provider` | Choose `whisper` (default) or `elevenlabs` |
| `--skip-drive-download` | Process local files without Drive download |
| `--auto-select` | Export all chats (required for `--headless` without `--resume`) |

## Common Workflows

### Full export with transcriptions, no media in output

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --no-output-media
```

### Resume a previous session

```bash
poetry run whatsapp --headless --output ~/exports --resume /path/to/drive/folder
```

### Process local files only

```bash
poetry run whatsapp --pipeline-only /path/to/downloads /path/to/output
```

### Minimal text-only export

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --without-media --no-transcribe
```

## Deprecated Commands

These print a migration notice and exit:

| Old Command | Replacement |
|---|---|
| `whatsapp-export` | `whatsapp --headless --output DIR` |
| `whatsapp-pipeline` | `whatsapp --pipeline-only SOURCE OUTPUT` |
| `whatsapp-process` | `whatsapp --pipeline-only SOURCE OUTPUT` |
| `whatsapp-drive` | `whatsapp --headless --output DIR` |
| `whatsapp-logs` | `whatsapp --debug` |
