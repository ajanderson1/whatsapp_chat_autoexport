"""
Base message source interface for WhatsApp Chat Auto-Export.

Defines the abstract interface that all data sources must implement,
following the same pattern as BaseTranscriber.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..processing.transcript_parser import Message


@dataclass
class ChatInfo:
    """Metadata about a single chat available from a source."""
    jid: str
    name: str
    last_message_time: Optional[datetime] = None
    message_count: int = 0


class MessageSource(ABC):
    """
    Abstract base class for message data sources.

    All source implementations must inherit from this class and implement
    the get_chats(), get_messages(), and get_media() methods.
    """

    def __init__(self, logger=None):
        """
        Initialize the message source.

        Args:
            logger: Optional Logger instance for output
        """
        self.logger = logger

    @abstractmethod
    def get_chats(self) -> List[ChatInfo]:
        """
        List all chats available from this source.

        Returns:
            List of ChatInfo objects describing available chats
        """
        pass

    @abstractmethod
    def get_messages(
        self,
        chat_id: str,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """
        Retrieve messages for a given chat.

        Args:
            chat_id: Identifier for the chat (JID or contact name)
            after: If provided, only return messages after this time
            limit: If provided, return at most this many messages

        Returns:
            List of Message objects in chronological order
        """
        pass

    @abstractmethod
    def get_media(self, message_id: str) -> Optional[Path]:
        """
        Retrieve the media file associated with a message.

        Args:
            message_id: Unique identifier of the message

        Returns:
            Path to the media file, or None if not available
        """
        pass

    # ----- helper logging methods (mirrors BaseTranscriber) -----

    def log_info(self, message: str):
        """Log an info message if logger is available."""
        if self.logger:
            self.logger.info(message)

    def log_success(self, message: str):
        """Log a success message if logger is available."""
        if self.logger:
            self.logger.success(message)

    def log_warning(self, message: str):
        """Log a warning message if logger is available."""
        if self.logger:
            self.logger.warning(message)

    def log_error(self, message: str):
        """Log an error message if logger is available."""
        if self.logger:
            self.logger.error(message)

    def log_debug(self, message: str):
        """Log a debug message if logger is available."""
        if self.logger:
            self.logger.debug_msg(message)
