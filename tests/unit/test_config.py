"""
Tests for configuration system.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from whatsapp_chat_autoexport.config import (
    # Settings
    ExportConfig,
    TranscriptionConfig,
    PipelineConfig,
    DeviceConfig,
    TUIConfig,
    get_config,
    load_config,
    # Selectors
    SelectorStrategy,
    SelectorDefinition,
    SelectorRegistry,
    get_selector_registry,
    # Timeouts
    TimeoutProfile,
    TimeoutConfig,
    get_timeout,
)
from whatsapp_chat_autoexport.config.settings import AppConfig, reset_config
from whatsapp_chat_autoexport.config.selectors import (
    ElementSelectors,
    reset_selector_registry,
    create_default_selectors,
)
from whatsapp_chat_autoexport.config.timeouts import (
    get_timeout_config,
    set_timeout_profile,
    reset_timeout_config,
)


class TestDeviceConfig:
    """Tests for DeviceConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DeviceConfig()
        assert config.connection_type == "usb"
        assert config.appium_port == 4723
        assert config.no_reset is True

    def test_wireless_config(self):
        """Test wireless connection configuration."""
        config = DeviceConfig(
            connection_type="wireless",
            wireless_ip="192.168.1.100",
            wireless_port=5555,
        )
        assert config.connection_type == "wireless"
        assert config.wireless_ip == "192.168.1.100"


class TestExportConfig:
    """Tests for ExportConfig."""

    def test_default_values(self):
        """Test default export configuration."""
        config = ExportConfig()
        assert config.include_media is True
        assert config.limit is None
        assert config.max_retries_per_chat == 2

    def test_path_expansion(self):
        """Test that paths are expanded."""
        config = ExportConfig(resume_directory="~/test")
        assert not str(config.resume_directory).startswith("~")

    def test_with_limit(self):
        """Test export with limit."""
        config = ExportConfig(limit=5)
        assert config.limit == 5


class TestTranscriptionConfig:
    """Tests for TranscriptionConfig."""

    def test_default_provider(self):
        """Test default transcription provider."""
        config = TranscriptionConfig()
        assert config.provider == "whisper"
        assert config.skip_existing is True

    def test_elevenlabs_provider(self):
        """Test ElevenLabs configuration."""
        config = TranscriptionConfig(
            provider="elevenlabs",
            api_key="test-key",
        )
        assert config.provider == "elevenlabs"


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_values(self):
        """Test default pipeline configuration."""
        config = PipelineConfig()
        assert config.copy_media is True
        assert config.include_transcriptions is True
        assert config.cleanup_temp_files is True


class TestTUIConfig:
    """Tests for TUIConfig."""

    def test_default_values(self):
        """Test default TUI configuration."""
        config = TUIConfig()
        assert config.show_progress_bar is True
        assert config.pause_key == "space"
        assert config.quit_key == "q"


class TestAppConfig:
    """Tests for AppConfig."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def test_default_config(self):
        """Test default app configuration."""
        config = AppConfig()
        assert config.debug is False
        assert config.dry_run is False
        assert isinstance(config.export, ExportConfig)
        assert isinstance(config.device, DeviceConfig)

    def test_get_config_singleton(self):
        """Test that get_config returns singleton."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_load_config_with_overrides(self):
        """Test loading config with overrides."""
        config = load_config(debug=True, verbose=True)
        assert config.debug is True
        assert config.verbose is True


class TestSelectorStrategy:
    """Tests for SelectorStrategy enum."""

    def test_all_strategies_defined(self):
        """Test all selector strategies exist."""
        assert SelectorStrategy.ID
        assert SelectorStrategy.XPATH
        assert SelectorStrategy.TEXT
        assert SelectorStrategy.TEXT_CONTAINS
        assert SelectorStrategy.CONTENT_DESC
        assert SelectorStrategy.ACCESSIBILITY_ID


class TestSelectorDefinition:
    """Tests for SelectorDefinition."""

    def test_basic_creation(self):
        """Test basic selector definition."""
        selector = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/toolbar",
        )
        assert selector.strategy == SelectorStrategy.ID
        assert selector.priority == 1
        assert selector.timeout == 5.0

    def test_to_appium_locator_id(self):
        """Test conversion to Appium locator for ID strategy."""
        selector = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/toolbar",
        )
        strategy, value = selector.to_appium_locator()
        assert strategy == "id"
        assert value == "com.whatsapp:id/toolbar"

    def test_to_appium_locator_text(self):
        """Test conversion to Appium locator for text strategy."""
        selector = SelectorDefinition(
            strategy=SelectorStrategy.TEXT,
            value="Export chat",
        )
        strategy, value = selector.to_appium_locator()
        assert strategy == "xpath"
        assert "@text='Export chat'" in value

    def test_to_appium_locator_text_contains(self):
        """Test conversion for text_contains strategy."""
        selector = SelectorDefinition(
            strategy=SelectorStrategy.TEXT_CONTAINS,
            value="export",
            case_sensitive=False,
        )
        strategy, value = selector.to_appium_locator()
        assert strategy == "xpath"
        assert "contains(" in value
        assert "translate(" in value  # Case insensitive

    def test_to_appium_locator_content_desc(self):
        """Test conversion for content description strategy."""
        selector = SelectorDefinition(
            strategy=SelectorStrategy.CONTENT_DESC,
            value="More options",
        )
        strategy, value = selector.to_appium_locator()
        assert strategy == "xpath"
        assert "@content-desc='More options'" in value


