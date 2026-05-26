"""
Incremental sync state management for MCP bridge integration.

Manages per-chat watermarks, a contact name cache, and a voice-message
retry queue. State is persisted as versioned JSON with atomic writes
(write to ``.tmp`` then ``os.rename``). Corrupted state files are
handled gracefully by reinitialising to defaults with a warning.
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Current schema version — bump when the JSON shape changes
STATE_VERSION = 1

# Default state file location
DEFAULT_STATE_PATH = Path.home() / ".whatsapp-sync" / "state.json"


@dataclass
class VoiceRetryItem:
    """A voice message that needs transcription retry."""
    message_id: str
    chat_jid: str
    timestamp: str  # ISO-8601 string
    attempts: int = 0
    last_attempt: Optional[str] = None  # ISO-8601 string


@dataclass
class MCPState:
    """
    Persistent state for MCP incremental sync.

    Attributes:
        version: Schema version for forward-compatibility checks.
        watermarks: Per-chat high-water marks keyed by JID. Values are
            ISO-8601 timestamp strings representing the newest message
            timestamp that has been synced for that chat.
        contact_cache: Mapping of sender identifier to resolved display
            name, persisted across runs to avoid repeated DB lookups.
        voice_retry_queue: List of voice messages whose transcription
            failed and should be retried on the next sync run.
        last_sync: ISO-8601 timestamp of the most recent sync run.
    """
    version: int = STATE_VERSION
    watermarks: Dict[str, str] = field(default_factory=dict)
    contact_cache: Dict[str, str] = field(default_factory=dict)
    voice_retry_queue: List[VoiceRetryItem] = field(default_factory=list)
    last_sync: Optional[str] = None

    # ------------------------------------------------------------------
    # Watermark helpers
    # ------------------------------------------------------------------

    def get_watermark(self, jid: str) -> Optional[datetime]:
        """
        Get the high-water mark for a chat.

        Returns:
            The watermark as a datetime, or None if no watermark exists.
        """
        ts_str = self.watermarks.get(jid)
        if ts_str is None:
            return None
        try:
            return datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            logger.warning("Corrupt watermark for %s: %s", jid, ts_str)
            return None

    def set_watermark(self, jid: str, timestamp: datetime) -> None:
        """Set the high-water mark for a chat."""
        self.watermarks[jid] = timestamp.isoformat()

    # ------------------------------------------------------------------
    # Contact cache helpers
    # ------------------------------------------------------------------

    def get_contact_name(self, sender: str) -> Optional[str]:
        """Look up a cached contact name."""
        return self.contact_cache.get(sender)

    def set_contact_name(self, sender: str, name: str) -> None:
        """Cache a resolved contact name."""
        self.contact_cache[sender] = name

    # ------------------------------------------------------------------
    # Voice retry queue helpers
    # ------------------------------------------------------------------

    def add_voice_retry(
        self, message_id: str, chat_jid: str, timestamp: datetime
    ) -> None:
        """Add a voice message to the retry queue."""
        # Don't add duplicates
        for item in self.voice_retry_queue:
            if item.message_id == message_id and item.chat_jid == chat_jid:
                return
        self.voice_retry_queue.append(
            VoiceRetryItem(
                message_id=message_id,
                chat_jid=chat_jid,
                timestamp=timestamp.isoformat(),
            )
        )

    def pop_voice_retries(self, max_attempts: int = 3) -> List[VoiceRetryItem]:
        """
        Return and remove retry items that have not exceeded max_attempts.

        Items that have reached max_attempts are silently discarded.

        Returns:
            List of VoiceRetryItem objects to retry.
        """
        eligible = []
        remaining = []
        for item in self.voice_retry_queue:
            if item.attempts < max_attempts:
                item.attempts += 1
                item.last_attempt = datetime.now().isoformat()
                eligible.append(item)
            else:
                logger.info(
                    "Dropping voice retry for %s after %d attempts",
                    item.message_id,
                    item.attempts,
                )
        self.voice_retry_queue = remaining
        return eligible

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise state to a JSON-compatible dictionary."""
        return {
            "version": self.version,
            "watermarks": self.watermarks,
            "contact_cache": self.contact_cache,
            "voice_retry_queue": [asdict(item) for item in self.voice_retry_queue],
            "last_sync": self.last_sync,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPState":
        """
        Deserialise state from a dictionary.

        Handles missing keys gracefully so that older state files can
        be loaded without error.
        """
        retry_items = []
        for item_data in data.get("voice_retry_queue", []):
            retry_items.append(
                VoiceRetryItem(
                    message_id=item_data["message_id"],
                    chat_jid=item_data["chat_jid"],
                    timestamp=item_data["timestamp"],
                    attempts=item_data.get("attempts", 0),
                    last_attempt=item_data.get("last_attempt"),
                )
            )

        return cls(
            version=data.get("version", STATE_VERSION),
            watermarks=data.get("watermarks", {}),
            contact_cache=data.get("contact_cache", {}),
            voice_retry_queue=retry_items,
            last_sync=data.get("last_sync"),
        )

    # ------------------------------------------------------------------
    # Persistence (atomic file I/O)
    # ------------------------------------------------------------------

    def save(self, path: Optional[Path] = None) -> None:
        """
        Persist state to disk with an atomic write.

        Writes to a temporary file alongside the target, then renames
        it into place. This ensures that a crash mid-write never leaves
        a corrupted state file.

        Args:
            path: File path to write. Defaults to DEFAULT_STATE_PATH.
        """
        path = Path(path) if path else DEFAULT_STATE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)

        self.last_sync = datetime.now().isoformat()

        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.rename(str(tmp_path), str(path))
            logger.debug("State saved to %s", path)
        except OSError as exc:
            logger.error("Failed to save state to %s: %s", path, exc)
            # Clean up temp file if rename failed
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "MCPState":
        """
        Load state from disk, with graceful degradation on corruption.

        If the file does not exist, returns a fresh default state.
        If the file is corrupt (invalid JSON, wrong type, etc.), logs a
        warning and returns a fresh default state.

        Args:
            path: File path to read. Defaults to DEFAULT_STATE_PATH.

        Returns:
            An MCPState instance.
        """
        path = Path(path) if path else DEFAULT_STATE_PATH

        if not path.exists():
            logger.debug("No state file at %s — starting fresh", path)
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError(
                    f"Expected dict at top level, got {type(data).__name__}"
                )

            state = cls.from_dict(data)

            # Version check — for now we only have v1, but future
            # migrations would go here
            if state.version > STATE_VERSION:
                logger.warning(
                    "State file version %d is newer than supported %d — "
                    "proceeding with best effort",
                    state.version,
                    STATE_VERSION,
                )

            return state

        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Corrupt state file at %s (%s) — reinitialising", path, exc
            )
            return cls()
