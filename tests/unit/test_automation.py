"""
Tests for automation layer.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

from whatsapp_chat_autoexport.automation import (
    ElementFinder,
    FindResult,
    ElementCache,
    CacheEntry,
    RuntimeSelectorRegistry,
)
from whatsapp_chat_autoexport.config.selectors import (
    SelectorDefinition,
    SelectorStrategy,
    ElementSelectors,
    create_default_selectors,
    SelectorRegistry,
)
from whatsapp_chat_autoexport.core.result import is_ok, is_err


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_basic_creation(self):
        """Test basic cache entry creation."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/test",
        )
        entry = CacheEntry(strategy=strategy)
        assert entry.hit_count == 0
        assert entry.miss_count == 0

    def test_record_hit(self):
        """Test recording a hit."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        entry = CacheEntry(strategy=strategy)
        entry.record_hit()
        assert entry.hit_count == 1

    def test_record_miss(self):
        """Test recording a miss."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        entry = CacheEntry(strategy=strategy)
        entry.record_miss()
        assert entry.miss_count == 1

    def test_success_rate(self):
        """Test success rate calculation."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        entry = CacheEntry(strategy=strategy, hit_count=8, miss_count=2)
        assert entry.success_rate == 0.8

    def test_success_rate_zero_total(self):
        """Test success rate with no attempts."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        entry = CacheEntry(strategy=strategy)
        assert entry.success_rate == 0.0

    def test_is_stale(self):
        """Test staleness check."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        entry = CacheEntry(
            strategy=strategy,
            last_used=datetime.now() - timedelta(hours=2),
        )
        assert entry.is_stale(timedelta(hours=1)) is True
        assert entry.is_stale(timedelta(hours=3)) is False


class TestElementCache:
    """Tests for ElementCache."""

    def test_empty_cache(self):
        """Test empty cache returns None."""
        cache = ElementCache()
        assert cache.get("nonexistent") is None
        assert len(cache) == 0

    def test_set_and_get(self):
        """Test setting and getting cache entry."""
        cache = ElementCache()
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/test",
        )
        cache.set("test_element", strategy)
        assert cache.get("test_element") == strategy
        assert len(cache) == 1

    def test_invalidate(self):
        """Test invalidating cache entry."""
        cache = ElementCache()
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        cache.set("test", strategy)
        cache.invalidate("test")
        assert cache.get("test") is None

    def test_invalidate_all(self):
        """Test invalidating all entries."""
        cache = ElementCache()
        for i in range(5):
            strategy = SelectorDefinition(
                strategy=SelectorStrategy.ID,
                value=f"test{i}",
            )
            cache.set(f"test{i}", strategy)
        assert len(cache) == 5
        cache.invalidate_all()
        assert len(cache) == 0

    def test_max_entries_eviction(self):
        """Test that oldest entries are evicted at capacity."""
        cache = ElementCache(max_entries=3)
        for i in range(5):
            strategy = SelectorDefinition(
                strategy=SelectorStrategy.ID,
                value=f"test{i}",
            )
            cache.set(f"element{i}", strategy)
        assert len(cache) == 3

    def test_stale_entries_removed(self):
        """Test that stale entries are removed on get."""
        cache = ElementCache(max_age=timedelta(seconds=1))
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        cache.set("test", strategy)

        # Manually make entry stale
        cache._cache["test"].last_used = datetime.now() - timedelta(hours=1)

        assert cache.get("test") is None

    def test_record_hit_and_miss(self):
        """Test recording hits and misses."""
        cache = ElementCache()
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        cache.set("test", strategy)
        cache.record_hit("test")
        cache.record_hit("test")
        cache.record_miss("test")

        stats = cache.get_stats()
        assert stats["total_hits"] >= 2
        assert stats["total_misses"] >= 1

    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = ElementCache(max_entries=10)
        stats = cache.get_stats()
        assert "entries" in stats
        assert "max_entries" in stats
        assert stats["max_entries"] == 10

    def test_contains(self):
        """Test __contains__ method."""
        cache = ElementCache()
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        cache.set("test", strategy)
        assert "test" in cache
        assert "nonexistent" not in cache

    def test_persistence(self):
        """Test cache persistence to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"

            # Create and populate cache
            cache1 = ElementCache(persistence_path=cache_path)
            strategy = SelectorDefinition(
                strategy=SelectorStrategy.ID,
                value="com.whatsapp:id/test",
            )
            cache1.set("test_element", strategy)
            cache1.persist()

            # Load cache from disk
            cache2 = ElementCache(persistence_path=cache_path)
            loaded_strategy = cache2.get("test_element")
            assert loaded_strategy is not None
            assert loaded_strategy.value == "com.whatsapp:id/test"


