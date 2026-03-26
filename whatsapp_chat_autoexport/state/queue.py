"""
Export queue management.

Provides a priority queue for managing chat export order
with support for reordering and status filtering.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Iterator, Callable
import heapq
import threading


class QueuePriority(Enum):
    """Priority levels for queue items."""

    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(order=True)
class QueueItem:
    """
    An item in the export queue.

    Uses dataclass with order=True for heap operations.
    """

    priority: int = field(compare=True)
    index: int = field(compare=True)
    chat_name: str = field(compare=False)
    added_at: datetime = field(default_factory=datetime.now, compare=False)
    metadata: dict = field(default_factory=dict, compare=False)

    @classmethod
    def create(
        cls,
        chat_name: str,
        index: int,
        priority: QueuePriority = QueuePriority.NORMAL,
        **metadata,
    ) -> "QueueItem":
        """Create a queue item with the given parameters."""
        return cls(
            priority=priority.value,
            index=index,
            chat_name=chat_name,
            metadata=metadata,
        )


class ExportQueue:
    """
    Priority queue for managing chat exports.

    Thread-safe queue with support for:
    - Priority ordering
    - Item lookup by name
    - Filtering and iteration
    """

    def __init__(self):
        """Initialize the export queue."""
        self._heap: List[QueueItem] = []
        self._items: dict[str, QueueItem] = {}
        self._lock = threading.RLock()
        self._counter = 0

    def __len__(self) -> int:
        """Return number of items in queue."""
        return len(self._heap)

    def __contains__(self, chat_name: str) -> bool:
        """Check if chat is in queue."""
        return chat_name in self._items

    def add(
        self,
        chat_name: str,
        priority: QueuePriority = QueuePriority.NORMAL,
        **metadata,
    ) -> QueueItem:
        """
        Add a chat to the queue.

        Args:
            chat_name: Name of the chat
            priority: Queue priority
            **metadata: Additional metadata

        Returns:
            Created QueueItem
        """
        with self._lock:
            if chat_name in self._items:
                return self._items[chat_name]

            item = QueueItem.create(
                chat_name=chat_name,
                index=self._counter,
                priority=priority,
                **metadata,
            )
            self._counter += 1

            heapq.heappush(self._heap, item)
            self._items[chat_name] = item

            return item

    def add_many(
        self,
        chat_names: List[str],
        priority: QueuePriority = QueuePriority.NORMAL,
    ) -> List[QueueItem]:
        """
        Add multiple chats to the queue.

        Args:
            chat_names: List of chat names
            priority: Priority for all chats

        Returns:
            List of created QueueItems
        """
        with self._lock:
            items = []
            for name in chat_names:
                item = self.add(name, priority)
                items.append(item)
            return items

    def pop(self) -> Optional[QueueItem]:
        """
        Remove and return the highest priority item.

        Returns:
            QueueItem or None if queue is empty
        """
        with self._lock:
            while self._heap:
                item = heapq.heappop(self._heap)
                if item.chat_name in self._items:
                    del self._items[item.chat_name]
                    return item
            return None

    def peek(self) -> Optional[QueueItem]:
        """
        Return the highest priority item without removing.

        Returns:
            QueueItem or None if queue is empty
        """
        with self._lock:
            if self._heap:
                return self._heap[0]
            return None

    def get(self, chat_name: str) -> Optional[QueueItem]:
        """
        Get an item by chat name.

        Args:
            chat_name: Name of the chat

        Returns:
            QueueItem or None if not found
        """
        return self._items.get(chat_name)

    def remove(self, chat_name: str) -> Optional[QueueItem]:
        """
        Remove an item by chat name.

        Args:
            chat_name: Name of the chat

        Returns:
            Removed QueueItem or None
        """
        with self._lock:
            item = self._items.pop(chat_name, None)
            if item:
                # Mark as removed (will be skipped on pop)
                self._heap = [i for i in self._heap if i.chat_name != chat_name]
                heapq.heapify(self._heap)
            return item

    def reprioritize(
        self,
        chat_name: str,
        priority: QueuePriority,
    ) -> Optional[QueueItem]:
        """
        Change the priority of an item.

        Args:
            chat_name: Name of the chat
            priority: New priority

        Returns:
            Updated QueueItem or None
        """
        with self._lock:
            item = self.remove(chat_name)
            if item:
                return self.add(
                    chat_name,
                    priority,
                    **item.metadata,
                )
            return None

    def clear(self) -> None:
        """Remove all items from the queue."""
        with self._lock:
            self._heap.clear()
            self._items.clear()
            self._counter = 0

    def items(self) -> List[QueueItem]:
        """
        Get all items in priority order.

        Returns:
            List of QueueItems sorted by priority
        """
        with self._lock:
            return sorted(self._heap)

    def filter(
        self,
        predicate: Callable[[QueueItem], bool],
    ) -> List[QueueItem]:
        """
        Filter items by a predicate.

        Args:
            predicate: Function that returns True for items to include

        Returns:
            List of matching QueueItems
        """
        with self._lock:
            return [item for item in self._heap if predicate(item)]

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._heap) == 0

    def stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dict with queue stats
        """
        with self._lock:
            by_priority = {p.name: 0 for p in QueuePriority}
            for item in self._heap:
                for p in QueuePriority:
                    if item.priority == p.value:
                        by_priority[p.name] += 1
                        break

            return {
                "total": len(self._heap),
                "by_priority": by_priority,
            }
