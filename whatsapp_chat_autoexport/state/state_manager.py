"""
State manager with event emission.

Provides centralized state management with automatic event
emission for state changes.
"""

from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import threading

from .models import (
    ChatStatus,
    ChatState,
    SessionStatus,
    SessionState,
    ExportProgress,
)
from ..core.events import (
    EventBus,
    EventType,
    StateChangeEvent,
    ExportProgressEvent,
    get_event_bus,
    emit,
)


class StateManager:
    """
    Centralized state manager for export sessions.

    Manages session and chat state with automatic event emission
    for state changes.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the state manager.

        Args:
            event_bus: Optional event bus for notifications
        """
        self._session: Optional[SessionState] = None
        self._event_bus = event_bus or get_event_bus()
        self._lock = threading.RLock()
        self._start_time: Optional[datetime] = None

    @property
    def session(self) -> Optional[SessionState]:
        """Get the current session state."""
        return self._session

    @property
    def has_session(self) -> bool:
        """Check if a session exists."""
        return self._session is not None

    def create_session(
        self,
        include_media: bool = True,
        limit: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> SessionState:
        """
        Create a new export session.

        Args:
            include_media: Whether to include media in exports
            limit: Optional limit on number of chats
            device_id: Optional device identifier

        Returns:
            New SessionState
        """
        with self._lock:
            self._session = SessionState(
                include_media=include_media,
                limit=limit,
                device_id=device_id,
            )
            self._start_time = datetime.now()

            self._emit_state_change("none", "initializing")
            return self._session

    def get_session(self) -> SessionState:
        """
        Get the current session, creating one if needed.

        Returns:
            Current SessionState
        """
        if self._session is None:
            return self.create_session()
        return self._session

    def set_session_status(self, status: SessionStatus) -> None:
        """
        Set the session status.

        Args:
            status: New session status
        """
        with self._lock:
            if self._session is None:
                return

            old_status = self._session.status.value
            self._session.status = status

            if status == SessionStatus.EXPORTING and self._session.started_at is None:
                self._session.started_at = datetime.now()
            elif status in (
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.CANCELLED,
            ):
                self._session.completed_at = datetime.now()

            self._emit_state_change(old_status, status.value)

    def add_chat(self, chat_name: str, index: int = 0) -> ChatState:
        """
        Add a chat to the session.

        Args:
            chat_name: Name of the chat
            index: Index in the chat list

        Returns:
            ChatState for the added chat
        """
        with self._lock:
            session = self.get_session()
            chat = session.add_chat(chat_name, index)

            self._event_bus.emit_simple(
                EventType.QUEUE_ITEM_ADDED,
                source="state_manager",
                chat_name=chat_name,
                index=index,
            )

            return chat

    def add_chats(self, chat_names: List[str]) -> List[ChatState]:
        """
        Add multiple chats to the session.

        Args:
            chat_names: List of chat names

        Returns:
            List of ChatState objects
        """
        with self._lock:
            chats = []
            for i, name in enumerate(chat_names):
                chat = self.add_chat(name, i)
                chats.append(chat)

            self._event_bus.emit_simple(
                EventType.CHAT_COLLECTION_COMPLETED,
                source="state_manager",
                total_chats=len(chat_names),
            )

            return chats

    def start_chat(self, chat_name: str) -> Optional[ChatState]:
        """
        Mark a chat as started.

        Args:
            chat_name: Name of the chat

        Returns:
            Updated ChatState or None
        """
        with self._lock:
            if self._session is None:
                return None

            chat = self._session.get_chat(chat_name)
            if chat is None:
                return None

            old_status = chat.status.value
            chat.start()

            self._emit_state_change(old_status, chat.status.value, chat_name=chat_name)
            self._emit_progress()

            return chat

    def complete_chat(self, chat_name: str) -> Optional[ChatState]:
        """
        Mark a chat as completed.

        Args:
            chat_name: Name of the chat

        Returns:
            Updated ChatState or None
        """
        with self._lock:
            if self._session is None:
                return None

            chat = self._session.get_chat(chat_name)
            if chat is None:
                return None

            old_status = chat.status.value
            chat.complete()
            self._session.update_counts()

            self._emit_state_change(old_status, chat.status.value, chat_name=chat_name)
            self._emit_progress()

            self._event_bus.emit_simple(
                EventType.EXPORT_COMPLETED,
                source="state_manager",
                chat_name=chat_name,
            )

            return chat

    def fail_chat(self, chat_name: str, error_message: str) -> Optional[ChatState]:
        """
        Mark a chat as failed.

        Args:
            chat_name: Name of the chat
            error_message: Error description

        Returns:
            Updated ChatState or None
        """
        with self._lock:
            if self._session is None:
                return None

            chat = self._session.get_chat(chat_name)
            if chat is None:
                return None

            old_status = chat.status.value
            chat.fail(error_message)
            self._session.update_counts()

            self._emit_state_change(old_status, chat.status.value, chat_name=chat_name)
            self._emit_progress()

            self._event_bus.emit_simple(
                EventType.EXPORT_FAILED,
                source="state_manager",
                chat_name=chat_name,
                error=error_message,
            )

            return chat

    def skip_chat(self, chat_name: str, reason: str) -> Optional[ChatState]:
        """
        Mark a chat as skipped.

        Args:
            chat_name: Name of the chat
            reason: Skip reason

        Returns:
            Updated ChatState or None
        """
        with self._lock:
            if self._session is None:
                return None

            chat = self._session.get_chat(chat_name)
            if chat is None:
                return None

            old_status = chat.status.value
            chat.skip(reason)
            self._session.update_counts()

            self._emit_state_change(old_status, chat.status.value, chat_name=chat_name)
            self._emit_progress()

            self._event_bus.emit_simple(
                EventType.EXPORT_SKIPPED,
                source="state_manager",
                chat_name=chat_name,
                reason=reason,
            )

            return chat

    def record_step(self, chat_name: str, step_name: str) -> None:
        """
        Record a completed step for a chat.

        Args:
            chat_name: Name of the chat
            step_name: Name of the completed step
        """
        with self._lock:
            if self._session is None:
                return

            chat = self._session.get_chat(chat_name)
            if chat is None:
                return

            chat.record_step(step_name)

            self._event_bus.emit_simple(
                EventType.EXPORT_STEP_COMPLETED,
                source="state_manager",
                chat_name=chat_name,
                step_name=step_name,
                step_index=chat.current_step,
            )

    def get_progress(self) -> ExportProgress:
        """
        Get current export progress snapshot.

        Returns:
            ExportProgress with current state
        """
        with self._lock:
            if self._session is None:
                return ExportProgress()

            current_chat = self._session.current_chat
            elapsed = 0.0
            if self._start_time:
                elapsed = (datetime.now() - self._start_time).total_seconds()

            return ExportProgress(
                current_chat=current_chat.name if current_chat else None,
                current_step=current_chat.steps_completed[-1]
                if current_chat and current_chat.steps_completed
                else "",
                step_index=current_chat.current_step if current_chat else 0,
                total_steps=6,
                chats_completed=self._session.completed_chats,
                chats_total=self._session.total_chats,
                chats_failed=self._session.failed_chats,
                chats_skipped=self._session.skipped_chats,
                status=self._session.status.value,
                elapsed_seconds=elapsed,
            )

    def get_pending_chats(self) -> List[ChatState]:
        """Get list of pending chats."""
        with self._lock:
            if self._session is None:
                return []
            return [
                c
                for c in self._session.chats.values()
                if c.status == ChatStatus.PENDING
            ]

    def get_next_chat(self) -> Optional[ChatState]:
        """Get the next pending chat to process."""
        with self._lock:
            pending = self.get_pending_chats()
            if pending:
                # Sort by index to maintain order
                return min(pending, key=lambda c: c.index)
            return None

    def pause(self) -> None:
        """Pause the session and current chat."""
        with self._lock:
            if self._session:
                old_status = self._session.status.value
                self._session.pause()

                # Also pause current chat
                current = self._session.current_chat
                if current:
                    current.pause()

                self._emit_state_change(old_status, "paused")

    def resume(self) -> None:
        """Resume the session."""
        with self._lock:
            if self._session:
                old_status = self._session.status.value
                self._session.resume()

                # Resume paused chat
                for chat in self._session.chats.values():
                    if chat.status == ChatStatus.PAUSED:
                        chat.resume()
                        break

                self._emit_state_change(old_status, "exporting")

    def reset(self) -> None:
        """Reset the state manager."""
        with self._lock:
            self._session = None
            self._start_time = None

    def _emit_state_change(
        self,
        old_state: str,
        new_state: str,
        **data,
    ) -> None:
        """Emit a state change event."""
        event = StateChangeEvent(
            old_state=old_state,
            new_state=new_state,
            data=data,
        )
        self._event_bus.emit(event)

    def _emit_progress(self) -> None:
        """Emit a progress update event."""
        progress = self.get_progress()
        event = ExportProgressEvent(
            chat_name=progress.current_chat or "",
            step_name=progress.current_step,
            step_index=progress.step_index,
            total_steps=progress.total_steps,
            status=progress.status,
            message=f"{progress.chats_completed}/{progress.chats_total} chats",
        )
        self._event_bus.emit(event)
