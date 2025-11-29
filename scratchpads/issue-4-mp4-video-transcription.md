# Issue #4: MP4 Video Messages Fail to Transcribe with ElevenLabs

**Issue Link**: https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/4

## Problem Summary

WhatsApp video messages (VID-*.mp4) fail to transcribe with ElevenLabs. The API rejects video files with:
```
status_code: 400, body: {'detail': {'status': 'invalid_content', 'message': 'File upload is corrupted. Please ensure it is playable audio.'}}
```

## Root Cause Analysis

1. The `AudioConverter` utility (`whatsapp_chat_autoexport/utils/audio_converter.py`) already has the capability to extract audio from video files using FFmpeg's `-vn` flag
2. Both transcribers (`elevenlabs_transcriber.py` and `whisper_transcriber.py`) only apply audio conversion for `.opus` files
3. MP4 is listed as a supported format in `ElevenLabsTranscriber.SUPPORTED_FORMATS`, but the ElevenLabs API rejects WhatsApp video note MP4 files when sent directly

## WhatsApp Video Message Pattern

Files matching: `^VID-\d{8}-WA\d+\.mp4$`
- Example: `VID-20251004-WA0011.mp4`

## Implementation Plan

### Step 1: Add WhatsApp Video Message Detection Utility

Create a new function in the codebase to detect WhatsApp video messages:
- Add `is_whatsapp_video_message(filename: str) -> bool` method
- Use regex pattern: `^VID-\d{8}-WA\d+\.mp4$`

**Location**: Add to both transcribers or create a shared utility

### Step 2: Add MP4 Extraction Method to AudioConverter

Add `extract_audio_from_video(video_file: Path, temp_dir: Path) -> Optional[Path]`:
- Similar to `convert_opus_to_m4a()` but for video files
- Extract audio track to M4A format
- Return path to extracted audio file

**Location**: `whatsapp_chat_autoexport/utils/audio_converter.py`

### Step 3: Modify ElevenLabsTranscriber.transcribe()

After the Opus conversion block (line ~233), add:
```python
# Check if file is a WhatsApp video message and needs audio extraction
if is_whatsapp_video_message(audio_path.name):
    if self.audio_converter and self.audio_converter.is_ffmpeg_available():
        temp_m4a_file = self.audio_converter.extract_audio_from_video(audio_path, audio_path.parent)
        if temp_m4a_file:
            actual_file_to_transcribe = temp_m4a_file
```

**Location**: `whatsapp_chat_autoexport/transcription/elevenlabs_transcriber.py`

### Step 4: Modify WhisperTranscriber.transcribe()

Same changes as ElevenLabsTranscriber for consistency.

**Location**: `whatsapp_chat_autoexport/transcription/whisper_transcriber.py`

### Step 5: Write Tests

Add test cases for:
- `is_whatsapp_video_message()` pattern matching
- `extract_audio_from_video()` with mock/real video files
- Transcriber behavior with WhatsApp video files
- Temp file cleanup after video transcription

**Location**: `tests/unit/test_transcription.py`

### Step 6: Update Documentation

Update CLAUDE.md if needed with new flags/behavior.

## Files to Modify

1. `whatsapp_chat_autoexport/utils/audio_converter.py` - Add `extract_audio_from_video()` method
2. `whatsapp_chat_autoexport/transcription/elevenlabs_transcriber.py` - Add video detection and extraction
3. `whatsapp_chat_autoexport/transcription/whisper_transcriber.py` - Add video detection and extraction
4. `tests/unit/test_transcription.py` - Add new test cases

## Design Decisions

1. **Only transcribe WhatsApp video messages** - Other video types (.avi, .mov, .mkv) will be ignored per the issue requirements
2. **Use existing AudioConverter** - Reuse the FFmpeg infrastructure already in place
3. **Extract to M4A** - Consistent with Opus conversion approach
4. **Shared pattern detection** - Could add to a shared utility, but for simplicity will add a helper method to each transcriber (or use a module-level function in audio_converter.py)
5. **Cleanup temp files** - Use same finally block pattern as Opus conversion

## Testing Strategy

1. Unit tests with mock files
2. Integration test with sample video file (if available in sample_data)
3. Run full test suite to ensure no regressions
