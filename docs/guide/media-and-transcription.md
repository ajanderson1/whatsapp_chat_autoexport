# Media & Transcription

Understanding the three media flags and transcription behavior.

## Media Flags

There are **three** different media flags that serve different purposes:

### `--without-media` (Export Flag)

Controls what WhatsApp exports to Google Drive.

!!! warning
    If you use this flag, voice message transcription will **not** work -- there are no audio files to transcribe.

### `--no-output-media` (Output Flag)

Controls what gets copied to the **final output** folder. Transcriptions still work because media exists during processing, just not in the final output.

This is the **recommended** approach: export with media (default), then exclude media from output.

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --no-output-media
```

### Key Insight

Always export **with** media (the default), then use `--no-output-media` to exclude media from the final output while preserving transcription functionality.

## Transcription Behavior

### Skip Existing (Default)

The pipeline skips re-transcribing files that already have transcriptions. This saves time and API costs.

Before transcribing, it checks if `[filename]_transcription.txt` exists. If found and non-empty, the file is skipped.

```
Transcribing 10 file(s) for: Chat Name

  Skipping (exists): Chat Name/PTT-001.opus
  Skipping (exists): Chat Name/VID-002.mp4
  Transcribing: PTT-003.opus

======================================================================
Transcription Summary
======================================================================
Total files: 10
Successful: 2 (newly transcribed)
Skipped (existing): 7
======================================================================
```

### Force Re-Transcription

Use `--force-transcribe` to re-transcribe all files, even if transcriptions exist:

```bash
poetry run whatsapp --headless --output ~/exports --auto-select --force-transcribe
```

Use when:

- Previous transcriptions were poor quality
- Language detection was incorrect
- Testing transcription improvements

### Providers

| Provider | Model | API Key | Notes |
|----------|-------|---------|-------|
| **Whisper** (default) | OpenAI Whisper API | `OPENAI_API_KEY` | $0.006/min |
| **ElevenLabs** | Scribe v1 | `ELEVENLABS_API_KEY` | Up to 32 speakers, diarization, 99 languages |

```bash
# Whisper (default)
export OPENAI_API_KEY="your-key"
poetry run whatsapp --headless --output ~/exports --auto-select

# ElevenLabs
export ELEVENLABS_API_KEY="your-key"
poetry run whatsapp --headless --output ~/exports --auto-select --transcription-provider elevenlabs
```
