"""
Element strategy caching for performance optimization.

Caches successful element finding strategies to avoid repeated
fallback attempts on subsequent finds.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional
import threading
import json
from pathlib import Path

from ...config.selectors import SelectorDefinition, SelectorStrategy


@dataclass
class CacheEntry:
    """A cached selector strategy entry."""

    strategy: SelectorDefinition
    hit_count: int = 0
    miss_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        """Calculate success rate of this cached strategy."""
        total = self.hit_count + self.miss_count
        if total == 0:
            return 0.0
        return self.hit_count / total

    def record_hit(self) -> None:
        """Record a successful use of this strategy."""
        self.hit_count += 1
        self.last_used = datetime.now()

    def record_miss(self) -> None:
        """Record a failed use of this strategy."""
        self.miss_count += 1

    def is_stale(self, max_age: timedelta) -> bool:
        """Check if this entry is stale."""
        return datetime.now() - self.last_used > max_age


class ElementCache:
    """
    Cache for element finding strategies.

    Stores strategies that successfully found elements, allowing
    faster finds on subsequent attempts by trying the cached
    strategy first.
    """

    def __init__(
        self,
        max_entries: int = 100,
        max_age: timedelta = timedelta(hours=1),
        persistence_path: Optional[Path] = None,
    ):
        """
        Initialize the element cache.

        Args:
            max_entries: Maximum number of entries to cache
            max_age: Maximum age of cache entries before eviction
            persistence_path: Optional path to persist cache to disk
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._max_age = max_age
        self._persistence_path = persistence_path
        self._lock = threading.RLock()

        # Load persisted cache if available
        if persistence_path and persistence_path.exists():
            self._load_from_disk()

    def get(self, key: str) -> Optional[SelectorDefinition]:
        """
        Get a cached strategy for a key.

        Args:
            key: Cache key (usually element name + context)

        Returns:
            Cached SelectorDefinition or None
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Check if stale
            if entry.is_stale(self._max_age):
                del self._cache[key]
                return None

            return entry.strategy

    def set(
        self,
        key: str,
        strategy: SelectorDefinition,
    ) -> None:
        """
        Cache a successful strategy.

        Args:
            key: Cache key
            strategy: Strategy that successfully found the element
        """
        with self._lock:
            # Evict old entries if at capacity
            if len(self._cache) >= self._max_entries:
                self._evict_oldest()

            # Check if entry already exists
            if key in self._cache:
                self._cache[key].strategy = strategy
                self._cache[key].record_hit()
            else:
                self._cache[key] = CacheEntry(strategy=strategy, hit_count=1)

    def record_hit(self, key: str) -> None:
        """Record a successful use of a cached strategy."""
        with self._lock:
            if key in self._cache:
                self._cache[key].record_hit()

    def record_miss(self, key: str) -> None:
        """Record a failed use of a cached strategy."""
        with self._lock:
            if key in self._cache:
                self._cache[key].record_miss()

    def invalidate(self, key: str) -> None:
        """
        Invalidate a cached entry.

        Called when a cached strategy fails to find an element.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, any]:
        """Get cache statistics."""
        with self._lock:
            total_hits = sum(e.hit_count for e in self._cache.values())
            total_misses = sum(e.miss_count for e in self._cache.values())
            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "total_hits": total_hits,
                "total_misses": total_misses,
                "hit_rate": total_hits / (total_hits + total_misses)
                if (total_hits + total_misses) > 0
                else 0.0,
            }

    def _evict_oldest(self) -> None:
        """Evict the oldest entry from the cache."""
        if not self._cache:
            return

        # Find oldest entry by last_used
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_used,
        )
        del self._cache[oldest_key]

    def persist(self) -> None:
        """Persist cache to disk."""
        if not self._persistence_path:
            return

        with self._lock:
            data = {}
            for key, entry in self._cache.items():
                data[key] = {
                    "strategy_type": entry.strategy.strategy.value,
                    "strategy_value": entry.strategy.value,
                    "priority": entry.strategy.priority,
                    "timeout": entry.strategy.timeout,
                    "hit_count": entry.hit_count,
                    "miss_count": entry.miss_count,
                    "created_at": entry.created_at.isoformat(),
                    "last_used": entry.last_used.isoformat(),
                }

            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persistence_path, "w") as f:
                json.dump(data, f, indent=2)

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self._persistence_path or not self._persistence_path.exists():
            return

        try:
            with open(self._persistence_path, "r") as f:
                data = json.load(f)

            for key, entry_data in data.items():
                strategy = SelectorDefinition(
                    strategy=SelectorStrategy(entry_data["strategy_type"]),
                    value=entry_data["strategy_value"],
                    priority=entry_data.get("priority", 1),
                    timeout=entry_data.get("timeout", 5.0),
                )
                self._cache[key] = CacheEntry(
                    strategy=strategy,
                    hit_count=entry_data.get("hit_count", 0),
                    miss_count=entry_data.get("miss_count", 0),
                    created_at=datetime.fromisoformat(entry_data["created_at"]),
                    last_used=datetime.fromisoformat(entry_data["last_used"]),
                )
        except Exception:
            # If loading fails, start with empty cache
            self._cache.clear()

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if key is in cache."""
        return key in self._cache and not self._cache[key].is_stale(self._max_age)
