"""
MCP bridge data source for WhatsApp Chat Auto-Export.

Implements the MessageSource interface by reading from the WhatsApp MCP
bridge's SQLite database via BridgeReader, translating rows to the
project's Message dataclass.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..mcp.bridge_reader import BridgeReader, BridgeMessage
from ..processing.transcript_parser import Message
from ..utils.logger import Logger
from .base import ChatInfo, MessageSource


class MCPSource(MessageSource):
    """
    MessageSource that reads from the WhatsApp MCP bridge database.

    Translates BridgeMessage rows into the project's Message dataclass
    with ``source="mcp"`` and ``message_id`` populated from WhatsApp's
    internal message IDs.
    """

    def __init__(
        self,
        reader: Optional[BridgeReader] = None,
        db_path: Optional[Path] = None,
        store_dir: Optional[Path] = None,
        user_display_name: str = "Me",
        logger: Optional[Logger] = None,
    ):
        """
        Initialize the MCP source.

        Provide either a pre-configured ``reader`` or ``db_path`` /
        ``store_dir`` to construct one automatically.

        Args:
            reader: An existing BridgeReader instance. If None, one is
                created from ``db_path`` and ``store_dir``.
            db_path: Path to the MCP bridge SQLite database.
            store_dir: Path to the bridge's store directory.
            user_display_name: Display name used for ``is_from_me``
                messages. Defaults to ``"Me"``.
            logger: Optional logger for output.
        """
        super().__init__(logger=logger or Logger())
        self.user_display_name = user_display_name

        if reader is not None:
            self._reader = reader
        else:
            kwargs = {}
            if db_path is not None:
                kwargs["db_path"] = db_path
            if store_dir is not None:
                kwargs["store_dir"] = store_dir
            self._reader = BridgeReader(**kwargs)

    # ------------------------------------------------------------------
    # MessageSource interface
    # ------------------------------------------------------------------

    def get_chats(self) -> List[ChatInfo]:
        """
        List all chats available in the MCP bridge database.

        Returns:
            List of ChatInfo objects with JID, display name, and
            last message time.
        """
        try:
            bridge_chats = self._reader.list_chats()
        except Exception as exc:
            self.log_error(f"Failed to list chats from MCP bridge: {exc}")
            return []

        chats: List[ChatInfo] = []
        for bc in bridge_chats:
            chats.append(
                ChatInfo(
                    jid=bc.jid,
                    name=bc.name or bc.jid,
                    last_message_time=bc.last_message_time,
                    # message_count is not cheaply available from the
                    # bridge schema, so we leave the default (0)
                )
            )

        self.log_info(f"Found {len(chats)} chats in MCP bridge")
        return chats

    def get_messages(
        self,
        chat_id: str,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """
        Retrieve messages for a chat from the MCP bridge.

        Args:
            chat_id: The chat JID.
            after: If set, only return messages after this timestamp.
            limit: If set, return at most this many messages.

        Returns:
            List of Message objects in chronological order, tagged with
            ``source="mcp"`` and ``message_id`` set.
        """
        try:
            bridge_messages = self._reader.get_messages(
                jid=chat_id, after=after, limit=limit
            )
        except Exception as exc:
            self.log_error(
                f"Failed to get messages for {chat_id}: {exc}"
            )
            return []

        messages: List[Message] = []
        for bm in bridge_messages:
            msg = self._translate_message(bm)
            messages.append(msg)

        return messages

    def get_media(self, message_id: str) -> Optional[Path]:
        """
        Retrieve media for a message by its ID.

        Note: this requires knowing the chat_jid. Since the
        MessageSource interface only passes message_id, we query the
        database for the chat_jid first.

        Args:
            message_id: The WhatsApp message ID.

        Returns:
            Path to the media file, or None if not available.
        """
        # We need the chat_jid to locate the media. Query for it.
        try:
            conn = self._reader._connect()
            try:
                cursor = conn.execute(
                    "SELECT chat_jid FROM messages WHERE id = ? LIMIT 1",
                    (message_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                chat_jid = row["chat_jid"]
            finally:
                conn.close()

            return self._reader.download_media(message_id, chat_jid)
        except Exception as exc:
            self.log_warning(f"Failed to get media for {message_id}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _translate_message(self, bm: BridgeMessage) -> Message:
        """Translate a BridgeMessage to a project Message."""
        # Resolve sender name
        if bm.is_from_me:
            sender = self.user_display_name
        elif bm.sender:
            sender = self._reader.get_sender_name(bm.sender)
        else:
            sender = "Unknown"

        # Determine media type — the bridge uses MIME-style types like
        # "image", "audio", "video", "document", "sticker" (or sometimes
        # the full MIME like "image/jpeg"). Normalise to simple types.
        is_media = bool(bm.media_type)
        media_type = self._normalise_media_type(bm.media_type) if is_media else None

        # Build content — for media messages with no text content,
        # produce a typed media tag matching the spec format
        content = bm.content
        if is_media and not content:
            content = f"<{media_type or 'media'}>"

        return Message(
            timestamp=bm.timestamp,
            sender=sender,
            content=content,
            is_media=is_media,
            media_type=media_type,
            raw_line="",
            line_number=0,
            message_id=bm.id,
            source="mcp",
        )

    @staticmethod
    def _normalise_media_type(raw: Optional[str]) -> Optional[str]:
        """
        Normalise a media type string to the project's canonical types.

        The bridge may store MIME types (``image/jpeg``) or simple
        labels (``image``). This normalises to: ``image``, ``audio``,
        ``video``, ``document``, ``sticker``.
        """
        if not raw:
            return None

        raw_lower = raw.lower().strip()

        # Direct matches
        canonical = {"image", "audio", "video", "document", "sticker"}
        if raw_lower in canonical:
            return raw_lower

        # MIME prefix matches
        for prefix in ("image", "audio", "video"):
            if raw_lower.startswith(prefix):
                return prefix

        # Application types → document
        if raw_lower.startswith("application") or raw_lower.startswith("document"):
            return "document"

        return raw_lower
