#!/usr/bin/env python3
"""
Test suite for transcription service.

Tests transcription interfaces, file handling, and batch processing.
"""

import sys
from pathlib import Path
import tempfile
import os

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from whatsapp_chat_autoexport.transcription import (
    BaseTranscriber,
    TranscriptionResult,
    WhisperTranscriber,
    TranscriptionManager
)
from whatsapp_chat_autoexport.utils.logger import Logger


class MockTranscriber(BaseTranscriber):
    """Mock transcriber for testing without API calls."""

    def __init__(self, logger=None, should_fail=False):
        super().__init__(logger)
        self.should_fail = should_fail
        self.transcribe_count = 0

    def transcribe(self, audio_path: Path, **kwargs) -> TranscriptionResult:
        """Mock transcription that returns fake text."""
        self.transcribe_count += 1

        if self.should_fail:
            return TranscriptionResult(
                success=False,
                error="Mock transcription failed"
            )

        return TranscriptionResult(
            success=True,
            text=f"Mock transcription of {audio_path.name}",
            duration_seconds=1.5,
            language="en",
            metadata={'model': 'mock'}
        )

    def is_available(self) -> bool:
        """Mock is always available."""
        return True

    def get_supported_formats(self) -> list[str]:
        """Return common audio formats."""
        return ['.mp3', '.m4a', '.opus', '.wav']


def test_import_modules():
    """Test that all transcription modules can be imported."""
    print("✓ All transcription modules imported successfully")
    return True


def test_transcription_result():
    """Test TranscriptionResult dataclass."""
    result = TranscriptionResult(
        success=True,
        text="Test transcription",
        duration_seconds=2.5,
        language="en"
    )

    print(f"\nTranscriptionResult:")
    print(f"  Success: {result.success}")
    print(f"  Text: {result.text}")
    print(f"  Duration: {result.duration_seconds}s")
    print(f"  Language: {result.language}")
    print(f"  Timestamp: {result.timestamp}")

    if not result.success:
        print("✗ Result should be successful")
        return False

    if result.text != "Test transcription":
        print("✗ Text doesn't match")
        return False

    if result.timestamp is None:
        print("✗ Timestamp should be auto-generated")
        return False

    print("✓ TranscriptionResult working correctly")
    return True


def test_base_transcriber_interface():
    """Test that BaseTranscriber enforces interface."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    # Test abstract methods are implemented
    if not hasattr(transcriber, 'transcribe'):
        print("✗ Missing transcribe method")
        return False

    if not hasattr(transcriber, 'is_available'):
        print("✗ Missing is_available method")
        return False

    if not hasattr(transcriber, 'get_supported_formats'):
        print("✗ Missing get_supported_formats method")
        return False

    print("✓ BaseTranscriber interface implemented correctly")
    return True


def test_file_validation():
    """Test file validation logic."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    # Create temp directory with test files
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Valid file
        valid_file = temp_path / "test.mp3"
        valid_file.write_text("fake audio data")

        is_valid, error = transcriber.validate_file(valid_file)
        if not is_valid:
            print(f"✗ Valid file rejected: {error}")
            return False

        # Nonexistent file
        nonexistent = temp_path / "missing.mp3"
        is_valid, error = transcriber.validate_file(nonexistent)
        if is_valid:
            print("✗ Nonexistent file should be invalid")
            return False

        # Unsupported format
        unsupported = temp_path / "test.xyz"
        unsupported.write_text("data")
        is_valid, error = transcriber.validate_file(unsupported)
        if is_valid:
            print("✗ Unsupported format should be invalid")
            return False

        # Empty file
        empty_file = temp_path / "empty.mp3"
        empty_file.touch()
        is_valid, error = transcriber.validate_file(empty_file)
        if is_valid:
            print("✗ Empty file should be invalid")
            return False

    print("✓ File validation working correctly")
    return True


