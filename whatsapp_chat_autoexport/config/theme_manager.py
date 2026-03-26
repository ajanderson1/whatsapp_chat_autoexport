"""
Theme persistence manager for the WhatsApp Exporter TUI.

Handles saving and loading theme preferences to disk at:
~/.config/whatsapp-exporter/ui.json
"""

import json
from pathlib import Path
from typing import Optional

from .themes import DEFAULT_THEME, get_all_theme_names


# =============================================================================
# Configuration
# =============================================================================

CONFIG_DIR = Path.home() / ".config" / "whatsapp-exporter"
UI_CONFIG_FILE = CONFIG_DIR / "ui.json"


# =============================================================================
# Theme Manager Class
# =============================================================================

class ThemeManager:
    """
    Manages theme persistence to disk.

    Saves user's theme preference to ~/.config/whatsapp-exporter/ui.json
    and retrieves it on startup.
    """

    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize the theme manager.

        Args:
            config_file: Path to config file. Defaults to standard location.
        """
        self._config_file = config_file or UI_CONFIG_FILE

    @property
    def config_file(self) -> Path:
        """Get the path to the config file."""
        return self._config_file

    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> dict:
        """Load the config file contents."""
        if not self._config_file.exists():
            return {}

        try:
            with open(self._config_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_config(self, config: dict) -> bool:
        """
        Save config to disk.

        Args:
            config: Configuration dictionary to save

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_config_dir()
            with open(self._config_file, "w") as f:
                json.dump(config, f, indent=2)
            return True
        except IOError:
            return False

    def get_saved_theme(self) -> str:
        """
        Get the saved theme name.

        Returns:
            Theme name if saved and valid, otherwise the default theme.
        """
        config = self._load_config()
        theme_name = config.get("theme", DEFAULT_THEME)

        # Validate theme name
        valid_themes = get_all_theme_names()
        if theme_name in valid_themes:
            return theme_name

        return DEFAULT_THEME

    def save_theme(self, theme_name: str) -> bool:
        """
        Save the theme preference to disk.

        Args:
            theme_name: Name of the theme to save

        Returns:
            True if successful, False otherwise
        """
        # Validate theme name
        valid_themes = get_all_theme_names()
        if theme_name not in valid_themes:
            return False

        # Load existing config and update
        config = self._load_config()
        config["theme"] = theme_name

        return self._save_config(config)

    def reset_theme(self) -> bool:
        """
        Reset theme to default.

        Returns:
            True if successful, False otherwise
        """
        return self.save_theme(DEFAULT_THEME)


# =============================================================================
# Singleton instance for convenience
# =============================================================================

_theme_manager: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def reset_theme_manager() -> None:
    """Reset the global theme manager (mainly for testing)."""
    global _theme_manager
    _theme_manager = None
