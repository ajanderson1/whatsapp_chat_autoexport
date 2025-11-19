"""
Test suite for transcription service.

Tests transcription interfaces, file handling, and batch processing.
"""

from pathlib import Path

import pytest

from whatsapp_chat_autoexport.transcription import (
    BaseTranscriber,
    TranscriptionResult,
    WhisperTranscriber,
    TranscriptionManager,
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
            return TranscriptionResult(success=False, error="Mock transcription failed")

        return TranscriptionResult(
            success=True,
            text=f"Mock transcription of {audio_path.name}",
            duration_seconds=1.5,
            language="en",
            metadata={"model": "mock"},
        )

    def is_available(self) -> bool:
        """Mock is always available."""
        return True

    def get_supported_formats(self) -> list[str]:
        """Return common audio formats."""
        return [".mp3", ".m4a", ".opus", ".wav"]


@pytest.mark.unit
def test_import_modules():
    """Test that all transcription modules can be imported."""
    # If we got here, imports succeeded
    assert BaseTranscriber is not None
    assert TranscriptionResult is not None
    assert WhisperTranscriber is not None
    assert TranscriptionManager is not None


@pytest.mark.unit
def test_transcription_result():
    """Test TranscriptionResult dataclass."""
    result = TranscriptionResult(
        success=True, text="Test transcription", duration_seconds=2.5, language="en"
    )

    assert result.success is True
    assert result.text == "Test transcription"
    assert result.duration_seconds == 2.5
    assert result.language == "en"
    assert result.timestamp is not None  # Auto-generated


@pytest.mark.unit
def test_base_transcriber_interface():
    """Test that BaseTranscriber enforces interface."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    # Test abstract methods are implemented
    assert hasattr(transcriber, "transcribe")
    assert hasattr(transcriber, "is_available")
    assert hasattr(transcriber, "get_supported_formats")
    assert callable(transcriber.transcribe)
    assert callable(transcriber.is_available)
    assert callable(transcriber.get_supported_formats)


@pytest.mark.unit
def test_file_validation(temp_working_dir):
    """Test file validation logic."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    # Valid file
    valid_file = temp_working_dir / "test.mp3"
    valid_file.write_text("fake audio data")

    is_valid, error = transcriber.validate_file(valid_file)
    assert is_valid is True, f"Valid file rejected: {error}"

    # Nonexistent file
    nonexistent = temp_working_dir / "missing.mp3"
    is_valid, error = transcriber.validate_file(nonexistent)
    assert is_valid is False, "Nonexistent file should be invalid"
    assert error is not None

    # Unsupported format
    unsupported = temp_working_dir / "test.xyz"
    unsupported.write_text("data")
    is_valid, error = transcriber.validate_file(unsupported)
    assert is_valid is False, "Unsupported format should be invalid"
    assert error is not None

    # Empty file
    empty_file = temp_working_dir / "empty.mp3"
    empty_file.touch()
    is_valid, error = transcriber.validate_file(empty_file)
    assert is_valid is False, "Empty file should be invalid"
    assert error is not None


@pytest.mark.unit
def test_mock_transcription(temp_working_dir):
    """Test mock transcriber functionality."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)

    # Create test audio file
    audio_file = temp_working_dir / "test_audio.mp3"
    audio_file.write_text("fake audio data")

    # Transcribe
    result = transcriber.transcribe(audio_file)

    assert result.success is True, f"Transcription failed: {result.error}"
    assert result.text is not None and len(result.text) > 0
    assert transcriber.transcribe_count == 1
    assert "test_audio.mp3" in result.text


@pytest.mark.unit
@pytest.mark.requires_api
def test_whisper_availability():
    """Test Whisper transcriber availability check."""
    logger = Logger()

    # Whisper may not be available (no API key)
    transcriber = WhisperTranscriber(logger=logger)

    # Just check it doesn't crash
    is_available = transcriber.is_available()
    supported_formats = transcriber.get_supported_formats()

    assert isinstance(is_available, bool)
    assert isinstance(supported_formats, list)
    assert len(supported_formats) > 0, "Should have some supported formats"


@pytest.mark.unit
def test_transcription_manager_basic():
    """Test TranscriptionManager basic functionality."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Test transcription path generation
    media_file = Path("/test/audio.opus")
    transcription_path = manager.get_transcription_path(media_file)

    expected = Path("/test/audio_transcription.txt")
    assert transcription_path == expected


@pytest.mark.unit
def test_save_and_load_transcription(temp_working_dir):
    """Test saving and loading transcriptions."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Create media file
    media_file = temp_working_dir / "audio.m4a"
    media_file.write_text("fake audio")

    # Create transcription result
    result = TranscriptionResult(
        success=True,
        text="This is the transcription text.",
        duration_seconds=3.2,
        language="en",
        metadata={"model": "test"},
    )

    # Save transcription
    transcription_path = manager.save_transcription(media_file, result)

    assert transcription_path is not None, "Failed to save transcription"
    assert transcription_path.exists(), "Transcription file not created"

    # Read transcription
    content = transcription_path.read_text()

    assert "This is the transcription text." in content
    assert "audio.m4a" in content


@pytest.mark.unit
def test_skip_existing_transcriptions(temp_working_dir):
    """Test resume functionality (skip existing transcriptions)."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Create media file
    media_file = temp_working_dir / "audio.mp3"
    media_file.write_text("fake audio")

    # Check not transcribed initially (returns tuple: (bool, location))
    is_transcribed, _ = manager.is_transcribed(media_file)
    assert is_transcribed is False

    # Transcribe
    success, trans_path, error = manager.transcribe_file(media_file, skip_existing=True)

    assert success is True, f"First transcription failed: {error}"
    assert trans_path is not None

    # Check now transcribed (returns tuple: (bool, location))
    is_transcribed, location = manager.is_transcribed(media_file)
    assert is_transcribed is True
    assert location == "temp"

    # Reset counter
    transcriber.transcribe_count = 0

    # Transcribe again with skip_existing=True
    success, trans_path, error = manager.transcribe_file(media_file, skip_existing=True)

    assert success is True, "Second transcription should succeed (skip)"
    assert transcriber.transcribe_count == 0, "Should skip existing transcription"


@pytest.mark.unit
@pytest.mark.slow
def test_batch_transcription(temp_working_dir):
    """Test batch transcription of multiple files."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Create multiple media files
    media_files = []
    for i in range(5):
        media_file = temp_working_dir / f"audio_{i}.mp3"
        media_file.write_text(f"fake audio {i}")
        media_files.append(media_file)

    # Batch transcribe
    results = manager.batch_transcribe(
        media_files, skip_existing=False, show_progress=False  # Disable for tests
    )

    assert results["total"] == 5
    assert results["successful"] == 5
    assert results["failed"] == 0
    assert len(results["transcriptions"]) == 5

    # Verify files exist
    for trans_path in results["transcriptions"]:
        assert trans_path.exists(), f"Transcription file not found: {trans_path}"


@pytest.mark.unit
def test_get_transcribable_files(temp_working_dir):
    """Test finding transcribable files in directory."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Create various files
    (temp_working_dir / "audio1.mp3").write_text("audio")
    (temp_working_dir / "audio2.m4a").write_text("audio")
    (temp_working_dir / "audio3.opus").write_text("audio")
    (temp_working_dir / "video.mp4").write_text("video")  # Not in supported formats
    (temp_working_dir / "text.txt").write_text("text")  # Not audio
    (temp_working_dir / "audio_transcription.txt").write_text(
        "transcription"
    )  # Should be skipped

    # Create subdirectory
    subdir = temp_working_dir / "subdir"
    subdir.mkdir()
    (subdir / "audio4.wav").write_text("audio")

    # Find transcribable files (recursive)
    files = manager.get_transcribable_files(temp_working_dir, recursive=True)

    # Should find 4 audio files (.mp3, .m4a, .opus, .wav)
    assert len(files) == 4, f"Expected 4 transcribable files, found {len(files)}"


@pytest.mark.unit
def test_progress_summary(temp_working_dir):
    """Test progress summary generation."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger)
    manager = TranscriptionManager(transcriber, logger=logger)

    # Create 4 audio files in a clean subdirectory for better isolation
    test_dir = temp_working_dir / "progress_test"
    test_dir.mkdir()

    for i in range(4):
        (test_dir / f"audio_{i}.mp3").write_text("audio")

    # Transcribe 2 of them explicitly
    manager.transcribe_file(test_dir / "audio_0.mp3", skip_existing=False)
    manager.transcribe_file(test_dir / "audio_1.mp3", skip_existing=False)

    # Get progress summary
    summary = manager.get_progress_summary(test_dir)

    # Verify structure of summary
    assert "total" in summary
    assert "transcribed" in summary
    assert "pending" in summary
    assert "progress_percent" in summary

    # Verify logical consistency
    assert summary["total"] == 4, f"Expected 4 total files, got {summary['total']}"
    assert summary["transcribed"] >= 2, f"Should have at least 2 transcribed, got {summary['transcribed']}"
    assert summary["pending"] >= 0, f"Pending should be non-negative, got {summary['pending']}"
    assert summary["transcribed"] + summary["pending"] == summary["total"], "Transcribed + pending should equal total"
    assert 0 <= summary["progress_percent"] <= 100, "Progress percent should be 0-100"


@pytest.mark.unit
def test_mock_transcriber_failure(temp_working_dir):
    """Test mock transcriber with failure mode."""
    logger = Logger()
    transcriber = MockTranscriber(logger=logger, should_fail=True)

    # Create test audio file
    audio_file = temp_working_dir / "test_audio.mp3"
    audio_file.write_text("fake audio data")

    # Transcribe
    result = transcriber.transcribe(audio_file)

    assert result.success is False
    assert result.error is not None
    assert "Mock transcription failed" in result.error
