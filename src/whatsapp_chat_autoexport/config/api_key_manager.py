"""
API Key Manager for transcription services.

Handles reading, writing, and validating API keys from environment
variables and .env files. Provides safe key display with masking.
"""

import os
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from dotenv import load_dotenv, set_key, dotenv_values


class ApiKeyManager:
    """
    Manages API keys for transcription providers.

    Supports reading from environment variables and .env files,
    writing to .env files, and validating keys via TranscriberFactory.
    """

    # Mapping of provider names to their environment variable names
    ENV_VAR_MAP: Dict[str, str] = {
        "whisper": "OPENAI_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
    }

    # Provider display names
    PROVIDER_NAMES: Dict[str, str] = {
        "whisper": "OpenAI (Whisper)",
        "elevenlabs": "ElevenLabs",
    }

    def __init__(self, env_file: Optional[Path] = None):
        """
        Initialize the API Key Manager.

        Args:
            env_file: Path to .env file. Defaults to .env in current directory
                     or project root.
        """
        self._env_file = env_file or self._find_env_file()
        # Load .env file values (doesn't override existing env vars)
        if self._env_file and self._env_file.exists():
            load_dotenv(self._env_file)

    def _find_env_file(self) -> Path:
        """
        Find the .env file location.

        Searches in order:
        1. Current working directory
        2. Project root (parent of whatsapp_chat_autoexport package)

        Returns:
            Path to .env file (may not exist yet)
        """
        # Try current directory
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists():
            return cwd_env

        # Try project root (go up from this file's location)
        project_root = Path(__file__).parent.parent.parent
        project_env = project_root / ".env"

        # Return project root .env as default location
        return project_env

    @property
    def env_file_path(self) -> Path:
        """Get the path to the .env file being used."""
        return self._env_file

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get the API key for a provider.

        Checks environment variables first, then .env file.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            API key if found, None otherwise
        """
        provider_lower = provider.lower()
        if provider_lower not in self.ENV_VAR_MAP:
            return None

        env_var = self.ENV_VAR_MAP[provider_lower]

        # First check current environment
        key = os.environ.get(env_var)
        if key:
            return key

        # Fall back to .env file
        if self._env_file and self._env_file.exists():
            env_values = dotenv_values(self._env_file)
            return env_values.get(env_var)

        return None

    def set_api_key(self, provider: str, api_key: str) -> bool:
        """
        Set the API key for a provider.

        Writes to .env file and updates current environment.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')
            api_key: The API key to set

        Returns:
            True if successful, False otherwise
        """
        provider_lower = provider.lower()
        if provider_lower not in self.ENV_VAR_MAP:
            return False

        env_var = self.ENV_VAR_MAP[provider_lower]

        try:
            # Ensure .env file exists
            if not self._env_file.exists():
                self._env_file.parent.mkdir(parents=True, exist_ok=True)
                self._env_file.touch()

            # Write to .env file
            set_key(str(self._env_file), env_var, api_key)

            # Update current environment
            os.environ[env_var] = api_key

            return True
        except Exception:
            return False

    def remove_api_key(self, provider: str) -> bool:
        """
        Remove the API key for a provider from .env file.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            True if successful, False otherwise
        """
        provider_lower = provider.lower()
        if provider_lower not in self.ENV_VAR_MAP:
            return False

        env_var = self.ENV_VAR_MAP[provider_lower]

        try:
            # Remove from environment
            if env_var in os.environ:
                del os.environ[env_var]

            # Remove from .env file by setting empty value
            if self._env_file and self._env_file.exists():
                set_key(str(self._env_file), env_var, "")

            return True
        except Exception:
            return False

    def validate_api_key(self, provider: str, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate an API key for a provider.

        Uses TranscriberFactory to verify the key works.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')
            api_key: API key to validate. If None, uses stored key.

        Returns:
            Tuple of (is_valid, error_message)
        """
        from ..transcription.transcriber_factory import TranscriberFactory

        provider_lower = provider.lower()

        # Get key if not provided
        if api_key is None:
            api_key = self.get_api_key(provider)

        if not api_key:
            return False, "No API key configured"

        # Use TranscriberFactory's validation
        return TranscriberFactory.validate_provider(provider_lower, api_key)

    def get_key_status(self, provider: str) -> str:
        """
        Get a human-readable status for a provider's API key.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            Status string: "Valid", "Invalid", or "Not configured"
        """
        key = self.get_api_key(provider)
        if not key:
            return "Not configured"

        is_valid, _ = self.validate_api_key(provider, key)
        return "Valid" if is_valid else "Invalid"

    def get_available_providers(self) -> List[str]:
        """
        Get list of providers with valid API keys configured.

        Returns:
            List of provider names with valid keys
        """
        available = []
        for provider in self.ENV_VAR_MAP.keys():
            is_valid, _ = self.validate_api_key(provider)
            if is_valid:
                available.append(provider)
        return available

    def get_all_providers(self) -> List[str]:
        """
        Get list of all supported providers.

        Returns:
            List of all provider names
        """
        return list(self.ENV_VAR_MAP.keys())

    @staticmethod
    def mask_api_key(api_key: Optional[str], visible_chars: int = 4) -> str:
        """
        Mask an API key for safe display.

        Shows first few characters and last few characters with dots in between.

        Args:
            api_key: The API key to mask
            visible_chars: Number of characters to show at start and end

        Returns:
            Masked string like "sk-...xxxx" or empty string if no key

        Examples:
            >>> ApiKeyManager.mask_api_key("sk-proj-abc123xyz")
            'sk-p...xyz'
            >>> ApiKeyManager.mask_api_key(None)
            ''
        """
        if not api_key:
            return ""

        if len(api_key) <= visible_chars * 2:
            return "*" * len(api_key)

        return f"{api_key[:visible_chars]}...{api_key[-visible_chars:]}"

    def get_provider_display_name(self, provider: str) -> str:
        """
        Get the display name for a provider.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            Human-readable provider name
        """
        return self.PROVIDER_NAMES.get(provider.lower(), provider.title())

    def get_env_var_name(self, provider: str) -> str:
        """
        Get the environment variable name for a provider.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            Environment variable name (e.g., 'OPENAI_API_KEY')
        """
        return self.ENV_VAR_MAP.get(provider.lower(), "")

    def get_provider_info(self, provider: str) -> Dict:
        """
        Get complete information about a provider's configuration.

        Args:
            provider: Provider name ('whisper' or 'elevenlabs')

        Returns:
            Dictionary with provider configuration details
        """
        provider_lower = provider.lower()
        key = self.get_api_key(provider)
        is_valid = False
        error_msg = ""

        if key:
            is_valid, error_msg = self.validate_api_key(provider, key)

        return {
            "name": provider_lower,
            "display_name": self.get_provider_display_name(provider),
            "env_var": self.get_env_var_name(provider),
            "has_key": key is not None,
            "masked_key": self.mask_api_key(key),
            "is_valid": is_valid,
            "status": self.get_key_status(provider),
            "error": error_msg if not is_valid and key else "",
        }


# Singleton instance for convenience
_api_key_manager: Optional[ApiKeyManager] = None


def get_api_key_manager() -> ApiKeyManager:
    """Get the global API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = ApiKeyManager()
    return _api_key_manager


def reset_api_key_manager() -> None:
    """Reset the global API key manager (mainly for testing)."""
    global _api_key_manager
    _api_key_manager = None
