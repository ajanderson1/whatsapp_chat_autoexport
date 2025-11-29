"""
Transcription module for WhatsApp Chat Auto-Export.

Provides audio and video transcription services with pluggable backends.
"""

from .base_transcriber import BaseTranscriber, TranscriptionResult
from .whisper_transcriber import WhisperTranscriber
from .transcription_manager import TranscriptionManager

__all__ = [
    'BaseTranscriber',
    'TranscriptionResult',
    'WhisperTranscriber',
    'TranscriptionManager',
]
