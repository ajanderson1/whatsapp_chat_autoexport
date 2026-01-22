# PRP: Fix Missing _has_audio_stream Method

## Issue Reference
GitHub Issue #7: Video transcription fails: missing _has_audio_stream method

## Problem Statement
Video transcription fails with `AttributeError: 'AudioConverter' object has no attribute '_has_audio_stream'` when processing WhatsApp video messages (VID-*.mp4). The method `_has_audio_stream` is called in `audio_converter.py` line 237 but was never implemented.

## Root Cause
Commit `99b9839` (Dec 24, 2025) added a call to `self._has_audio_stream(video_file)` at line 237 of `audio_converter.py`, but the method implementation was omitted.

## Solution

### Implementation Plan

1. **Add `_has_audio_stream` method to `AudioConverter` class**
   - Use `ffprobe` to detect if video file has an audio stream
   - Return `True` if audio stream exists, `False` otherwise
   - Handle edge cases: missing ffprobe, invalid file, timeout

### Code Changes

**File: `whatsapp_chat_autoexport/utils/audio_converter.py`**

Add the following method to the `AudioConverter` class (before `extract_audio_from_video` method):

```python
def _has_audio_stream(self, video_file: Path) -> bool:
    """
    Check if a video file contains an audio stream.

    Uses ffprobe to analyze the video file and detect audio streams.

    Args:
        video_file: Path to video file

    Returns:
        True if the video has an audio stream, False otherwise
    """
    if not self.is_ffmpeg_available():
        # If ffprobe unavailable, assume audio exists and let extraction fail gracefully
        return True

    try:
        # Use ffprobe to check for audio streams
        # -v quiet: suppress output
        # -select_streams a: select only audio streams
        # -show_entries stream=codec_type: show codec type
        # -of csv=p=0: output in CSV format without headers
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_type',
            '-of', 'csv=p=0',
            str(video_file)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )

        # If ffprobe returns "audio" for any stream, the video has audio
        return 'audio' in result.stdout.lower()

    except subprocess.TimeoutExpired:
        self.logger.debug_msg(f"Timeout checking audio stream in {video_file.name}")
        # Assume audio exists on timeout, let extraction handle it
        return True
    except Exception as e:
        self.logger.debug_msg(f"Error checking audio stream: {e}")
        # Assume audio exists on error, let extraction handle it
        return True
```

### Insert Location
- Insert the method after `convert_opus_to_m4a` method (around line 208)
- Before `extract_audio_from_video` method (line 210)

## Testing Plan

1. **Unit Test: Method exists and returns bool**
   - Verify `_has_audio_stream` method exists on `AudioConverter`
   - Verify it returns boolean values

2. **Unit Test: Video with audio stream**
   - Create/use test video with audio
   - Verify returns `True`

3. **Unit Test: Video without audio stream**
   - Create/use test video without audio (screen recording with no mic)
   - Verify returns `False`

4. **Integration Test: Full video transcription flow**
   - Run pipeline on WhatsApp export with video messages
   - Verify no AttributeError
   - Verify videos with audio are transcribed
   - Verify videos without audio are gracefully skipped

## Acceptance Criteria

- [ ] `_has_audio_stream` method implemented in `AudioConverter` class
- [ ] Method uses ffprobe to detect audio streams
- [ ] Method handles edge cases (timeout, errors) gracefully
- [ ] Video transcription works end-to-end without AttributeError
- [ ] Videos without audio tracks are skipped with informative message
