"""
Transcription module for WhatsApp Chat Auto-Export.

Provides audio and video transcription services with pluggable backends.
"""

from .base_transcriber import BaseTranscriber, TranscriptionResult
from .transcription_manager import TranscriptionManager
from .whisper_transcriber import WhisperTranscriber

__all__ = [
    "BaseTranscriber",
    "TranscriptionResult",
    "WhisperTranscriber",
    "TranscriptionManager",
]
