"""
Transcript data source for WhatsApp Chat Auto-Export.

Reads existing vault transcripts — both the legacy ``.txt`` format produced
by the original Appium pipeline and the new ``.md`` format defined in the
transcript format spec — into the unified Message model.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..processing.transcript_parser import Message, TranscriptParser
from ..utils.logger import Logger
from .base import ChatInfo, MessageSource


# New .md spec format: [HH:MM] Sender: content
_MD_MESSAGE_RE = re.compile(
    r'^\[(\d{2}:\d{2})\]\s+(.+?):\s(.*)$'
)

# Day header in .md spec format: ## YYYY-MM-DD
_MD_DAY_HEADER_RE = re.compile(
    r'^##\s+(\d{4}-\d{2}-\d{2})\s*$'
)

# System event in .md spec format: [HH:MM] event text (no colon-separated sender)
_MD_SYSTEM_RE = re.compile(
    r'^\[(\d{2}:\d{2})\]\s+(.+)$'
)


class TranscriptSource(MessageSource):
    """
    MessageSource that reads existing vault transcript files.

    Supports two formats:

    1. **Legacy (.txt)** — the WhatsApp export format parsed by
       ``TranscriptParser`` (``M/D/YY, H:MM AM/PM - Sender: content``).
    2. **New (.md)** — the spec format with YAML frontmatter, day headers
       (``## YYYY-MM-DD``), and ``[HH:MM] Sender: content`` lines.

    The source auto-detects the format based on file extension and content.
    """

    def __init__(
        self,
        transcript_dir: Path,
        logger: Optional[Logger] = None,
    ):
        """
        Initialize the transcript source.

        Args:
            transcript_dir: Root directory containing transcript files
                (or chat sub-directories each containing a transcript file)
            logger: Optional logger for output
        """
        super().__init__(logger=logger or Logger())
        self.transcript_dir = transcript_dir
        self._parser = TranscriptParser(logger=self.logger)
        # Cache: chat_id -> messages
        self._cache: Dict[str, List[Message]] = {}

    def get_chats(self) -> List[ChatInfo]:
        """
        List all chats found under the transcript directory.

        Looks for transcript files in two layouts:

        - Flat: ``transcript_dir/*.txt`` / ``transcript_dir/*.md``
        - Nested: ``transcript_dir/<chat>/transcript.txt`` or
          ``transcript_dir/<chat>/transcript.md``
        """
        chats: List[ChatInfo] = []

        if not self.transcript_dir.is_dir():
            self.log_error(f"Transcript directory not found: {self.transcript_dir}")
            return chats

        seen: set = set()

        # Nested layout: sub-dirs with transcript files
        for child in sorted(self.transcript_dir.iterdir()):
            if not child.is_dir():
                continue

            transcript = self._find_transcript_in(child)
            if transcript is None:
                continue

            chat_name = child.name
            if chat_name in seen:
                continue
            seen.add(chat_name)

            messages = self._load_messages(chat_name, transcript)
            last_time = messages[-1].timestamp if messages else None

            chats.append(
                ChatInfo(
                    jid=chat_name,
                    name=chat_name,
                    last_message_time=last_time,
                    message_count=len(messages),
                )
            )

        # Flat layout: transcript files directly in the root
        for candidate in sorted(self.transcript_dir.glob("*.txt")):
            chat_name = candidate.stem
            if chat_name in seen:
                continue
            seen.add(chat_name)

            messages = self._load_messages(chat_name, candidate)
            last_time = messages[-1].timestamp if messages else None

            chats.append(
                ChatInfo(
                    jid=chat_name,
                    name=chat_name,
                    last_message_time=last_time,
                    message_count=len(messages),
                )
            )

        for candidate in sorted(self.transcript_dir.glob("*.md")):
            chat_name = candidate.stem
            if chat_name in seen:
                continue
            seen.add(chat_name)

            messages = self._load_messages(chat_name, candidate)
            last_time = messages[-1].timestamp if messages else None

            chats.append(
                ChatInfo(
                    jid=chat_name,
                    name=chat_name,
                    last_message_time=last_time,
                    message_count=len(messages),
                )
            )

        self.log_info(f"Found {len(chats)} chats in transcript directory")
        return chats

    def get_messages(
        self,
        chat_id: str,
        after: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Message]:
        """
        Retrieve messages for a chat from an existing transcript.

        Args:
            chat_id: Chat identifier (directory name or file stem)
            after: If set, only return messages after this timestamp
            limit: If set, return at most this many messages
        """
        if chat_id not in self._cache:
            transcript = self._resolve_transcript(chat_id)
            if transcript is None:
                self.log_warning(f"No transcript found for chat: {chat_id}")
                return []
            self._load_messages(chat_id, transcript)

        messages = list(self._cache.get(chat_id, []))

        if after is not None:
            messages = [m for m in messages if m.timestamp > after]

        if limit is not None:
            messages = messages[:limit]

        return messages

    def get_media(self, message_id: str) -> Optional[Path]:
        """
        Media lookup is not supported for transcript sources.
        """
        return None

    # ----- internal helpers -----

    def _find_transcript_in(self, directory: Path) -> Optional[Path]:
        """Find a transcript file inside a chat directory."""
        # Prefer the new spec format
        for name in ("transcript.md", "transcript.txt"):
            candidate = directory / name
            if candidate.is_file():
                return candidate

        # Fall back to any .txt file
        for candidate in sorted(directory.glob("*.txt")):
            if candidate.is_file():
                return candidate

        # Fall back to any .md file (skip index.md)
        for candidate in sorted(directory.glob("*.md")):
            if candidate.is_file() and candidate.name != "index.md":
                return candidate

        return None

    def _resolve_transcript(self, chat_id: str) -> Optional[Path]:
        """Resolve a chat_id to a transcript file path."""
        # Nested layout
        nested = self.transcript_dir / chat_id
        if nested.is_dir():
            found = self._find_transcript_in(nested)
            if found:
                return found

        # Flat layout
        for ext in (".md", ".txt"):
            flat = self.transcript_dir / f"{chat_id}{ext}"
            if flat.is_file():
                return flat

        return None

    def _load_messages(
        self, chat_id: str, transcript: Path
    ) -> List[Message]:
        """Load and cache messages from a transcript file."""
        if chat_id in self._cache:
            return self._cache[chat_id]

        if transcript.suffix == ".md":
            messages = self._parse_md_transcript(transcript)
        else:
            messages, _ = self._parser.parse_transcript(transcript)
            for msg in messages:
                msg.source = "transcript"

        self._cache[chat_id] = messages
        return messages

    def _parse_md_transcript(self, path: Path) -> List[Message]:
        """
        Parse a new-format ``.md`` transcript.

        Expected structure::

            ---
            cssclasses: [whatsapp-transcript, exclude-from-graph]
            ---
            <!-- integrity: ... -->

            ## 2024-06-15

            [10:30] Alice: Hello!
            [10:31] Bob: Hi there
        """
        messages: List[Message] = []

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            self.log_error(f"Error reading transcript: {e}")
            return messages

        current_date: Optional[str] = None
        in_frontmatter = False
        line_num = 0

        for line in text.splitlines():
            line_num += 1
            stripped = line.rstrip()

            # Skip YAML frontmatter
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue

            # Skip blank lines and HTML comments
            if not stripped or stripped.startswith("<!--"):
                continue

            # Day header
            day_match = _MD_DAY_HEADER_RE.match(stripped)
            if day_match:
                current_date = day_match.group(1)
                continue

            if current_date is None:
                # Haven't hit a day header yet — skip preamble
                continue

            # Message line
            msg_match = _MD_MESSAGE_RE.match(stripped)
            if msg_match:
                time_str = msg_match.group(1)
                sender = msg_match.group(2)
                content = msg_match.group(3)

                timestamp = self._build_timestamp(current_date, time_str)
                if timestamp is None:
                    continue

                is_media, media_type = self._detect_md_media(content)

                messages.append(
                    Message(
                        timestamp=timestamp,
                        sender=sender,
                        content=content,
                        is_media=is_media,
                        media_type=media_type,
                        raw_line=stripped,
                        line_number=line_num,
                        source="transcript",
                    )
                )
                continue

            # Continuation line (belongs to previous message)
            if messages:
                messages[-1].content += "\n" + stripped

        self.log_info(
            f"Parsed {len(messages)} messages from .md transcript: {path.name}"
        )
        return messages

    @staticmethod
    def _build_timestamp(date_str: str, time_str: str) -> Optional[datetime]:
        """Combine a YYYY-MM-DD date and HH:MM time into a datetime."""
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    @staticmethod
    def _detect_md_media(content: str) -> Tuple[bool, Optional[str]]:
        """
        Detect typed media tags in new-format transcripts.

        Tags: ``<photo>``, ``<video>``, ``<voice>``, ``<document>``, ``<sticker>``
        """
        tag_map = {
            "<photo>": "image",
            "<video>": "video",
            "<voice>": "audio",
            "<document>": "document",
            "<sticker>": "sticker",
        }
        content_stripped = content.strip()
        for tag, media_type in tag_map.items():
            if content_stripped.startswith(tag):
                return True, media_type
        return False, None
