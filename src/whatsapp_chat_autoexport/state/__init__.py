"""
State management for WhatsApp Chat Auto-Export.

Provides:
- Pydantic state models for sessions and chats
- State manager with event emission
- Checkpoint save/restore functionality
- Export queue management
"""

from .models import (
    ChatStatus,
    ChatState,
    SessionStatus,
    SessionState,
    ExportProgress,
    PipelineProgress,
)
from .state_manager import StateManager
from .checkpoint import CheckpointManager
from .queue import ExportQueue, QueueItem, QueuePriority

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
