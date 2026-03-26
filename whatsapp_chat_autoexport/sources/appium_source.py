"""
Appium data source for WhatsApp Chat Auto-Export.

Wraps the existing TranscriptParser to provide Appium-exported chats
through the MessageSource interface.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..processing.transcript_parser import Message, MediaReference, TranscriptParser
from ..utils.logger import Logger
from .base import ChatInfo, MessageSource


class AppiumSource(MessageSource):
    """
    MessageSource that reads Appium export directories.

    Expects a root directory containing one sub-directory per chat, each with
    a transcript file (``*.txt``) and an optional ``media/`` folder.

    Directory layout::

        export_root/
            Contact Name/
                WhatsApp Chat with Contact Name.txt
                media/
                    IMG-20240101-WA0001.jpg
                    ...
    """

    def __init__(
        self,
        export_dir: Path,
        logger: Optional[Logger] = None,
    ):
        """
        Initialize the Appium source.

        Args:
            export_dir: Root directory of the Appium export output
            logger: Optional logger for output
        """
        super().__init__(logger=logger or Logger())
        self.export_dir = export_dir
        self._parser = TranscriptParser(logger=self.logger)
        # Cache: chat_name -> (messages, media_refs)
        self._cache: Dict[str, Tuple[List[Message], List[MediaReference]]] = {}

    def get_chats(self) -> List[ChatInfo]:
        """
        List all chats found in the Appium export directory.

        Each sub-directory that contains a ``.txt`` transcript file is
        treated as a chat.
        """
        chats: List[ChatInfo] = []

        if not self.export_dir.is_dir():
            self.log_error(f"Export directory not found: {self.export_dir}")
            return chats

        for child in sorted(self.export_dir.iterdir()):
            if not child.is_dir():
                continue

            transcript = self._find_transcript(child)
            if transcript is None:
                continue

            # Parse to get message count and date range
            messages, _ = self._parse_chat(child.name)
            last_time = messages[-1].timestamp if messages else None

            chats.append(
                ChatInfo(
                    jid=child.name,
                    name=child.name,
                    last_message_time=last_time,
                    message_count=len(messages),
                )
            )

        self.log_info(f"Found {len(chats)} chats in Appium export")
        return chats

    def get_messages(
        self,
        chat_id: str,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """
        Retrieve messages for a chat, optionally filtered by time.

        Args:
            chat_id: The chat directory name (contact name)
            after: If set, only return messages after this timestamp
            limit: If set, return at most this many messages
        """
        messages, _ = self._parse_chat(chat_id)

        # Tag every message with the appium source
        for msg in messages:
            msg.source = "appium"

        if after is not None:
            messages = [m for m in messages if m.timestamp > after]

        if limit is not None:
            messages = messages[:limit]

        return messages

    def get_media(self, message_id: str) -> Optional[Path]:
        """
        Media lookup is not supported for Appium exports by message ID.

        Use ``TranscriptParser.correlate_media_files()`` instead.
        """
        self.log_warning(
            "get_media() is not supported for AppiumSource; "
            "use TranscriptParser.correlate_media_files() for media correlation"
        )
        return None

    # ----- internal helpers -----

    def _find_transcript(self, chat_dir: Path) -> Optional[Path]:
        """Return the first .txt transcript file in *chat_dir*, or None."""
        for candidate in sorted(chat_dir.glob("*.txt")):
            if candidate.is_file():
                return candidate
        return None

    def _parse_chat(
        self, chat_name: str
    ) -> Tuple[List[Message], List[MediaReference]]:
        """Parse a chat directory, returning cached results when available."""
        if chat_name in self._cache:
            return self._cache[chat_name]

        chat_dir = self.export_dir / chat_name
        transcript = self._find_transcript(chat_dir)

        if transcript is None:
            self.log_warning(f"No transcript found in {chat_dir}")
            self._cache[chat_name] = ([], [])
            return [], []

        messages, media_refs = self._parser.parse_transcript(transcript)
        self._cache[chat_name] = (messages, media_refs)
        return messages, media_refs
