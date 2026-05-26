"""
State management for WhatsApp Chat Auto-Export.

Provides:
- Pydantic state models for sessions and chats
- State manager with event emission
- Checkpoint save/restore functionality
- Export queue management
"""

from .checkpoint import CheckpointManager
from .models import (
    ChatState,
    ChatStatus,
    ExportProgress,
    PipelineProgress,
    SessionState,
    SessionStatus,
)
from .queue import ExportQueue, QueueItem, QueuePriority
from .state_manager import StateManager

__all__ = [
    # Models
    "ChatStatus",
    "ChatState",
    "SessionStatus",
    "SessionState",
    "ExportProgress",
    "PipelineProgress",
    # State manager
    "StateManager",
    # Checkpoint
    "CheckpointManager",
    # Queue
    "ExportQueue",
    "QueueItem",
    "QueuePriority",
]
