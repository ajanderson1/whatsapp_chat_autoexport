"""
Base transcriber interface for WhatsApp Chat Auto-Export.

Defines the abstract interface for transcription services.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TranscriptionResult:
    """Result of a transcription operation."""

    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None
    language: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()


class BaseTranscriber(ABC):
    """
    Abstract base class for transcription services.

    All transcription implementations must inherit from this class
    and implement the transcribe() method.
    """

    def __init__(self, logger=None):
        """
        Initialize the transcriber.

        Args:
            logger: Optional logger instance for output
        """
        self.logger = logger

    @abstractmethod
    def transcribe(self, audio_path: Path, **kwargs) -> TranscriptionResult:
        """
        Transcribe an audio or video file.

        Args:
            audio_path: Path to the audio/video file
            **kwargs: Additional service-specific parameters

        Returns:
            TranscriptionResult object with transcription text or error
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the transcription service is available.

        Returns:
            True if the service can be used, False otherwise
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported audio/video formats.

        Returns:
            List of file extensions (e.g., ['.mp3', '.m4a', '.wav'])
        """
        pass

    def validate_file(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """
        Validate that a file can be transcribed.

        Args:
            file_path: Path to the file to validate

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        # Check file exists
        if not file_path.exists():
            return False, f"File does not exist: {file_path}"

        # Check it's a file
        if not file_path.is_file():
            return False, f"Path is not a file: {file_path}"

        # Check file extension
        ext = file_path.suffix.lower()
        supported = self.get_supported_formats()

        if ext not in supported:
            return False, f"Unsupported format: {ext}. Supported: {', '.join(supported)}"

        # Check file is not empty
        if file_path.stat().st_size == 0:
            return False, f"File is empty: {file_path}"

        return True, None

    def log_info(self, message: str):
        """Log an info message if logger is available."""
        if self.logger:
            self.logger.info(message)

    def log_success(self, message: str):
        """Log a success message if logger is available."""
        if self.logger:
            self.logger.success(message)

    def log_warning(self, message: str):
        """Log a warning message if logger is available."""
        if self.logger:
            self.logger.warning(message)

    def log_error(self, message: str):
        """Log an error message if logger is available."""
        if self.logger:
            self.logger.error(message)

    def log_debug(self, message: str):
        """Log a debug message if logger is available."""
        if self.logger:
            self.logger.debug_msg(message)
