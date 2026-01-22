"""
Unit tests for AudioConverter class.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whatsapp_chat_autoexport.utils.audio_converter import (
    AudioConverter,
    is_whatsapp_video_message,
)


class TestIsWhatsAppVideoMessage:
    """Tests for the is_whatsapp_video_message helper function."""

    def test_valid_video_message_pattern(self):
        """Test that valid WhatsApp video filenames are recognized."""
        assert is_whatsapp_video_message("VID-20231207-WA0000.mp4") is True
        assert is_whatsapp_video_message("VID-20251004-WA0011.mp4") is True
        assert is_whatsapp_video_message("VID-20170101-WA9999.mp4") is True

    def test_case_insensitive(self):
        """Test that pattern matching is case-insensitive."""
        assert is_whatsapp_video_message("vid-20231207-wa0000.mp4") is True
        assert is_whatsapp_video_message("VID-20231207-wa0000.MP4") is True

    def test_invalid_patterns(self):
        """Test that non-WhatsApp video filenames are rejected."""
        assert is_whatsapp_video_message("video.mp4") is False
        assert is_whatsapp_video_message("movie.avi") is False
        assert is_whatsapp_video_message("IMG-20231207-WA0000.jpg") is False
        assert is_whatsapp_video_message("PTT-20231207-WA0000.opus") is False
        assert is_whatsapp_video_message("VID-123-WA0000.mp4") is False  # Wrong date format


class TestAudioConverterHasAudioStream:
    """Tests for AudioConverter._has_audio_stream method."""

    @pytest.fixture
    def converter(self):
        """Create an AudioConverter instance with mocked logger."""
        logger = MagicMock()
        return AudioConverter(logger=logger)

    def test_method_exists(self, converter):
        """Test that _has_audio_stream method exists."""
        assert hasattr(converter, '_has_audio_stream')
        assert callable(converter._has_audio_stream)

    def test_returns_bool(self, converter, temp_working_dir):
        """Test that method returns a boolean value."""
        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=False):
            result = converter._has_audio_stream(dummy_video)
            assert isinstance(result, bool)

    @patch('subprocess.run')
    def test_video_with_audio_stream(self, mock_run, converter, temp_working_dir):
        """Test detection of video with audio stream."""
        # Mock ffprobe returning "audio" for a stream
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="audio\n",
            stderr=""
        )

        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            result = converter._has_audio_stream(dummy_video)

        assert result is True
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_video_without_audio_stream(self, mock_run, converter, temp_working_dir):
        """Test detection of video without audio stream."""
        # Mock ffprobe returning empty output (no audio streams)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )

        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            result = converter._has_audio_stream(dummy_video)

        assert result is False

    def test_ffmpeg_unavailable_returns_true(self, converter, temp_working_dir):
        """Test that method returns True when FFmpeg is unavailable (fail-open)."""
        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=False):
            result = converter._has_audio_stream(dummy_video)

        # Should assume audio exists when we can't check
        assert result is True

    @patch('subprocess.run')
    def test_timeout_returns_true(self, mock_run, converter, temp_working_dir):
        """Test that method returns True on timeout (fail-open)."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=10)

        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            result = converter._has_audio_stream(dummy_video)

        # Should assume audio exists on timeout
        assert result is True

    @patch('subprocess.run')
    def test_exception_returns_true(self, mock_run, converter, temp_working_dir):
        """Test that method returns True on general exception (fail-open)."""
        mock_run.side_effect = Exception("Unexpected error")

        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            result = converter._has_audio_stream(dummy_video)

        # Should assume audio exists on error
        assert result is True

    @patch('subprocess.run')
    def test_calls_ffprobe_with_correct_args(self, mock_run, converter, temp_working_dir):
        """Test that ffprobe is called with correct arguments."""
        mock_run.return_value = MagicMock(returncode=0, stdout="audio", stderr="")

        dummy_video = temp_working_dir / "test.mp4"
        dummy_video.write_bytes(b"dummy")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            converter._has_audio_stream(dummy_video)

        # Verify ffprobe was called with expected arguments
        call_args = mock_run.call_args
        cmd = call_args[0][0]

        assert cmd[0] == 'ffprobe'
        assert '-v' in cmd and 'quiet' in cmd
        assert '-select_streams' in cmd and 'a' in cmd
        assert str(dummy_video) in cmd


class TestExtractAudioFromVideoIntegration:
    """Integration tests for extract_audio_from_video with _has_audio_stream."""

    @pytest.fixture
    def converter(self):
        """Create an AudioConverter instance with mocked logger."""
        logger = MagicMock()
        return AudioConverter(logger=logger)

    @patch('subprocess.run')
    def test_skips_extraction_when_no_audio(self, mock_run, converter, temp_working_dir):
        """Test that extraction is skipped when video has no audio stream."""
        # First call to ffprobe (for _has_audio_stream) returns no audio
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        dummy_video = temp_working_dir / "VID-20231207-WA0000.mp4"
        dummy_video.write_bytes(b"dummy video content")

        with patch.object(converter, 'is_ffmpeg_available', return_value=True):
            result = converter.extract_audio_from_video(dummy_video)

        # Should return None because no audio stream
        assert result is None

        # FFprobe should be called for audio check, but ffmpeg extraction should NOT be called
        # (only one subprocess.run call for ffprobe)
        assert mock_run.call_count == 1
