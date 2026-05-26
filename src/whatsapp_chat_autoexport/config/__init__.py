"""
Configuration system for WhatsApp Chat Auto-Export.

Provides centralized configuration management including:
- Application settings via Pydantic models
- YAML-based selector definitions
- Timing profiles for automation
- API key management for transcription services
- Theme management for TUI color schemes
"""

from .settings import (
    ExportConfig,
    TranscriptionConfig,
    PipelineConfig,
    DeviceConfig,
    TUIConfig,
    get_config,
    load_config,
)
from .selectors import (
    SelectorStrategy,
    SelectorDefinition,
    SelectorRegistry,
    get_selector_registry,
)
from .timeouts import (
    TimeoutProfile,
    TimeoutConfig,
    get_timeout,
)
from .api_key_manager import (
    ApiKeyManager,
    get_api_key_manager,
    reset_api_key_manager,
)
from .themes import (
    ALL_THEMES,
    DEFAULT_THEME,
    THEME_DISPLAY_NAMES,
    get_theme_by_name,
    get_theme_display_name,
    get_all_theme_names,
)
from .theme_manager import (
    ThemeManager,
    get_theme_manager,
    reset_theme_manager,
)

__all__ = [
    # Settings
    "ExportConfig",
    "TranscriptionConfig",
    "PipelineConfig",
    "DeviceConfig",
    "TUIConfig",
    "get_config",
    "load_config",
    # Selectors
    "SelectorStrategy",
    "SelectorDefinition",
    "SelectorRegistry",
    "get_selector_registry",
    # Timeouts
    "TimeoutProfile",
    "TimeoutConfig",
    "get_timeout",
    # API Keys
    "ApiKeyManager",
    "get_api_key_manager",
    "reset_api_key_manager",
    # Themes
    "ALL_THEMES",
    "DEFAULT_THEME",
    "THEME_DISPLAY_NAMES",
    "get_theme_by_name",
    "get_theme_display_name",
    "get_all_theme_names",
    "ThemeManager",
    "get_theme_manager",
    "reset_theme_manager",
]
