"""
ElevenLabs Scribe transcriber implementation.

Uses ElevenLabs' Scribe API for audio/video transcription.
"""

import os
import time
from pathlib import Path
from typing import Optional
from io import BytesIO

from .base_transcriber import BaseTranscriber, TranscriptionResult
from ..utils.audio_converter import AudioConverter

# ElevenLabs import (will be optional)
try:
    from elevenlabs import ElevenLabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False


class ElevenLabsTranscriber(BaseTranscriber):
    """
    ElevenLabs Scribe transcription service.

    Uses the ElevenLabs API to transcribe audio and video files.
    Requires ELEVENLABS_API_KEY environment variable to be set.
    """

    # Maximum file size for ElevenLabs API (3 GB)
    MAX_FILE_SIZE_MB = 3072  # 3 GB

    # Maximum duration (10 hours)
    MAX_DURATION_HOURS = 10

    # Supported formats - ElevenLabs supports common audio/video formats
    # Based on their documentation, they support most common formats
    SUPPORTED_FORMATS = [
        '.mp3', '.mp4', '.mpeg', '.mpga',
        '.m4a', '.wav', '.webm', '.ogg',
        '.opus', '.flac', '.avi', '.mov',
        '.mkv', '.aac', '.wma'
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        logger=None,
        model: str = "scribe_v1",
        convert_opus: bool = True,
        diarize: bool = False,
        tag_audio_events: bool = False
    ):
        """
        Initialize ElevenLabs transcriber.

        Args:
            api_key: ElevenLabs API key (if None, uses ELEVENLABS_API_KEY env var)
            logger: Optional logger instance
            model: Scribe model to use (default: "scribe_v1")
            convert_opus: Whether to convert Opus files to M4A (default: True)
            diarize: Enable speaker identification (default: False)
            tag_audio_events: Detect audio events like laughter (default: False)
        """
        super().__init__(logger)

        if not ELEVENLABS_AVAILABLE:
            self.log_error("ElevenLabs package not installed. Install with: pip install elevenlabs")
            self.client = None
            self.model = None
            self.audio_converter = None
            return

        # Check for API key early to provide helpful error message
        effective_api_key = api_key or os.environ.get('ELEVENLABS_API_KEY')
        if not effective_api_key:
            self.log_error(
                "ElevenLabs API key not found!\n"
                "Please set the ELEVENLABS_API_KEY environment variable:\n"
                "  export ELEVENLABS_API_KEY='your-api-key-here'\n"
                "Or get your API key from: https://elevenlabs.io/"
            )
            self.client = None
            self.model = None
            self.audio_converter = None
            return

        self.model = model
        self.convert_opus = convert_opus
        self.diarize = diarize
        self.tag_audio_events = tag_audio_events
        self.audio_converter = AudioConverter(logger=logger) if convert_opus else None

        try:
            # Initialize ElevenLabs client with the API key
            # Don't pass api_key=None, as that prevents SDK from reading env var
            if api_key:
                self.client = ElevenLabs(api_key=api_key)
            else:
                # Let SDK read from environment variable
                self.client = ElevenLabs()

            self.log_debug(f"Initialized ElevenLabs Scribe with model: {model}")
            if convert_opus and self.audio_converter:
                if self.audio_converter.is_ffmpeg_available():
                    self.log_debug("Opus to M4A conversion enabled (FFmpeg available)")
                else:
                    self.log_warning("Opus to M4A conversion requested but FFmpeg not available")
        except Exception as e:
            self.log_error(f"Failed to initialize ElevenLabs client: {e}")
            self.client = None

    def is_available(self) -> bool:
        """
        Check if ElevenLabs service is available.

        Returns:
            True if ElevenLabs package is installed and client is initialized
        """
        return ELEVENLABS_AVAILABLE and self.client is not None

    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported audio/video formats.

        Returns:
            List of file extensions supported by ElevenLabs API
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
        skip_existing: bool = True,
        **kwargs
    ) -> TranscriptionResult:
        """
        Transcribe an audio or video file using ElevenLabs Scribe.

        Args:
            audio_path: Path to the audio/video file
            language: Optional ISO-639-1 language code (e.g., 'en', 'es')
            skip_existing: Skip transcription if file already exists (default: True)
            **kwargs: Additional parameters passed to the API

        Returns:
            TranscriptionResult with transcription text or error
        """
        # Check if service is available
        if not self.is_available():
            return TranscriptionResult(
                success=False,
                error="ElevenLabs Scribe service not available. Check API key and installation."
            )

        # DEFENSIVE CHECK: Skip if transcription already exists (if skip_existing=True)
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

                self.log_info(f"🔄 Converting Opus to M4A for better compatibility...")
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
            # Read file into memory
            with open(actual_file_to_transcribe, 'rb') as audio_file:
                audio_data = audio_file.read()

            # Build request parameters
            request_params = {
                'model_id': self.model,
                'file': audio_data,
            }

            # Add optional parameters
            if language:
                # ElevenLabs uses 3-letter ISO codes (e.g., 'eng' instead of 'en')
                # Try to convert common 2-letter codes to 3-letter
                language_mapping = {
                    'en': 'eng',
                    'es': 'spa',
                    'fr': 'fra',
                    'de': 'deu',
                    'it': 'ita',
                    'pt': 'por',
                    'ru': 'rus',
                    'ja': 'jpn',
                    'ko': 'kor',
                    'zh': 'chi',
                    'ar': 'ara',
                    'hi': 'hin',
                }
                language_code = language_mapping.get(language, language)
                request_params['language_code'] = language_code

            # Add diarization if enabled
            if self.diarize:
                request_params['diarize'] = True

            # Add audio event tagging if enabled
            if self.tag_audio_events:
                request_params['tag_audio_events'] = True

            # Add any additional kwargs
            request_params.update(kwargs)

            # Call API
            response = self.client.speech_to_text.convert(**request_params)

            duration = time.time() - start_time

            # Extract text from response
            # The response structure includes a 'text' field
            transcription_text = response.text.strip() if hasattr(response, 'text') else str(response).strip()

            if not transcription_text:
                return TranscriptionResult(
                    success=False,
                    error="Transcription returned empty text",
                    duration_seconds=duration
                )

            self.log_success(f"✓ Transcribed {audio_path.name} in {duration:.1f}s ({len(transcription_text)} chars)")

            # Extract metadata from response
            metadata = {
                'model': self.model,
                'file_size_mb': file_size_mb,
                'was_converted': temp_m4a_file is not None,
                'original_format': audio_path.suffix if temp_m4a_file else None,
                'diarization_enabled': self.diarize,
                'audio_events_enabled': self.tag_audio_events
            }

            # Add detected language if available
            detected_language = None
            if hasattr(response, 'language'):
                detected_language = response.language
                metadata['detected_language'] = detected_language

            return TranscriptionResult(
                success=True,
                text=transcription_text,
                duration_seconds=duration,
                language=detected_language or language,
                metadata=metadata
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

        ElevenLabs Scribe pricing varies by plan. Check their pricing page.
        This is a placeholder - update based on current pricing.

        Args:
            file_size_mb: File size in megabytes

        Returns:
            Estimated cost in USD (0 for placeholder)
        """
        # ElevenLabs pricing is based on character count for output, not input size
        # Return 0 as we can't estimate without knowing output length
        # Users should check their ElevenLabs plan for actual costs
        return 0.0
