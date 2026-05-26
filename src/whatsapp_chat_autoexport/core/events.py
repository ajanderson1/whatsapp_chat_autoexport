"""
Event system for state change notifications.

Provides a simple pub/sub event system for decoupling components
and enabling real-time UI updates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, Any, List, Callable, Optional
from threading import Lock


class EventType(Enum):
    """Types of events that can be emitted."""

    # State change events
    STATE_CHANGED = auto()
    SESSION_STARTED = auto()
    SESSION_ENDED = auto()

    # Device events
    DEVICE_CONNECTED = auto()
    DEVICE_DISCONNECTED = auto()
    DEVICE_ERROR = auto()

    # Export workflow events
    EXPORT_STARTED = auto()
    EXPORT_STEP_STARTED = auto()
    EXPORT_STEP_COMPLETED = auto()
    EXPORT_STEP_FAILED = auto()
    EXPORT_COMPLETED = auto()
    EXPORT_FAILED = auto()
    EXPORT_SKIPPED = auto()

    # Chat events
    CHAT_COLLECTION_STARTED = auto()
    CHAT_COLLECTION_COMPLETED = auto()
    CHAT_FOUND = auto()
    CHAT_PROCESSING_STARTED = auto()
    CHAT_PROCESSING_COMPLETED = auto()

    # Queue events
    QUEUE_UPDATED = auto()
    QUEUE_ITEM_ADDED = auto()
    QUEUE_ITEM_REMOVED = auto()
    QUEUE_ITEM_STATUS_CHANGED = auto()

    # Pipeline events
    PIPELINE_STARTED = auto()
    PIPELINE_PHASE_STARTED = auto()
    PIPELINE_PHASE_COMPLETED = auto()
    PIPELINE_PHASE_FAILED = auto()
    PIPELINE_COMPLETED = auto()

    # Progress events
    PROGRESS_UPDATED = auto()
    PROGRESS_INDETERMINATE = auto()

    # Transcription events
    TRANSCRIPTION_STARTED = auto()
    TRANSCRIPTION_COMPLETED = auto()
    TRANSCRIPTION_FAILED = auto()
    TRANSCRIPTION_SKIPPED = auto()

    # Error events
    ERROR_OCCURRED = auto()
    WARNING_OCCURRED = auto()
    RECOVERY_ATTEMPTED = auto()
    RECOVERY_SUCCEEDED = auto()
    RECOVERY_FAILED = auto()

    # User interaction events
    USER_INPUT_REQUIRED = auto()
    USER_CONFIRMATION_REQUIRED = auto()
    USER_ACTION_COMPLETED = auto()

    # Checkpoint events
    CHECKPOINT_SAVED = auto()
    CHECKPOINT_LOADED = auto()


@dataclass
class Event:
    """Base event class."""

    type: EventType = field(default=None)  # type: ignore  # Set by subclass or required for base
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None  # Component that emitted the event

    def __post_init__(self):
        if self.type is None:
            raise ValueError("Event type is required")

    def __str__(self) -> str:
        return f"Event({self.type.name}, data={self.data})"


@dataclass
class StateChangeEvent(Event):
    """Event for state changes."""

    old_state: str = ""
    new_state: str = ""

    def __post_init__(self):
        # Set type before parent validation
        object.__setattr__(self, "type", EventType.STATE_CHANGED)
        self.data.update(
            {
                "old_state": self.old_state,
                "new_state": self.new_state,
            }
        )


@dataclass
class ExportProgressEvent(Event):
    """Event for export progress updates."""

    chat_name: str = ""
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 6
    status: str = "in_progress"
    message: str = ""

    def __post_init__(self):
        # Set type before parent validation
        object.__setattr__(self, "type", EventType.PROGRESS_UPDATED)
        self.data.update(
            {
                "chat_name": self.chat_name,
                "step_name": self.step_name,
                "step_index": self.step_index,
                "total_steps": self.total_steps,
                "status": self.status,
                "message": self.message,
            }
        )


@dataclass
class PipelineProgressEvent(Event):
    """Event for pipeline progress updates."""

    phase: str = ""
    current: int = 0
    total: int = 0
    item_name: str = ""
    message: str = ""

    def __post_init__(self):
        # Set type before parent validation
        object.__setattr__(self, "type", EventType.PROGRESS_UPDATED)
        self.data.update(
            {
                "phase": self.phase,
                "current": self.current,
                "total": self.total,
                "item_name": self.item_name,
                "message": self.message,
            }
        )


@dataclass
class ErrorEvent(Event):
    """Event for error notifications."""

    error_message: str = ""
    error_category: str = ""
    recoverable: bool = False
    recovery_action: Optional[str] = None

    def __post_init__(self):
        # Set type before parent validation
        object.__setattr__(self, "type", EventType.ERROR_OCCURRED)
        self.data.update(
            {
                "error_message": self.error_message,
                "error_category": self.error_category,
                "recoverable": self.recoverable,
                "recovery_action": self.recovery_action,
            }
        )


# Type alias for event handlers
EventHandler = Callable[[Event], None]


class EventBus:
    """
    Simple pub/sub event bus for decoupled communication.

    Thread-safe implementation for synchronous event handling.

    Usage:
        bus = EventBus()

        def on_progress(event):
            print(f"Progress: {event.data}")

        bus.subscribe(EventType.PROGRESS_UPDATED, on_progress)
        bus.emit(ExportProgressEvent(chat_name="John", step_name="open_menu"))
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._lock = Lock()
        self._history: List[Event] = []
        self._max_history = 100

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> Callable[[], None]:
        """
        Subscribe to an event type.

        Args:
            event_type: Type of event to listen for
            handler: Function to call when event occurs

        Returns:
            Unsubscribe function
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []

            self._handlers[event_type].append(handler)

        def unsubscribe():
            with self._lock:
                if event_type in self._handlers:
                    try:
                        self._handlers[event_type].remove(handler)
                    except ValueError:
                        pass  # Handler already removed

        return unsubscribe

    def subscribe_all(self, handler: EventHandler) -> Callable[[], None]:
        """
        Subscribe to all event types.

        Args:
            handler: Function to call for any event

        Returns:
            Unsubscribe function
        """
        unsubscribers = []
        for event_type in EventType:
            unsubscribers.append(self.subscribe(event_type, handler))

        def unsubscribe_all():
            for unsub in unsubscribers:
                unsub()

        return unsubscribe_all

    def emit(self, event: Event) -> None:
        """
        Emit an event to all subscribers.

        Args:
            event: Event to emit
        """
        with self._lock:
            # Store in history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            # Get a copy of handlers to iterate
            handlers = list(self._handlers.get(event.type, []))

        # Call handlers outside the lock to prevent deadlocks
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Log but don't propagate handler errors
                print(f"Event handler error: {e}")

    def emit_simple(
        self,
        event_type: EventType,
        source: Optional[str] = None,
        **data,
    ) -> None:
        """
        Emit a simple event with data.

        Args:
            event_type: Type of event
            source: Component emitting the event
            **data: Event data
        """
        self.emit(Event(type=event_type, data=data, source=source))

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 50,
    ) -> List[Event]:
        """
        Get event history.

        Args:
            event_type: Filter by event type (None for all)
            limit: Maximum number of events to return

        Returns:
            List of recent events
        """
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e.type == event_type]
            return events[-limit:]

    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._history = []

    def clear_handlers(self) -> None:
        """Remove all event handlers."""
        with self._lock:
            self._handlers = {}


# Global event bus singleton
_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def emit(event: Event) -> None:
    """Emit an event on the global bus."""
    get_event_bus().emit(event)


def subscribe(event_type: EventType, handler: EventHandler) -> Callable[[], None]:
    """Subscribe to an event type on the global bus."""
    return get_event_bus().subscribe(event_type, handler)
