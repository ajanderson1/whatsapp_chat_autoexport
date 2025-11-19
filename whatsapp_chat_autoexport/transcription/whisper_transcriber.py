"""
OpenAI Whisper transcriber implementation.

Uses OpenAI's Whisper API for audio/video transcription.
"""

import os
import time
from pathlib import Path
from typing import Optional

from .base_transcriber import BaseTranscriber, TranscriptionResult
from ..utils.audio_converter import AudioConverter

# OpenAI import (will be optional)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class WhisperTranscriber(BaseTranscriber):
    """
    OpenAI Whisper transcription service.

    Uses the OpenAI API to transcribe audio and video files.
    Requires OPENAI_API_KEY environment variable to be set.
    """

    # Maximum file size for Whisper API (25 MB)
    MAX_FILE_SIZE_MB = 25

    # Supported formats per OpenAI docs
    SUPPORTED_FORMATS = [
        '.mp3', '.mp4', '.mpeg', '.mpga',
        '.m4a', '.wav', '.webm', '.ogg',
        '.opus', '.flac'
    ]

    def __init__(self, api_key: Optional[str] = None, logger=None, model: str = "whisper-1", convert_opus: bool = True):
        """
        Initialize Whisper transcriber.

        Args:
            api_key: OpenAI API key (if None, uses OPENAI_API_KEY env var)
            logger: Optional logger instance
            model: Whisper model to use (default: "whisper-1")
            convert_opus: Whether to convert Opus files to M4A (default: True)
        """
        super().__init__(logger)

        if not OPENAI_AVAILABLE:
            self.log_error("OpenAI package not installed. Install with: pip install openai")
            self.client = None
            self.model = None
            self.audio_converter = None
            return

        # Check for API key early to provide helpful error message
        effective_api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not effective_api_key:
            self.log_error(
                "OpenAI API key not found!\n"
                "Please set the OPENAI_API_KEY environment variable:\n"
                "  export OPENAI_API_KEY='your-api-key-here'\n"
                "Or get your API key from: https://platform.openai.com/api-keys"
            )
            self.client = None
            self.model = None
            self.audio_converter = None
            return

        self.model = model
        self.convert_opus = convert_opus
        self.audio_converter = AudioConverter(logger=logger) if convert_opus else None

        try:
            # Initialize OpenAI client with the API key
            # Don't pass api_key=None, as that prevents SDK from reading env var
            if api_key:
                self.client = OpenAI(api_key=api_key)
            else:
                # Let SDK read from environment variable
                self.client = OpenAI()

            self.log_debug(f"Initialized OpenAI Whisper with model: {model}")
            if convert_opus and self.audio_converter:
                if self.audio_converter.is_ffmpeg_available():
                    self.log_debug("Opus to M4A conversion enabled (FFmpeg available)")
                else:
                    self.log_warning("Opus to M4A conversion requested but FFmpeg not available")
        except Exception as e:
            self.log_error(f"Failed to initialize OpenAI client: {e}")
            self.client = None

    def is_available(self) -> bool:
        """
        Check if Whisper service is available.

        Returns:
            True if OpenAI package is installed and client is initialized
        """
        return OPENAI_AVAILABLE and self.client is not None

    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported audio/video formats.

        Returns:
            List of file extensions supported by Whisper API
        """
        return self.SUPPORTED_FORMATS.copy()

    def _check_existing_transcription(self, audio_path: Path) -> Optional[str]:
        """
        Check if transcription already exists for this audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcription text if exists and non-empty, None otherwise
        """
        # Calculate expected transcription path (same logic as TranscriptionManager)
        transcription_path = audio_path.parent / f"{audio_path.stem}_transcription.txt"
        
        try:
            if not transcription_path.exists():
                return None
            
            # Check if file is not empty
            if transcription_path.stat().st_size == 0:
                self.log_debug(f"Found empty transcription file: {transcription_path.name}")
                return None
            
            # Read the transcription file
            with open(transcription_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Extract text, skipping metadata lines (starting with #)
            text_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip metadata headers and empty lines
                if stripped and not stripped.startswith('#'):
                    text_lines.append(stripped)
            
            transcription_text = '\n'.join(text_lines)
            
            if transcription_text:
                self.log_debug(f"Found existing transcription: {transcription_path.name} ({len(transcription_text)} chars)")
                return transcription_text
            else:
                return None
                
        except Exception as e:
            self.log_debug(f"Could not read existing transcription: {e}")
            return None

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0,
        skip_existing: bool = True,
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe an audio or video file using OpenAI Whisper.

        Args:
            audio_path: Path to the audio/video file
            language: Optional ISO-639-1 language code (e.g., 'en', 'es')
            prompt: Optional text to guide the model's style
            temperature: Sampling temperature (0-1, default: 0 for deterministic)
            skip_existing: Skip transcription if file already exists (default: True)
            **kwargs: Additional parameters passed to the API

        Returns:
            TranscriptionResult with transcription text or error
        """
        # Check if service is available
        if not self.is_available():
            return TranscriptionResult(
                success=False,
                error="OpenAI Whisper service not available. Check API key and installation."
            )

        # DEFENSIVE CHECK: Skip if transcription already exists (if skip_existing=True)
        # This prevents unnecessary opus conversion even if called directly
        if skip_existing:
            existing_transcription = self._check_existing_transcription(audio_path)
            if existing_transcription:
                self.log_info(f"⏭️  Skipping (transcription exists): {audio_path.name}")
                return TranscriptionResult(
                    success=True,
                    text=existing_transcription,
                    duration_seconds=0.0,
                    language=language,
                    metadata={
                        'cached': True,
                        'source': 'existing_transcription'
                    }
                )

        # Validate file
        is_valid, error_msg = self.validate_file(audio_path)
        if not is_valid:
            return TranscriptionResult(
                success=False,
                error=error_msg
            )

        # Check if file is Opus and needs conversion
        temp_m4a_file = None
        actual_file_to_transcribe = audio_path
        
        if audio_path.suffix.lower() == '.opus':
            if self.convert_opus and self.audio_converter:
                if not self.audio_converter.is_ffmpeg_available():
                    return TranscriptionResult(
                        success=False,
                        error="Opus file requires FFmpeg for conversion. Install FFmpeg or use --skip-opus-conversion."
                    )
                
                self.log_info(f"🔄 Converting Opus to M4A for Whisper API compatibility...")
                temp_m4a_file = self.audio_converter.convert_opus_to_m4a(
                    audio_path,
                    temp_dir=audio_path.parent
                )
                
                if not temp_m4a_file:
                    return TranscriptionResult(
                        success=False,
                        error="Failed to convert Opus file to M4A"
                    )
                
                actual_file_to_transcribe = temp_m4a_file
                self.log_debug(f"✓ Converted to: {temp_m4a_file.name}")
            else:
                return TranscriptionResult(
                    success=False,
                    error="Opus format not supported by Whisper API. Enable opus conversion or install FFmpeg."
                )

        # Check file size
        file_size_mb = actual_file_to_transcribe.stat().st_size / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            # Cleanup temp file if created
            if temp_m4a_file and temp_m4a_file.exists():
                temp_m4a_file.unlink()
            
            return TranscriptionResult(
                success=False,
                error=f"File too large: {file_size_mb:.1f} MB (max: {self.MAX_FILE_SIZE_MB} MB)"
            )

        self.log_info(f"Transcribing: {audio_path.name} ({file_size_mb:.2f} MB)")

        start_time = time.time()

        try:
            # Open file and send to Whisper API
            with open(actual_file_to_transcribe, 'rb') as audio_file:
                # Build request parameters
                request_params = {
                    'model': self.model,
                    'file': audio_file,
                    'response_format': 'text',  # Get plain text response
                    'temperature': temperature,
                }

                # Add optional parameters
                if language:
                    request_params['language'] = language
                if prompt:
                    request_params['prompt'] = prompt

                # Add any additional kwargs
                request_params.update(kwargs)

                # Call API
                transcript = self.client.audio.transcriptions.create(**request_params)

            duration = time.time() - start_time

            # The response is just a string when response_format='text'
            transcription_text = transcript.strip()

            if not transcription_text:
                return TranscriptionResult(
                    success=False,
                    error="Transcription returned empty text",
                    duration_seconds=duration
                )

            self.log_success(f"✓ Transcribed {audio_path.name} in {duration:.1f}s ({len(transcription_text)} chars)")

            return TranscriptionResult(
                success=True,
                text=transcription_text,
                duration_seconds=duration,
                language=language,
                metadata={
                    'model': self.model,
                    'file_size_mb': file_size_mb,
                    'temperature': temperature,
                    'was_converted': temp_m4a_file is not None,
                    'original_format': audio_path.suffix if temp_m4a_file else None
                }
            )

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Transcription failed: {str(e)}"
            self.log_error(error_msg)

            return TranscriptionResult(
                success=False,
                error=error_msg,
                duration_seconds=duration
            )
        
        finally:
            # Always cleanup temporary M4A file
            if temp_m4a_file and temp_m4a_file.exists():
                try:
                    temp_m4a_file.unlink()
                    self.log_debug(f"Cleaned up temp file: {temp_m4a_file.name}")
                except Exception as e:
                    self.log_warning(f"Failed to cleanup temp file: {e}")

    def transcribe_with_retry(
        self,
        audio_path: Path,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe with automatic retry on failure.

        Args:
            audio_path: Path to the audio/video file
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            **kwargs: Additional parameters passed to transcribe()

        Returns:
            TranscriptionResult with transcription text or error
        """
        for attempt in range(max_retries):
            result = self.transcribe(audio_path, **kwargs)

            if result.success:
                return result

            if attempt < max_retries - 1:
                self.log_warning(f"Retry {attempt + 1}/{max_retries - 1} for {audio_path.name}")
                time.sleep(retry_delay)
            else:
                self.log_error(f"Failed after {max_retries} attempts: {audio_path.name}")

        return result

    def estimate_cost(self, file_size_mb: float) -> float:
        """
        Estimate transcription cost in USD.

        OpenAI Whisper pricing: $0.006 per minute (as of 2024)
        Rough estimate: 1 MB ≈ 1 minute of audio

        Args:
            file_size_mb: File size in megabytes

        Returns:
            Estimated cost in USD
        """
        estimated_minutes = file_size_mb  # Rough approximation
        cost_per_minute = 0.006
        return estimated_minutes * cost_per_minute