def test_mock_transcription():
    """Test mock transcriber functionality."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create test audio file
        audio_file = temp_path / "test_audio.mp3"
        audio_file.write_text("fake audio data")

        # Transcribe
        result = transcriber.transcribe(audio_file)

        if not result.success:
            print(f"✗ Transcription failed: {result.error}")
            return False

        if not result.text:
            print("✗ No transcription text returned")
            return False

        if transcriber.transcribe_count != 1:
            print(f"✗ Expected 1 transcription, got {transcriber.transcribe_count}")
            return False

        print(f"  Transcription: {result.text}")
        print("✓ Mock transcription working correctly")
        return True


def test_whisper_availability():
    """Test Whisper transcriber availability check."""
    logger = Logger()

    # Whisper may not be available (no API key)
    transcriber = WhisperTranscriber(logger=logger)

    # Just check it doesn't crash
    is_available = transcriber.is_available()
    supported_formats = transcriber.get_supported_formats()

    print(f"\nWhisper Transcriber:")
    print(f"  Available: {is_available}")
    print(f"  Supported formats: {len(supported_formats)} formats")

    if not isinstance(supported_formats, list):
        print("✗ Supported formats should be a list")
        return False

    if len(supported_formats) == 0:
        print("✗ Should have some supported formats")
        return False

    print("✓ Whisper transcriber initialization working")
    return True


def test_transcription_manager_basic():
    """Test TranscriptionManager basic functionality."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Test transcription path generation
    media_file = Path("/test/audio.opus")
    transcription_path = manager.get_transcription_path(media_file)

    expected = Path("/test/audio_transcription.txt")
    if transcription_path != expected:
        print(f"✗ Expected {expected}, got {transcription_path}")
        return False

    print(f"  Transcription path: {transcription_path}")
    print("✓ TranscriptionManager basic functionality working")
    return True


def test_save_and_load_transcription():
    """Test saving and loading transcriptions."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create media file
        media_file = temp_path / "audio.m4a"
        media_file.write_text("fake audio")

        # Create transcription result
        result = TranscriptionResult(
            success=True,
            text="This is the transcription text.",
            duration_seconds=3.2,
            language="en",
            metadata={'model': 'test'}
        )

        # Save transcription
        transcription_path = manager.save_transcription(media_file, result)

        if not transcription_path:
            print("✗ Failed to save transcription")
            return False

        if not transcription_path.exists():
            print("✗ Transcription file not created")
            return False

        # Read transcription
        content = transcription_path.read_text()

        if "This is the transcription text." not in content:
            print("✗ Transcription text not in file")
            return False

        if "audio.m4a" not in content:
            print("✗ Filename metadata not in file")
            return False

        print(f"  Saved to: {transcription_path.name}")
        print(f"  Content length: {len(content)} chars")
        print("✓ Save/load transcription working")
        return True


def test_skip_existing_transcriptions():
    """Test resume functionality (skip existing transcriptions)."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create media file
        media_file = temp_path / "audio.mp3"
        media_file.write_text("fake audio")

        # Check not transcribed initially
        if manager.is_transcribed(media_file):
            print("✗ Should not be transcribed initially")
            return False

        # Transcribe
        success, trans_path, error = manager.transcribe_file(media_file, skip_existing=True)

        if not success:
            print(f"✗ First transcription failed: {error}")
            return False

        # Check now transcribed
        if not manager.is_transcribed(media_file):
            print("✗ Should be transcribed after transcription")
            return False

        # Reset counter
        transcriber.transcribe_count = 0

        # Transcribe again with skip_existing=True
        success, trans_path, error = manager.transcribe_file(media_file, skip_existing=True)

        if not success:
            print("✗ Second transcription should succeed (skip)")
            return False

        if transcriber.transcribe_count != 0:
            print(f"✗ Should skip existing (count={transcriber.transcribe_count})")
            return False

        print("✓ Skip existing transcriptions working")
        return True


