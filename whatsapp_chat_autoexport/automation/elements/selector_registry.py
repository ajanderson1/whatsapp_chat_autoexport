"""
Runtime selector registry for automation.

Combines static YAML-defined selectors with runtime-discovered
selectors for flexible element finding.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from pathlib import Path

from ...config.selectors import (
    SelectorRegistry,
    ElementSelectors,
    SelectorDefinition,
    SelectorStrategy,
    create_default_selectors,
)
from ...core.result import Result, Ok, Err
from ...core.errors import ElementNotFoundError


@dataclass
class DiscoveredSelector:
    """A selector discovered at runtime."""

    element_name: str
    strategy: SelectorDefinition
    discovered_on_screen: str
    discovery_time: float


class RuntimeSelectorRegistry:
    """
    Enhanced selector registry with runtime discovery.

    Extends the base SelectorRegistry with:
    - Runtime selector discovery and learning
    - Screen-specific selector overrides
    - Selector versioning and compatibility
    """

    def __init__(
        self,
        base_registry: Optional[SelectorRegistry] = None,
        enable_discovery: bool = True,
    ):
        """
        Initialize the runtime registry.

        Args:
            base_registry: Optional base registry with YAML selectors
            enable_discovery: Whether to enable runtime discovery
        """
        self._base_registry = base_registry or SelectorRegistry()
        self._enable_discovery = enable_discovery

        # Screen-specific overrides: {screen_name: {element_name: ElementSelectors}}
        self._screen_overrides: Dict[str, Dict[str, ElementSelectors]] = {}

        # Runtime discovered selectors
        self._discovered: Dict[str, DiscoveredSelector] = {}

        # Default selectors as fallback
        self._defaults = create_default_selectors()

    def get(
        self,
        element_name: str,
        screen: Optional[str] = None,
    ) -> Optional[ElementSelectors]:
        """
        Get selectors for an element.

        Checks in order:
        1. Screen-specific overrides
        2. Discovered runtime selectors
        3. Base registry (YAML)
        4. Default programmatic selectors

        Args:
            element_name: Name of the element
            screen: Optional current screen name for overrides

        Returns:
            ElementSelectors or None
        """
        # 1. Check screen-specific overrides
        if screen and screen in self._screen_overrides:
            screen_selectors = self._screen_overrides[screen].get(element_name)
            if screen_selectors:
                return screen_selectors

        # 2. Check discovered selectors
        discovered = self._discovered.get(element_name)
        if discovered:
            return ElementSelectors(
                name=element_name,
                strategies=[discovered.strategy],
            )

        # 3. Check base registry
        base_selectors = self._base_registry.get(element_name)
        if base_selectors:
            return base_selectors

        # 4. Check defaults
        return self._defaults.get(element_name)

    def get_required(
        self,
        element_name: str,
        screen: Optional[str] = None,
    ) -> ElementSelectors:
        """
        Get selectors, raising if not found.

        Args:
            element_name: Name of the element
            screen: Optional current screen name

        Returns:
            ElementSelectors

        Raises:
            KeyError: If no selectors found
        """
        selectors = self.get(element_name, screen)
        if selectors is None:
            raise KeyError(
                f"No selectors found for element: {element_name}"
                + (f" on screen: {screen}" if screen else "")
            )
        return selectors

    def register_screen_override(
        self,
        screen: str,
        element_name: str,
        selectors: ElementSelectors,
    ) -> None:
        """
        Register screen-specific selectors.

        Args:
            screen: Screen name
            element_name: Element name
            selectors: Selectors to use on this screen
        """
        if screen not in self._screen_overrides:
            self._screen_overrides[screen] = {}
        self._screen_overrides[screen][element_name] = selectors

    def record_discovery(
        self,
        element_name: str,
        strategy: SelectorDefinition,
        screen: str,
        duration: float,
    ) -> None:
        """
        Record a runtime-discovered selector.

        Called when an element is found using a strategy that wasn't
        in the original configuration.

        Args:
            element_name: Name of the element
            strategy: Strategy that found the element
            screen: Screen where discovered
            duration: Time taken to discover
        """
        if not self._enable_discovery:
            return

        self._discovered[element_name] = DiscoveredSelector(
            element_name=element_name,
            strategy=strategy,
            discovered_on_screen=screen,
            discovery_time=duration,
        )

    def get_all_element_names(self) -> List[str]:
        """Get all known element names."""
        names = set()

        # From base registry
        names.update(self._base_registry.get_all_names())

        # From defaults
        names.update(self._defaults.keys())

        # From screen overrides
        for screen_selectors in self._screen_overrides.values():
            names.update(screen_selectors.keys())

        # From discovered
        names.update(self._discovered.keys())

        return sorted(names)

    def get_discovery_stats(self) -> Dict[str, Any]:
        """Get statistics about discovered selectors."""
        return {
            "total_discovered": len(self._discovered),
            "discoveries_by_screen": self._count_by_screen(),
            "discovery_enabled": self._enable_discovery,
        }

    def _count_by_screen(self) -> Dict[str, int]:
        """Count discoveries by screen."""
        counts: Dict[str, int] = {}
        for discovery in self._discovered.values():
            screen = discovery.discovered_on_screen
            counts[screen] = counts.get(screen, 0) + 1
        return counts

    def export_discoveries(self) -> Dict[str, Any]:
        """
        Export discovered selectors for persistence.

        Returns a dictionary suitable for saving to YAML/JSON.
        """
        result = {}
        for name, discovery in self._discovered.items():
            result[name] = {
                "type": discovery.strategy.strategy.value,
                "value": discovery.strategy.value,
                "priority": discovery.strategy.priority,
                "discovered_on": discovery.discovered_on_screen,
            }
        return result

    def import_discoveries(self, data: Dict[str, Any]) -> None:
        """
        Import previously discovered selectors.

        Args:
            data: Dictionary from export_discoveries
        """
        for name, selector_data in data.items():
            strategy = SelectorDefinition(
                strategy=SelectorStrategy(selector_data["type"]),
                value=selector_data["value"],
                priority=selector_data.get("priority", 1),
            )
            self._discovered[name] = DiscoveredSelector(
                element_name=name,
                strategy=strategy,
                discovered_on_screen=selector_data.get("discovered_on", "unknown"),
                discovery_time=0.0,
            )

    def clear_discoveries(self) -> None:
        """Clear all runtime discoveries."""
        self._discovered.clear()
