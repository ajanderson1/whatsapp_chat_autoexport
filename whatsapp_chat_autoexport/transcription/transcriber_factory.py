"""
Factory for creating transcription service instances.

Provides a centralized way to create transcriber instances based on provider name.
"""

import os
from pathlib import Path
from typing import Optional, Tuple

from .base_transcriber import BaseTranscriber
from .whisper_transcriber import WhisperTranscriber
from .elevenlabs_transcriber import ElevenLabsTranscriber


class TranscriberFactory:
    """
    Factory for creating transcription service instances.

    Supports multiple providers:
    - 'whisper': OpenAI Whisper API
    - 'elevenlabs': ElevenLabs Scribe API
    """

    SUPPORTED_PROVIDERS = ['whisper', 'elevenlabs']

    @staticmethod
    def create_transcriber(
        provider: str,
        api_key: Optional[str] = None,
        logger=None,
        convert_opus: bool = True,
        video_test_mode: bool = False,
        **provider_kwargs
    ) -> BaseTranscriber:
        """
        Create a transcriber instance for the specified provider.

        Args:
            provider: Transcription provider name ('whisper' or 'elevenlabs')
            api_key: Optional API key (if None, uses environment variable)
            logger: Optional logger instance
            convert_opus: Whether to convert Opus files to M4A (default: True)
            video_test_mode: Debug mode for video transcription (keeps temp files)
            **provider_kwargs: Additional provider-specific arguments

        Returns:
            BaseTranscriber instance

        Raises:
            ValueError: If provider is not supported

        Examples:
            # Create Whisper transcriber
            transcriber = TranscriberFactory.create_transcriber(
                'whisper',
                logger=logger,
                model='whisper-1'
            )

            # Create ElevenLabs transcriber
            transcriber = TranscriberFactory.create_transcriber(
                'elevenlabs',
                logger=logger,
                diarize=True
            )
        """
        provider_lower = provider.lower()

        if provider_lower not in TranscriberFactory.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported transcription provider: {provider}. "
                f"Supported providers: {', '.join(TranscriberFactory.SUPPORTED_PROVIDERS)}"
            )

        if provider_lower == 'whisper':
            return WhisperTranscriber(
                api_key=api_key,
                logger=logger,
                convert_opus=convert_opus,
                **provider_kwargs
            )

        elif provider_lower == 'elevenlabs':
            return ElevenLabsTranscriber(
                api_key=api_key,
                logger=logger,
                convert_opus=convert_opus,
                **provider_kwargs
            )

        # This should never be reached due to the validation above
        raise ValueError(f"Provider '{provider}' not implemented")

    @staticmethod
    def get_supported_providers() -> list[str]:
        """
        Get list of supported transcription providers.

        Returns:
            List of provider names
        """
        return TranscriberFactory.SUPPORTED_PROVIDERS.copy()

    @staticmethod
    def is_provider_available(provider: str, api_key: Optional[str] = None) -> bool:
        """
        Check if a transcription provider is available.

        Args:
            provider: Provider name to check
            api_key: Optional API key to test

        Returns:
            True if provider is available and can be initialized
        """
        if provider.lower() not in TranscriberFactory.SUPPORTED_PROVIDERS:
            return False

        try:
            transcriber = TranscriberFactory.create_transcriber(
                provider,
                api_key=api_key,
                logger=None
            )
            return transcriber.is_available()
        except Exception:
            return False

    @staticmethod
    def validate_provider(provider: str, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate that a transcription provider is properly configured.

        Checks:
        1. Provider is supported
        2. Required API key environment variable is set
        3. Provider can be initialized successfully

        Args:
            provider: Provider name to validate
            api_key: Optional API key to test (if None, uses environment variable)

        Returns:
            Tuple of (success: bool, error_message: str)
            - If success=True, error_message will be empty
            - If success=False, error_message contains helpful error description

        Examples:
            success, error = TranscriberFactory.validate_provider('whisper')
            if not success:
                print(f"Validation failed: {error}")
        """
        provider_lower = provider.lower()

        # Check 1: Provider must be supported
        if provider_lower not in TranscriberFactory.SUPPORTED_PROVIDERS:
            return False, (
                f"Unsupported transcription provider: '{provider}'. "
                f"Supported providers: {', '.join(TranscriberFactory.SUPPORTED_PROVIDERS)}"
            )

        # Determine which environment variable to check
        env_var_map = {
            'whisper': 'OPENAI_API_KEY',
            'elevenlabs': 'ELEVENLABS_API_KEY'
        }
        required_env_var = env_var_map[provider_lower]

        # Check 2: If no API key provided, check environment variable is set
        if api_key is None:
            api_key = os.environ.get(required_env_var)
            if not api_key:
                return False, (
                    f"API key for {provider} not found. "
                    f"Please set the {required_env_var} environment variable:\n"
                    f"  export {required_env_var}='your-api-key-here'"
                )

        # Check 3: Try to initialize the provider
        try:
            transcriber = TranscriberFactory.create_transcriber(
                provider,
                api_key=api_key,
                logger=None
            )

            if not transcriber.is_available():
                return False, (
                    f"{provider} transcriber initialization failed. "
                    f"Please check your {required_env_var} is valid."
                )

            return True, ""

        except Exception as e:
            return False, (
                f"Failed to initialize {provider} transcriber: {str(e)}"
            )

    @staticmethod
    def get_default_provider() -> str:
        """
        Get the default transcription provider.

        Returns:
            Default provider name ('whisper')
        """
        return 'whisper'
