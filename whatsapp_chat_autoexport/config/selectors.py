"""
Selector management for UI automation.

Provides YAML-based selector definitions with multi-strategy fallback
support and version compatibility checking.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
import yaml


class SelectorStrategy(Enum):
    """Types of selector strategies."""

    ID = "id"  # Android resource ID
    XPATH = "xpath"  # XPath expression
    TEXT = "text"  # Exact text match
    TEXT_CONTAINS = "text_contains"  # Partial text match
    CONTENT_DESC = "content_desc"  # Accessibility content description
    CLASS_NAME = "class_name"  # Android class name
    ACCESSIBILITY_ID = "accessibility_id"  # Appium accessibility ID


@dataclass
class SelectorDefinition:
    """A single selector strategy definition."""

    strategy: SelectorStrategy
    value: str
    priority: int = 1
    timeout: float = 5.0
    wait_visible: bool = True
    case_sensitive: bool = True
    constraints: Dict[str, Any] = field(default_factory=dict)

    def to_appium_locator(self) -> tuple[str, str]:
        """Convert to Appium locator tuple (strategy, value)."""
        strategy_map = {
            SelectorStrategy.ID: "id",
            SelectorStrategy.XPATH: "xpath",
            SelectorStrategy.TEXT: "xpath",
            SelectorStrategy.TEXT_CONTAINS: "xpath",
            SelectorStrategy.CONTENT_DESC: "xpath",
            SelectorStrategy.CLASS_NAME: "class name",
            SelectorStrategy.ACCESSIBILITY_ID: "accessibility id",
        }

        strategy_str = strategy_map.get(self.strategy, "id")

        # Convert text strategies to xpath
        if self.strategy == SelectorStrategy.TEXT:
            if self.case_sensitive:
                value = f"//*[@text='{self.value}']"
            else:
                value = f"//*[translate(@text, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{self.value.lower()}']"
        elif self.strategy == SelectorStrategy.TEXT_CONTAINS:
            if self.case_sensitive:
                value = f"//*[contains(@text, '{self.value}')]"
            else:
                value = f"//*[contains(translate(@text, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{self.value.lower()}')]"
        elif self.strategy == SelectorStrategy.CONTENT_DESC:
            value = f"//*[@content-desc='{self.value}']"
        else:
            value = self.value

        return (strategy_str, value)


@dataclass
class ElementSelectors:
    """Collection of selectors for a single UI element."""

    name: str
    description: str = ""
    strategies: List[SelectorDefinition] = field(default_factory=list)
    fallback_behavior: str = "error"  # "error", "skip", "retry"
    required: bool = True

    def get_sorted_strategies(self) -> List[SelectorDefinition]:
        """Get strategies sorted by priority (lower = higher priority)."""
        return sorted(self.strategies, key=lambda s: s.priority)


class SelectorRegistry:
    """
    Registry for managing UI element selectors.

    Loads selectors from YAML files and provides lookup functionality.
    """

    def __init__(self, selectors_path: Optional[Path] = None):
        self._selectors: Dict[str, ElementSelectors] = {}
        self._version: Optional[str] = None
        self._app_name: Optional[str] = None
        self._loaded_files: List[Path] = []

        if selectors_path:
            self.load_from_directory(selectors_path)

    @property
    def version(self) -> Optional[str]:
        """Get the loaded selector version."""
        return self._version

    @property
    def app_name(self) -> Optional[str]:
        """Get the app name for these selectors."""
        return self._app_name

    def load_from_directory(self, path: Path) -> None:
        """Load all YAML selector files from a directory."""
        if not path.exists():
            return

        for yaml_file in path.glob("*.yaml"):
            self.load_from_file(yaml_file)
        for yml_file in path.glob("*.yml"):
            self.load_from_file(yml_file)

    def load_from_file(self, path: Path) -> None:
        """Load selectors from a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Selector file not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            return

        # Store metadata
        if "version" in data:
            self._version = data["version"]
        if "app" in data:
            self._app_name = data["app"]

        # Load selectors
        selectors_data = data.get("selectors", {})
        for name, selector_data in selectors_data.items():
            self._selectors[name] = self._parse_element_selectors(name, selector_data)

        self._loaded_files.append(path)

    def _parse_element_selectors(
        self, name: str, data: Dict[str, Any]
    ) -> ElementSelectors:
        """Parse selector data into ElementSelectors."""
        strategies = []

        for strategy_data in data.get("strategies", []):
            strategy_type = SelectorStrategy(strategy_data.get("type", "id"))
            strategies.append(
                SelectorDefinition(
                    strategy=strategy_type,
                    value=strategy_data.get("value", ""),
                    priority=strategy_data.get("priority", 1),
                    timeout=strategy_data.get("timeout", 5.0),
                    wait_visible=strategy_data.get("wait_visible", True),
                    case_sensitive=strategy_data.get("case_sensitive", True),
                    constraints=strategy_data.get("constraints", {}),
                )
            )

        return ElementSelectors(
            name=name,
            description=data.get("description", ""),
            strategies=strategies,
            fallback_behavior=data.get("fallback_behavior", "error"),
            required=data.get("required", True),
        )

    def get(self, name: str) -> Optional[ElementSelectors]:
        """Get selectors for an element by name."""
        return self._selectors.get(name)

    def get_required(self, name: str) -> ElementSelectors:
        """Get selectors for an element, raising if not found."""
        selectors = self._selectors.get(name)
        if selectors is None:
            raise KeyError(f"No selectors found for element: {name}")
        return selectors

    def get_all_names(self) -> List[str]:
        """Get all registered element names."""
        return list(self._selectors.keys())

    def register(self, selectors: ElementSelectors) -> None:
        """Register selectors programmatically."""
        self._selectors[selectors.name] = selectors

    def register_simple(
        self,
        name: str,
        strategy: SelectorStrategy,
        value: str,
        **kwargs,
    ) -> None:
        """Register a simple single-strategy selector."""
        self._selectors[name] = ElementSelectors(
            name=name,
            strategies=[SelectorDefinition(strategy=strategy, value=value, **kwargs)],
        )


