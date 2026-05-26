"""
Element finding and caching for UI automation.
"""

from .element_finder import ElementFinder, FindResult
from .element_cache import ElementCache, CacheEntry
from .selector_registry import RuntimeSelectorRegistry

__all__ = [
    "ElementFinder",
    "FindResult",
    "ElementCache",
    "CacheEntry",
    "RuntimeSelectorRegistry",
]