class TestElementSelectors:
    """Tests for ElementSelectors."""

    def test_basic_creation(self):
        """Test basic element selectors."""
        selectors = ElementSelectors(
            name="menu_button",
            description="Three-dot menu",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/menuitem_overflow",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.CONTENT_DESC,
                    value="More options",
                    priority=2,
                ),
            ],
        )
        assert selectors.name == "menu_button"
        assert len(selectors.strategies) == 2

    def test_get_sorted_strategies(self):
        """Test that strategies are sorted by priority."""
        selectors = ElementSelectors(
            name="test",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.XPATH,
                    value="//test",
                    priority=3,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="test",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="test",
                    priority=2,
                ),
            ],
        )
        sorted_strategies = selectors.get_sorted_strategies()
        assert sorted_strategies[0].priority == 1
        assert sorted_strategies[1].priority == 2
        assert sorted_strategies[2].priority == 3


class TestSelectorRegistry:
    """Tests for SelectorRegistry."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_selector_registry()

    def test_empty_registry(self):
        """Test empty registry."""
        registry = SelectorRegistry()
        assert len(registry.get_all_names()) == 0

    def test_register_simple(self):
        """Test registering a simple selector."""
        registry = SelectorRegistry()
        registry.register_simple(
            "test_element",
            SelectorStrategy.ID,
            "com.test:id/element",
        )
        assert "test_element" in registry.get_all_names()

    def test_register_element_selectors(self):
        """Test registering ElementSelectors."""
        registry = SelectorRegistry()
        selectors = ElementSelectors(
            name="menu_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/menu",
                ),
            ],
        )
        registry.register(selectors)
        assert registry.get("menu_button") is selectors

    def test_get_required_raises(self):
        """Test that get_required raises for missing selector."""
        registry = SelectorRegistry()
        with pytest.raises(KeyError):
            registry.get_required("nonexistent")

    def test_load_from_yaml_file(self):
        """Test loading selectors from YAML file."""
        yaml_content = """
version: "1.0"
app: "com.test.app"
selectors:
  test_button:
    description: "Test button"
    strategies:
      - type: id
        value: "com.test:id/button"
        priority: 1
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)

        try:
            registry = SelectorRegistry()
            registry.load_from_file(path)

            assert registry.version == "1.0"
            assert registry.app_name == "com.test.app"
            assert "test_button" in registry.get_all_names()

            selectors = registry.get("test_button")
            assert selectors.description == "Test button"
            assert len(selectors.strategies) == 1
        finally:
            path.unlink()

    def test_load_from_directory(self):
        """Test loading selectors from directory."""
        # Use the actual selectors directory
        selectors_path = (
            Path(__file__).parent.parent.parent
            / "whatsapp_chat_autoexport"
            / "config"
            / "selectors"
        )
        if selectors_path.exists():
            registry = SelectorRegistry(selectors_path)
            # Should have loaded WhatsApp selectors
            names = registry.get_all_names()
            assert len(names) > 0


class TestDefaultSelectors:
    """Tests for default programmatic selectors."""

    def test_create_default_selectors(self):
        """Test creating default selectors."""
        selectors = create_default_selectors()
        assert "chat_list_item" in selectors
        assert "menu_button" in selectors
        assert "export_chat_option" in selectors

    def test_menu_button_strategies(self):
        """Test menu button has multiple strategies."""
        selectors = create_default_selectors()
        menu_button = selectors["menu_button"]
        assert len(menu_button.strategies) >= 3


class TestTimeoutProfile:
    """Tests for TimeoutProfile enum."""

    def test_all_profiles_defined(self):
        """Test all timeout profiles exist."""
        assert TimeoutProfile.FAST
        assert TimeoutProfile.NORMAL
        assert TimeoutProfile.SLOW
        assert TimeoutProfile.DEBUG


class TestTimeoutConfig:
    """Tests for TimeoutConfig."""

    def setup_method(self):
        """Reset timeout config before each test."""
        reset_timeout_config()

    def test_default_values(self):
        """Test default timeout values."""
        config = TimeoutConfig()
        assert config.element_find_timeout == 5.0
        assert config.step_delay == 0.5

    def test_fast_profile(self):
        """Test fast timeout profile."""
        config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        assert config.element_find_timeout < 5.0
        assert config.step_delay < 0.5

    def test_slow_profile(self):
        """Test slow timeout profile."""
        config = TimeoutConfig.for_profile(TimeoutProfile.SLOW)
        assert config.element_find_timeout > 5.0
        assert config.export_timeout > 120.0

    def test_debug_profile(self):
        """Test debug timeout profile."""
        config = TimeoutConfig.for_profile(TimeoutProfile.DEBUG)
        assert config.element_find_timeout >= 15.0

    def test_scale(self):
        """Test scaling timeouts."""
        config = TimeoutConfig()
        scaled = config.scale(2.0)
        assert scaled.element_find_timeout == 10.0
        assert scaled.step_delay == 1.0

    def test_get_timeout_function(self):
        """Test get_timeout helper function."""
        reset_timeout_config()
        assert get_timeout("element") == 5.0
        assert get_timeout("element_find") == 5.0
        assert get_timeout("step") == 0.5
        assert get_timeout("export") == 120.0

    def test_set_timeout_profile(self):
        """Test setting timeout profile."""
        reset_timeout_config()
        set_timeout_profile(TimeoutProfile.SLOW)
        config = get_timeout_config()
        assert config.element_find_timeout > 5.0


class TestCleanupDriveDuplicatesSetting:
    def test_default_is_true(self):
        """PipelineConfig.cleanup_drive_duplicates defaults to True."""
        config = PipelineConfig()
        assert config.cleanup_drive_duplicates is True