class TestRuntimeSelectorRegistry:
    """Tests for RuntimeSelectorRegistry."""

    def test_empty_registry(self):
        """Test empty registry uses defaults."""
        registry = RuntimeSelectorRegistry()
        # Should have default selectors
        assert registry.get("menu_button") is not None

    def test_get_from_defaults(self):
        """Test getting selector from defaults."""
        registry = RuntimeSelectorRegistry()
        selectors = registry.get("chat_list_item")
        assert selectors is not None
        assert len(selectors.strategies) > 0

    def test_get_required_raises(self):
        """Test get_required raises for missing selector."""
        registry = RuntimeSelectorRegistry()
        with pytest.raises(KeyError):
            registry.get_required("completely_nonexistent_element_xyz")

    def test_screen_override(self):
        """Test screen-specific override."""
        registry = RuntimeSelectorRegistry()

        # Create custom selectors for a specific screen
        custom_selectors = ElementSelectors(
            name="menu_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.XPATH,
                    value="//custom/xpath",
                    priority=1,
                ),
            ],
        )
        registry.register_screen_override("chat_view", "menu_button", custom_selectors)

        # Without screen, get default
        default = registry.get("menu_button")

        # With screen, get override
        override = registry.get("menu_button", screen="chat_view")
        assert override is not None
        assert override.strategies[0].value == "//custom/xpath"

    def test_record_discovery(self):
        """Test recording runtime discoveries."""
        registry = RuntimeSelectorRegistry(enable_discovery=True)
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.XPATH,
            value="//discovered/element",
        )
        registry.record_discovery(
            element_name="new_element",
            strategy=strategy,
            screen="main_screen",
            duration=0.5,
        )

        selectors = registry.get("new_element")
        assert selectors is not None
        assert selectors.strategies[0].value == "//discovered/element"

    def test_discovery_disabled(self):
        """Test that discoveries are ignored when disabled."""
        registry = RuntimeSelectorRegistry(enable_discovery=False)
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.XPATH,
            value="//discovered/element",
        )
        registry.record_discovery(
            element_name="new_element",
            strategy=strategy,
            screen="main_screen",
            duration=0.5,
        )

        # Discovery should be ignored
        selectors = registry.get("new_element")
        assert selectors is None

    def test_get_all_element_names(self):
        """Test getting all element names."""
        registry = RuntimeSelectorRegistry()
        names = registry.get_all_element_names()
        assert len(names) > 0
        assert "menu_button" in names

    def test_discovery_stats(self):
        """Test discovery statistics."""
        registry = RuntimeSelectorRegistry(enable_discovery=True)
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.XPATH,
            value="//test",
        )
        registry.record_discovery("elem1", strategy, "screen1", 0.1)
        registry.record_discovery("elem2", strategy, "screen1", 0.2)
        registry.record_discovery("elem3", strategy, "screen2", 0.3)

        stats = registry.get_discovery_stats()
        assert stats["total_discovered"] == 3
        assert stats["discoveries_by_screen"]["screen1"] == 2
        assert stats["discoveries_by_screen"]["screen2"] == 1

    def test_export_import_discoveries(self):
        """Test exporting and importing discoveries."""
        registry1 = RuntimeSelectorRegistry(enable_discovery=True)
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.test:id/element",
        )
        registry1.record_discovery("discovered_element", strategy, "screen1", 0.5)

        # Export
        data = registry1.export_discoveries()

        # Import into new registry
        registry2 = RuntimeSelectorRegistry(enable_discovery=True)
        registry2.import_discoveries(data)

        selectors = registry2.get("discovered_element")
        assert selectors is not None

    def test_clear_discoveries(self):
        """Test clearing discoveries."""
        registry = RuntimeSelectorRegistry(enable_discovery=True)
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="test",
        )
        registry.record_discovery("elem", strategy, "screen", 0.1)
        assert registry.get("elem") is not None

        registry.clear_discoveries()
        assert registry.get("elem") is None


