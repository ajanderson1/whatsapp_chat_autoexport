"""
Automation layer for WhatsApp Chat Auto-Export.

Provides UI automation abstractions including:
- Element finding with multi-strategy fallback
- Session and driver management
- Gesture execution (scroll, swipe, tap)
- App and screen verification
"""

from .elements.element_finder import (
    ElementFinder,
    FindResult,
)
from .elements.element_cache import (
    ElementCache,
    CacheEntry,
)
from .elements.selector_registry import (
    RuntimeSelectorRegistry,
)

__all__ = [
    # Element finding
    "ElementFinder",
    "FindResult",
    # Caching
    "ElementCache",
    "CacheEntry",
    # Registry
    "RuntimeSelectorRegistry",
]