# Global registry instance
_registry: Optional[SelectorRegistry] = None


def get_selector_registry() -> SelectorRegistry:
    """Get the global selector registry instance."""
    global _registry
    if _registry is None:
        # Load from default location
        default_path = Path(__file__).parent / "selectors"
        _registry = SelectorRegistry(default_path)
    return _registry


def reset_selector_registry() -> None:
    """Reset the global selector registry (mainly for testing)."""
    global _registry
    _registry = None


def create_default_selectors() -> Dict[str, ElementSelectors]:
    """
    Create default WhatsApp selectors.

    This provides a programmatic fallback when YAML files are not available.
    """
    return {
        # Chat list elements
        "chat_list_item": ElementSelectors(
            name="chat_list_item",
            description="Individual chat entry in the main list",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/conversations_row_contact_name",
                    priority=1,
                ),
            ],
        ),
        "toolbar": ElementSelectors(
            name="toolbar",
            description="Main toolbar at top of screen",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/toolbar",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/action_bar",
                    priority=2,
                ),
            ],
        ),
        # Menu elements
        "menu_button": ElementSelectors(
            name="menu_button",
            description="Three-dot menu button",
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
                SelectorDefinition(
                    strategy=SelectorStrategy.ACCESSIBILITY_ID,
                    value="More options",
                    priority=3,
                ),
            ],
        ),
        "more_option": ElementSelectors(
            name="more_option",
            description="'More' option in menu",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="More",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT_CONTAINS,
                    value="more",
                    case_sensitive=False,
                    priority=2,
                ),
            ],
        ),
        "export_chat_option": ElementSelectors(
            name="export_chat_option",
            description="'Export chat' option in menu",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Export chat",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT_CONTAINS,
                    value="export",
                    case_sensitive=False,
                    priority=2,
                ),
            ],
            fallback_behavior="skip",
        ),
        # Media selection
        "include_media_button": ElementSelectors(
            name="include_media_button",
            description="'Include media' button in export dialog",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Include media",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT_CONTAINS,
                    value="include",
                    case_sensitive=False,
                    priority=2,
                ),
            ],
        ),
        "without_media_button": ElementSelectors(
            name="without_media_button",
            description="'Without media' button in export dialog",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Without media",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT_CONTAINS,
                    value="without",
                    case_sensitive=False,
                    priority=2,
                ),
            ],
        ),
        # Google Drive
        "google_drive_option": ElementSelectors(
            name="google_drive_option",
            description="Google Drive option in share sheet",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Drive",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT_CONTAINS,
                    value="drive",
                    case_sensitive=False,
                    priority=2,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.CONTENT_DESC,
                    value="Save to Drive",
                    priority=3,
                ),
            ],
        ),
        "my_drive_folder": ElementSelectors(
            name="my_drive_folder",
            description="'My Drive' folder in Drive picker",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="My Drive",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Drive",
                    priority=2,
                ),
            ],
        ),
        "upload_button": ElementSelectors(
            name="upload_button",
            description="Upload/Save button in Drive picker",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.TEXT,
                    value="Save",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.CONTENT_DESC,
                    value="Save",
                    priority=2,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.google.android.apps.docs:id/save_button",
                    priority=3,
                ),
            ],
        ),
    }