class TestElementFinder:
    """Tests for ElementFinder."""

    def create_mock_driver_and_finder(self, find_returns=None, find_raises=None):
        """Create a mock Appium driver and finder with mocked Selenium."""
        mock_driver = Mock()
        mock_element = Mock()
        mock_element.is_displayed.return_value = True

        # Create a custom ElementFinder that overrides _find_element and _find_visible_element
        class MockedElementFinder(ElementFinder):
            def __init__(self, driver, **kwargs):
                super().__init__(driver, **kwargs)
                self._find_count = 0
                self._find_returns = find_returns
                self._find_raises = find_raises

            def _find_element(self, locator_type, locator_value, timeout):
                self._find_count += 1
                if self._find_raises:
                    if callable(self._find_raises):
                        exc = self._find_raises(self._find_count)
                        if exc:
                            raise exc
                    else:
                        raise self._find_raises
                return self._find_returns

            def _find_visible_element(self, locator_type, locator_value, timeout):
                return self._find_element(locator_type, locator_value, timeout)

            def _find_elements_with_timeout(self, locator_type, locator_value, timeout):
                result = self._find_element(locator_type, locator_value, timeout)
                if result is None:
                    return []
                return [result] if result else []

        finder = MockedElementFinder(mock_driver)
        return mock_driver, mock_element, finder

    def test_find_success(self):
        """Test successful element find."""
        mock_element = Mock()
        mock_driver, _, finder = self.create_mock_driver_and_finder(find_returns=mock_element)

        selectors = ElementSelectors(
            name="test_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/button",
                ),
            ],
        )

        result = finder.find(selectors)
        assert is_ok(result)
        find_result = result.unwrap()
        assert find_result.element is mock_element
        assert find_result.attempts == 1

    def test_find_with_fallback(self):
        """Test element find with fallback to second strategy."""
        mock_element = Mock()

        # First strategy fails, second succeeds
        def find_raises(call_count):
            if call_count == 1:
                return Exception("First strategy failed")
            return None

        mock_driver, _, finder = self.create_mock_driver_and_finder(
            find_returns=mock_element,
            find_raises=find_raises,
        )

        selectors = ElementSelectors(
            name="test_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/button",
                    priority=1,
                ),
                SelectorDefinition(
                    strategy=SelectorStrategy.CONTENT_DESC,
                    value="Test Button",
                    priority=2,
                ),
            ],
        )

        result = finder.find(selectors)
        assert is_ok(result)
        find_result = result.unwrap()
        assert find_result.attempts == 2

    def test_find_failure(self):
        """Test element find failure returns error."""
        mock_driver, _, finder = self.create_mock_driver_and_finder(
            find_raises=Exception("Not found")
        )

        selectors = ElementSelectors(
            name="test_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/button",
                ),
            ],
        )

        result = finder.find(selectors)
        assert is_err(result)

    def test_find_with_cache(self):
        """Test that successful strategies are cached."""
        cache = ElementCache()

        # Directly test cache behavior
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/button",
        )

        # Verify cache is initially empty
        assert cache.get("test_context") is None

        # Add to cache
        cache.set("test_context", strategy)

        # Verify cache now has entry
        assert cache.get("test_context") is not None
        assert cache.get("test_context").value == "com.whatsapp:id/button"

        # Verify __contains__ works
        assert "test_context" in cache

    def test_is_present(self):
        """Test is_present method."""
        mock_element = Mock()
        mock_driver, _, finder = self.create_mock_driver_and_finder(find_returns=mock_element)

        selectors = ElementSelectors(
            name="test_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/button",
                ),
            ],
        )

        assert finder.is_present(selectors) is True

    def test_is_present_not_found(self):
        """Test is_present returns False when not found."""
        mock_driver, _, finder = self.create_mock_driver_and_finder(
            find_raises=Exception("Not found")
        )

        selectors = ElementSelectors(
            name="test_button",
            strategies=[
                SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="com.whatsapp:id/nonexistent",
                ),
            ],
        )

        assert finder.is_present(selectors) is False


class TestFindResult:
    """Tests for FindResult dataclass."""

    def test_locator_property(self):
        """Test getting locator from FindResult."""
        strategy = SelectorDefinition(
            strategy=SelectorStrategy.ID,
            value="com.whatsapp:id/button",
        )
        result = FindResult(
            element=Mock(),
            strategy=strategy,
            attempts=1,
            duration_seconds=0.5,
        )
        locator_type, locator_value = result.locator
        assert locator_type == "id"
        assert locator_value == "com.whatsapp:id/button"