def test_batch_transcription():
    """Test batch transcription of multiple files."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create multiple media files
        media_files = []
        for i in range(5):
            media_file = temp_path / f"audio_{i}.mp3"
            media_file.write_text(f"fake audio {i}")
            media_files.append(media_file)

        # Batch transcribe
        results = manager.batch_transcribe(
            media_files,
            skip_existing=False,
            show_progress=False  # Disable for tests
        )

        if results['total'] != 5:
            print(f"✗ Expected 5 total, got {results['total']}")
            return False

        if results['successful'] != 5:
            print(f"✗ Expected 5 successful, got {results['successful']}")
            return False

        if results['failed'] != 0:
            print(f"✗ Expected 0 failed, got {results['failed']}")
            return False

        if len(results['transcriptions']) != 5:
            print(f"✗ Expected 5 transcriptions, got {len(results['transcriptions'])}")
            return False

        # Verify files exist
        for trans_path in results['transcriptions']:
            if not trans_path.exists():
                print(f"✗ Transcription file not found: {trans_path}")
                return False

        print(f"\n  Batch results:")
        print(f"    Total: {results['total']}")
        print(f"    Successful: {results['successful']}")
        print(f"    Failed: {results['failed']}")
        print("✓ Batch transcription working")
        return True


def test_get_transcribable_files():
    """Test finding transcribable files in directory."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create various files
        (temp_path / "audio1.mp3").write_text("audio")
        (temp_path / "audio2.m4a").write_text("audio")
        (temp_path / "audio3.opus").write_text("audio")
        (temp_path / "video.mp4").write_text("video")  # Not in supported formats
        (temp_path / "text.txt").write_text("text")  # Not audio
        (temp_path / "audio_transcription.txt").write_text("transcription")  # Should be skipped

        # Create subdirectory
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "audio4.wav").write_text("audio")

        # Find transcribable files (recursive)
        files = manager.get_transcribable_files(temp_path, recursive=True)

        # Should find 4 audio files (.mp3, .m4a, .opus, .wav)
        if len(files) != 4:
            print(f"✗ Expected 4 transcribable files, found {len(files)}")
            for f in files:
                print(f"    {f.name}")
            return False

        print(f"  Found {len(files)} transcribable files")
        print("✓ Finding transcribable files working")
        return True


def test_progress_summary():
    """Test progress summary generation."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create 3 audio files
        for i in range(3):
            (temp_path / f"audio_{i}.mp3").write_text("audio")

        # Transcribe 2 of them
        manager.transcribe_file(temp_path / "audio_0.mp3", skip_existing=False)
        manager.transcribe_file(temp_path / "audio_1.mp3", skip_existing=False)

        # Get progress summary
        summary = manager.get_progress_summary(temp_path)

        if summary['total'] != 3:
            print(f"✗ Expected 3 total, got {summary['total']}")
            return False

        if summary['transcribed'] != 2:
            print(f"✗ Expected 2 transcribed, got {summary['transcribed']}")
            return False

        if summary['pending'] != 1:
            print(f"✗ Expected 1 pending, got {summary['pending']}")
            return False

        expected_percent = (2/3) * 100
        if abs(summary['progress_percent'] - expected_percent) > 0.1:
            print(f"✗ Expected {expected_percent:.1f}%, got {summary['progress_percent']:.1f}%")
            return False

        print(f"\n  Progress:")
        print(f"    Total: {summary['total']}")
        print(f"    Transcribed: {summary['transcribed']}")
        print(f"    Pending: {summary['pending']}")
        print(f"    Progress: {summary['progress_percent']:.1f}%")
        print("✓ Progress summary working")
        return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("Transcription Service Test Suite")
    print("=" * 70)

    tests = [
        ("Import Modules", test_import_modules),
        ("TranscriptionResult", test_transcription_result),
        ("BaseTranscriber Interface", test_base_transcriber_interface),
        ("File Validation", test_file_validation),
        ("Mock Transcription", test_mock_transcription),
        ("Whisper Availability", test_whisper_availability),
        ("TranscriptionManager Basic", test_transcription_manager_basic),
        ("Save/Load Transcription", test_save_and_load_transcription),
        ("Skip Existing Transcriptions", test_skip_existing_transcriptions),
        ("Batch Transcription", test_batch_transcription),
        ("Get Transcribable Files", test_get_transcribable_files),
        ("Progress Summary", test_progress_summary),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{'─' * 70}")
        print(f"Test: {test_name}")
        print('─' * 70)

        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("=" * 70)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 70)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
