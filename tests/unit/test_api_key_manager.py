"""Unit tests for ApiKeyManager."""

import os
import tempfile
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.config.api_key_manager import (
    ApiKeyManager,
    get_api_key_manager,
    reset_api_key_manager,
)


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("# Test .env file\n")
        f.write("OPENAI_API_KEY=test-openai-key-123\n")
        f.write("ELEVENLABS_API_KEY=\n")  # Empty value
        env_path = Path(f.name)
    yield env_path
    # Cleanup
    try:
        env_path.unlink()
    except Exception:
        pass


@pytest.fixture
def manager(temp_env_file):
    """Create an ApiKeyManager with temp .env file."""
    return ApiKeyManager(env_file=temp_env_file)


class TestApiKeyManager:
    """Tests for ApiKeyManager class."""

    def test_get_api_key_from_env_file(self, manager):
        """Test reading API key from .env file."""
        # Clear environment to ensure we read from file
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            key = manager.get_api_key("whisper")
            assert key == "test-openai-key-123"
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key

    def test_get_api_key_from_environment(self, manager):
        """Test that environment variable takes precedence."""
        os.environ["OPENAI_API_KEY"] = "env-key-overrides"
        try:
            key = manager.get_api_key("whisper")
            assert key == "env-key-overrides"
        finally:
            del os.environ["OPENAI_API_KEY"]

    def test_get_api_key_unknown_provider(self, manager):
        """Test that unknown provider returns None."""
        key = manager.get_api_key("unknown_provider")
        assert key is None

    def test_mask_api_key(self):
        """Test API key masking."""
        # Normal key - shows first 4 and last 4 characters
        assert ApiKeyManager.mask_api_key("sk-proj-abc123xyz456") == "sk-p...z456"

        # Short key
        assert ApiKeyManager.mask_api_key("short") == "*****"

        # Empty/None
        assert ApiKeyManager.mask_api_key("") == ""
        assert ApiKeyManager.mask_api_key(None) == ""

    def test_env_var_mapping(self, manager):
        """Test environment variable mapping."""
        assert manager.get_env_var_name("whisper") == "OPENAI_API_KEY"
        assert manager.get_env_var_name("elevenlabs") == "ELEVENLABS_API_KEY"
        assert manager.get_env_var_name("unknown") == ""

    def test_provider_display_names(self, manager):
        """Test provider display name mapping."""
        assert manager.get_provider_display_name("whisper") == "OpenAI (Whisper)"
        assert manager.get_provider_display_name("elevenlabs") == "ElevenLabs"

    def test_get_all_providers(self, manager):
        """Test getting all providers."""
        providers = manager.get_all_providers()
        assert "whisper" in providers
        assert "elevenlabs" in providers

    def test_set_api_key(self, temp_env_file):
        """Test setting API key."""
        manager = ApiKeyManager(env_file=temp_env_file)

        # Set a new key
        success = manager.set_api_key("elevenlabs", "new-elevenlabs-key")
        assert success is True

        # Verify it's in the environment
        assert os.environ.get("ELEVENLABS_API_KEY") == "new-elevenlabs-key"

        # Verify it can be retrieved
        key = manager.get_api_key("elevenlabs")
        assert key == "new-elevenlabs-key"

        # Cleanup
        del os.environ["ELEVENLABS_API_KEY"]

    def test_get_key_status_not_configured(self, manager):
        """Test key status when not configured."""
        # Clear any existing key
        old_key = os.environ.pop("ELEVENLABS_API_KEY", None)
        try:
            # Create new manager to reload state
            manager2 = ApiKeyManager(env_file=manager.env_file_path)
            status = manager2.get_key_status("elevenlabs")
            assert status == "Not configured"
        finally:
            if old_key:
                os.environ["ELEVENLABS_API_KEY"] = old_key

    def test_provider_info(self, manager):
        """Test getting complete provider info."""
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            info = manager.get_provider_info("whisper")
            assert info["name"] == "whisper"
            assert info["display_name"] == "OpenAI (Whisper)"
            assert info["env_var"] == "OPENAI_API_KEY"
            assert info["has_key"] is True
            assert "masked_key" in info
            assert "status" in info
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_get_api_key_manager_returns_singleton(self):
        """Test that get_api_key_manager returns same instance."""
        reset_api_key_manager()
        manager1 = get_api_key_manager()
        manager2 = get_api_key_manager()
        assert manager1 is manager2

    def test_reset_clears_singleton(self):
        """Test that reset_api_key_manager clears the singleton."""
        manager1 = get_api_key_manager()
        reset_api_key_manager()
        manager2 = get_api_key_manager()
        assert manager1 is not manager2
