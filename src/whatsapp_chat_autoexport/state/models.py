"""
Pydantic state models for session and chat tracking.

Provides type-safe state representations that can be serialized
for checkpointing and resumed later.
"""

from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatStatus(str, Enum):
    """Status of a chat in the export queue."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PAUSED = "paused"


class ChatState(BaseModel):
    """
    State of a single chat export.

    Tracks the progress and status of exporting one chat.
    """

    # Identification
    name: str
    index: int = 0

    # Status
    status: ChatStatus = ChatStatus.PENDING
    error_message: Optional[str] = None

    # Progress
    current_step: int = 0
    total_steps: int = 6
    steps_completed: List[str] = Field(default_factory=list)

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Retry tracking
    attempt_count: int = 0
    max_attempts: int = 3

    # Additional data
    include_media: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Check if export is complete (success or skipped)."""
        return self.status in (ChatStatus.COMPLETED, ChatStatus.SKIPPED)

    @property
    def is_failed(self) -> bool:
        """Check if export failed."""
        return self.status == ChatStatus.FAILED

    @property
    def can_retry(self) -> bool:
        """Check if export can be retried."""
        return self.is_failed and self.attempt_count < self.max_attempts

    def start(self) -> None:
        """Mark export as started."""
        self.status = ChatStatus.IN_PROGRESS
        self.started_at = datetime.now()
        self.attempt_count += 1

    def complete(self) -> None:
        """Mark export as completed."""
        self.status = ChatStatus.COMPLETED
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def fail(self, error_message: str) -> None:
        """Mark export as failed."""
        self.status = ChatStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def skip(self, reason: str) -> None:
        """Mark export as skipped."""
        self.status = ChatStatus.SKIPPED
        self.error_message = reason
        self.completed_at = datetime.now()

    def pause(self) -> None:
        """Mark export as paused."""
        self.status = ChatStatus.PAUSED

    def resume(self) -> None:
        """Resume paused export."""
        self.status = ChatStatus.IN_PROGRESS

    def record_step(self, step_name: str) -> None:
        """Record a completed step."""
        if step_name not in self.steps_completed:
            self.steps_completed.append(step_name)
        self.current_step = len(self.steps_completed)


class SessionStatus(str, Enum):
    """Status of an export session."""

    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    COLLECTING_CHATS = "collecting_chats"
    EXPORTING = "exporting"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionState(BaseModel):
    """
    State of an export session.

    Tracks the overall progress of the export process.
    """

    # Session identification
    session_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    # Status
    status: SessionStatus = SessionStatus.INITIALIZING
    error_message: Optional[str] = None

    # Chat tracking
    chats: Dict[str, ChatState] = Field(default_factory=dict)
    chat_order: List[str] = Field(default_factory=list)

    # Progress
    total_chats: int = 0
    completed_chats: int = 0
    failed_chats: int = 0
    skipped_chats: int = 0

    # Configuration
    include_media: bool = True
    limit: Optional[int] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Device info
    device_id: Optional[str] = None
    device_name: Optional[str] = None

    @property
    def pending_chats(self) -> int:
        """Get count of pending chats."""
        return self.total_chats - self.completed_chats - self.failed_chats - self.skipped_chats

    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_chats == 0:
            return 0.0
        processed = self.completed_chats + self.failed_chats + self.skipped_chats
        return (processed / self.total_chats) * 100

    @property
    def current_chat(self) -> Optional[ChatState]:
        """Get the currently active chat."""
        for chat in self.chats.values():
            if chat.status == ChatStatus.IN_PROGRESS:
                return chat
        return None

    def add_chat(self, chat_name: str, index: int = 0) -> ChatState:
        """Add a chat to the session."""
        if chat_name in self.chats:
            return self.chats[chat_name]

        chat = ChatState(
            name=chat_name,
            index=index,
            include_media=self.include_media,
        )
        self.chats[chat_name] = chat
        self.chat_order.append(chat_name)
        self.total_chats = len(self.chats)
        return chat

    def get_chat(self, chat_name: str) -> Optional[ChatState]:
        """Get a chat by name."""
        return self.chats.get(chat_name)

    def update_counts(self) -> None:
        """Update progress counts from chat states."""
        self.completed_chats = sum(
            1 for c in self.chats.values() if c.status == ChatStatus.COMPLETED
        )
        self.failed_chats = sum(
            1 for c in self.chats.values() if c.status == ChatStatus.FAILED
        )
        self.skipped_chats = sum(
            1 for c in self.chats.values() if c.status == ChatStatus.SKIPPED
        )

    def start(self) -> None:
        """Mark session as started."""
        self.status = SessionStatus.EXPORTING
        self.started_at = datetime.now()

    def complete(self) -> None:
        """Mark session as completed."""
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.now()

    def fail(self, error_message: str) -> None:
        """Mark session as failed."""
        self.status = SessionStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()

    def pause(self) -> None:
        """Pause the session."""
        self.status = SessionStatus.PAUSED

    def resume(self) -> None:
        """Resume the session."""
        self.status = SessionStatus.EXPORTING


class ExportProgress(BaseModel):
    """Progress snapshot for export operations."""

    # Current chat
    current_chat: Optional[str] = None
    current_step: str = ""
    step_index: int = 0
    total_steps: int = 6

    # Overall progress
    chats_completed: int = 0
    chats_total: int = 0
    chats_failed: int = 0
    chats_skipped: int = 0

    # Status
    status: str = "idle"
    message: str = ""

    # Timing
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None

    @property
    def percent_complete(self) -> float:
        """Get overall progress percentage."""
        if self.chats_total == 0:
            return 0.0
        processed = self.chats_completed + self.chats_failed + self.chats_skipped
        return (processed / self.chats_total) * 100


class PipelineProgress(BaseModel):
    """Progress snapshot for pipeline operations."""

    # Current phase
    phase: str = ""
    phase_index: int = 0
    total_phases: int = 5

    # Items in current phase
    items_processed: int = 0
    items_total: int = 0
    current_item: Optional[str] = None

    # Status
    status: str = "idle"
    message: str = ""

    # Timing
    elapsed_seconds: float = 0.0

    @property
    def percent_complete(self) -> float:
        """Get overall progress percentage."""
        if self.total_phases == 0:
            return 0.0
        phase_progress = (self.phase_index / self.total_phases) * 100
        if self.items_total > 0:
            item_progress = (self.items_processed / self.items_total) * (
                100 / self.total_phases
            )
            return phase_progress + item_progress
        return phase_progress
