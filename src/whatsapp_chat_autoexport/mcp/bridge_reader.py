"""
Bridge reader for the WhatsApp MCP bridge's SQLite database.

Self-contained module that reads messages and chats directly from the
SQLite database maintained by the Go-based WhatsApp bridge. Does not
import or depend on the MCP server Python code.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default location of the MCP bridge's SQLite database
DEFAULT_DB_PATH = Path.home() / "GitHub" / "claude" / "mcps" / "third_party" / "whatsapp" / "repo" / "whatsapp-bridge" / "store" / "messages.db"

# Default location of the bridge's media store directory
DEFAULT_STORE_DIR = Path.home() / "GitHub" / "claude" / "mcps" / "third_party" / "whatsapp" / "repo" / "whatsapp-bridge" / "store"


@dataclass
class BridgeChat:
    """A chat record from the MCP bridge database."""
    jid: str
    name: Optional[str]
    last_message_time: Optional[datetime]


@dataclass
class BridgeMessage:
    """A message record from the MCP bridge database."""
    id: str
    chat_jid: str
    sender: str
    content: str
    timestamp: datetime
    is_from_me: bool
    media_type: Optional[str] = None
    filename: Optional[str] = None


class BridgeReaderError(Exception):
    """Base exception for BridgeReader errors."""
    pass


class DatabaseNotFoundError(BridgeReaderError):
    """Raised when the MCP bridge database file does not exist."""
    pass


class DatabaseLockedError(BridgeReaderError):
    """Raised when the MCP bridge database is locked."""
    pass


class BridgeReader:
    """
    Reads the WhatsApp MCP bridge's SQLite database directly.

    Provides methods to list chats, query messages with optional time
    filtering, resolve sender names, and locate downloaded media files.

    The database path and store directory are configurable. Connections
    are opened in read-only mode with a busy timeout to handle brief
    locks from the Go bridge writing concurrently.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        store_dir: Optional[Path] = None,
        busy_timeout_ms: int = 5000,
    ):
        """
        Initialize the bridge reader.

        Args:
            db_path: Path to the SQLite database. Defaults to the
                standard MCP bridge location.
            store_dir: Path to the bridge's ``store/`` directory where
                media files are saved. Defaults to the parent of the
                database file.
            busy_timeout_ms: SQLite busy timeout in milliseconds.
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.store_dir = Path(store_dir) if store_dir else DEFAULT_STORE_DIR
        self.busy_timeout_ms = busy_timeout_ms

        # Cache for sender name resolution
        self._name_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """
        Open a read-only connection to the bridge database.

        Raises:
            DatabaseNotFoundError: If the database file does not exist.
            DatabaseLockedError: If the database cannot be opened due
                to a persistent lock.
        """
        if not self.db_path.exists():
            raise DatabaseNotFoundError(
                f"MCP bridge database not found at {self.db_path}"
            )

        try:
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                timeout=self.busy_timeout_ms / 1000,
            )
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "readonly" in str(exc).lower():
                raise DatabaseLockedError(
                    f"MCP bridge database is locked: {exc}"
                ) from exc
            raise BridgeReaderError(
                f"Failed to open database: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_chats(self) -> List[BridgeChat]:
        """
        List all chats in the bridge database.

        Returns:
            List of BridgeChat objects sorted by last_message_time
            descending.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT jid, name, last_message_time "
                "FROM chats "
                "ORDER BY last_message_time DESC"
            )
            chats: List[BridgeChat] = []
            for row in cursor.fetchall():
                last_time = None
                if row["last_message_time"]:
                    try:
                        last_time = datetime.fromisoformat(
                            str(row["last_message_time"])
                        )
                    except (ValueError, TypeError):
                        logger.warning(
                            "Could not parse last_message_time for %s: %s",
                            row["jid"],
                            row["last_message_time"],
                        )
                chats.append(
                    BridgeChat(
                        jid=row["jid"],
                        name=row["name"],
                        last_message_time=last_time,
                    )
                )
            return chats
        finally:
            conn.close()

    def get_messages(
        self,
        jid: str,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[BridgeMessage]:
        """
        Retrieve messages for a chat, optionally filtered by time.

        Messages are returned in chronological order (oldest first).

        Args:
            jid: Chat JID to query.
            after: If provided, only return messages with a timestamp
                strictly after this value.
            limit: If provided, return at most this many messages.

        Returns:
            List of BridgeMessage objects in chronological order.
        """
        conn = self._connect()
        try:
            query_parts = [
                "SELECT id, chat_jid, sender, content, timestamp, "
                "is_from_me, media_type, filename "
                "FROM messages "
                "WHERE chat_jid = ?"
            ]
            params: list = [jid]

            if after is not None:
                query_parts.append("AND timestamp > ?")
                # Use space-separated format to match how the Go bridge stores timestamps
                params.append(after.strftime("%Y-%m-%d %H:%M:%S"))

            query_parts.append("ORDER BY timestamp ASC")

            if limit is not None:
                query_parts.append("LIMIT ?")
                params.append(limit)

            cursor = conn.execute(" ".join(query_parts), params)
            messages: List[BridgeMessage] = []
            for row in cursor.fetchall():
                try:
                    ts = datetime.fromisoformat(str(row["timestamp"]))
                except (ValueError, TypeError):
                    logger.warning(
                        "Skipping message %s: unparseable timestamp %s",
                        row["id"],
                        row["timestamp"],
                    )
                    continue

                messages.append(
                    BridgeMessage(
                        id=row["id"],
                        chat_jid=row["chat_jid"],
                        sender=row["sender"] or "",
                        content=row["content"] or "",
                        timestamp=ts,
                        is_from_me=bool(row["is_from_me"]),
                        media_type=row["media_type"] or None,
                        filename=row["filename"] or None,
                    )
                )
            return messages
        finally:
            conn.close()

    def get_sender_name(self, sender_value: str) -> str:
        """
        Resolve a sender identifier to a human-readable display name.

        Resolution strategy (mirrors the MCP Python server):
        1. Exact JID match in the ``chats`` table.
        2. Extract the phone-number portion and LIKE-match.
        3. Fall back to the raw sender value.

        Results are cached in memory for the lifetime of this reader.

        Args:
            sender_value: A phone number (``"447837370336"``) or a full
                JID (``"447837370336@s.whatsapp.net"``).

        Returns:
            The resolved display name, or the raw sender value if
            resolution fails.
        """
        if sender_value in self._name_cache:
            return self._name_cache[sender_value]

        resolved = self._resolve_sender_name(sender_value)
        self._name_cache[sender_value] = resolved
        return resolved

    def download_media(
        self, message_id: str, chat_jid: str
    ) -> Optional[Path]:
        """
        Locate a previously-downloaded media file on disk.

        The Go bridge stores downloaded media at::

            store/{chat_jid_sanitised}/{filename}

        where the JID is sanitised by replacing ``@`` and ``.`` with
        underscores.

        Args:
            message_id: The WhatsApp message ID.
            chat_jid: The chat JID the message belongs to.

        Returns:
            Path to the media file if it exists on disk, or None.
        """
        # Look up the filename for this message
        try:
            conn = self._connect()
        except BridgeReaderError:
            return None

        try:
            cursor = conn.execute(
                "SELECT filename FROM messages "
                "WHERE id = ? AND chat_jid = ?",
                (message_id, chat_jid),
            )
            row = cursor.fetchone()
            if not row or not row["filename"]:
                return None

            filename = row["filename"]
        finally:
            conn.close()

        # Construct the expected path
        sanitised_jid = chat_jid.replace("@", "_").replace(".", "_")
        media_path = self.store_dir / sanitised_jid / filename

        if media_path.exists():
            return media_path

        # Also try without JID subdirectory (some bridge versions)
        flat_path = self.store_dir / filename
        if flat_path.exists():
            return flat_path

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_sender_name(self, sender_value: str) -> str:
        """Resolve sender to display name by querying the chats table."""
        try:
            conn = self._connect()
        except BridgeReaderError:
            return sender_value

        try:
            # Strategy 1: exact JID match
            cursor = conn.execute(
                "SELECT name FROM chats WHERE jid = ? LIMIT 1",
                (sender_value,),
            )
            row = cursor.fetchone()
            if row and row["name"]:
                return row["name"]

            # Strategy 2: extract phone part and LIKE match
            if "@" in sender_value:
                phone_part = sender_value.split("@")[0]
            else:
                phone_part = sender_value

            cursor = conn.execute(
                "SELECT name FROM chats WHERE jid LIKE ? LIMIT 1",
                (f"%{phone_part}%",),
            )
            row = cursor.fetchone()
            if row and row["name"]:
                return row["name"]

            # Strategy 3: fall back to raw value
            return sender_value
        except sqlite3.Error:
            return sender_value
        finally:
            conn.close()
