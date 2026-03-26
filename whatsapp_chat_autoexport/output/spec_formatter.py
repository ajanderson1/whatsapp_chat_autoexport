"""
Spec Formatter module for WhatsApp Chat Auto-Export.

Produces transcript.md files conforming to the format specification
defined in docs/specs/transcript-format-spec.md.

Pure formatting logic: Message list -> formatted transcript content.
"""

import hashlib
import re
from collections import OrderedDict
from datetime import datetime
from typing import List, Optional

from ..processing.transcript_parser import Message


# Auto-generated filename patterns — these are noise in the transcript
_AUTO_FILENAME_RE = re.compile(
    r'^(IMG|VID|PTT|AUD|STK|DOC)-\d{8}-WA\d{4}\.\w+$',
    re.IGNORECASE,
)

# Media type mapping from Message.media_type to spec tag names
_MEDIA_TYPE_TAG = {
    'image': 'photo',
    'audio': 'voice',      # default for audio; caller can override
    'video': 'video',
    'document': 'document',
    'sticker': 'sticker',
    'gif': 'gif',
}

# System message patterns — messages from WhatsApp itself (no real sender)
_SYSTEM_PATTERNS = [
    'Messages and calls are end-to-end encrypted',
    'Your security code with',
    'changed their phone number',
    'was added',
    'was removed',
    'left',
    'joined using this group',
    'created group',
    'changed the group',
    'changed this group',
    'changed the subject',
    'changed the description',
    'turned on disappearing messages',
    'turned off disappearing messages',
    'pinned a message',
    'deleted this group',
    'Tap to learn more',
    'You were added',
    'You joined using',
    'This message was deleted',
    'Waiting for this message',
    'added you',
]

# Compiled pattern for quick system-message detection
_SYSTEM_RE = re.compile(
    '|'.join(re.escape(p) for p in _SYSTEM_PATTERNS),
    re.IGNORECASE,
)


class SpecFormatter:
    """
    Formats Message objects into the canonical transcript.md format.

    Produces output matching docs/specs/transcript-format-spec.md:
    - Minimal YAML frontmatter with cssclasses
    - HTML comment integrity header
    - Messages grouped by day with ## YYYY-MM-DD headers
    - Typed media tags, voice transcriptions, system events
    """

    GENERATOR_VERSION = "wa-sync/1.0.0"

    def __init__(self, user_display_name: str = "AJ Anderson"):
        """
        Initialise the formatter.

        Args:
            user_display_name: Display name to use for is_from_me messages.
        """
        self.user_display_name = user_display_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_transcript(
        self,
        messages: List[Message],
        chat_jid: str,
        contact_name: str,
    ) -> str:
        """
        Format a complete transcript.md file.

        Args:
            messages: Chronologically ordered list of Message objects.
            chat_jid: WhatsApp JID for this chat.
            contact_name: Display name for the chat contact.

        Returns:
            Full transcript.md content as a string.
        """
        body = self.format_messages_only(messages)
        body_hash = self._sha256(body)

        # Gather stats
        message_count = len(messages)
        media_count = sum(1 for m in messages if m.is_media)
        date_range = self._date_range(messages)

        # Build the complete file
        parts = [
            self._build_frontmatter(),
            "",
            self._build_integrity_header(
                chat_jid=chat_jid,
                contact_name=contact_name,
                message_count=message_count,
                media_count=media_count,
                date_range=date_range,
                body_sha256=body_hash,
            ),
            "",
            body,
        ]
        return "\n".join(parts)

    def format_messages_only(self, messages: List[Message]) -> str:
        """
        Format the day-grouped message body without frontmatter or header.

        This is the content whose SHA-256 becomes body_sha256 in the
        integrity header.

        Args:
            messages: Chronologically ordered list of Message objects.

        Returns:
            Formatted message body string.
        """
        if not messages:
            return ""

        lines: List[str] = []
        current_date: Optional[str] = None

        i = 0
        while i < len(messages):
            msg = messages[i]
            msg_date = msg.timestamp.strftime("%Y-%m-%d")

            # Day header
            if msg_date != current_date:
                if current_date is not None:
                    # Blank line before new day header
                    lines.append("")
                lines.append(f"## {msg_date}")
                lines.append("")
                current_date = msg_date

            # Format the message line(s)
            formatted = self._format_message(msg)
            lines.append(formatted)

            # Check for voice transcription on the next message
            # Convention: a transcription is stored as the next Message
            # with content starting with "[Transcription]:" or as an
            # attribute.  We also handle inline transcription content
            # attached to the voice message itself.
            if msg.is_media and self._is_voice(msg):
                transcription = self._extract_transcription(msg, messages, i)
                if transcription:
                    lines.append(f"  [Transcription]: {transcription}")

            i += 1

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_message(self, msg: Message) -> str:
        """Format a single message line."""
        time_str = msg.timestamp.strftime("%H:%M")

        if self._is_system_message(msg):
            return f"[{time_str}] {msg.content}"

        sender = self._resolve_sender(msg)

        if msg.is_media:
            content = self._format_media_content(msg)
        else:
            content = self._format_text_content(msg.content)

        return f"[{time_str}] {sender}: {content}"

    def _is_system_message(self, msg: Message) -> bool:
        """Detect system/event messages (no real sender)."""
        if not msg.sender or msg.sender.strip() == "":
            return True
        # Some parsers put the system text in sender field
        if _SYSTEM_RE.search(msg.sender):
            return True
        # Check content for system patterns when sender looks like system text
        if _SYSTEM_RE.search(msg.content) and not self._looks_like_person_name(msg.sender):
            # Only treat as system if sender is clearly not a person
            pass
        return False

    def _looks_like_person_name(self, sender: str) -> bool:
        """Heuristic: does this sender look like a real person name?"""
        # Phone numbers
        if re.match(r'^\+?\d[\d\s-]{6,}$', sender.strip()):
            return True  # Phone numbers are valid senders
        # Names typically have letters
        if re.search(r'[a-zA-Z]', sender):
            return True
        return False

    def _resolve_sender(self, msg: Message) -> str:
        """Resolve the display name for a message sender."""
        # For is_from_me, some sources may set sender to empty or "Me"
        if hasattr(msg, 'is_from_me') and getattr(msg, 'is_from_me', False):
            return self.user_display_name
        if msg.sender.lower() in ("me", "you"):
            return self.user_display_name
        return msg.sender

    def _format_media_content(self, msg: Message) -> str:
        """Format media message content with typed tags."""
        tag = self._media_tag(msg)
        filename = self._extract_filename(msg.content)

        # Check for view-once
        if self._is_view_once(msg):
            return f"<view-once {tag}>"

        # Include filename only for documents with descriptive names
        if filename and msg.media_type == 'document' and not _AUTO_FILENAME_RE.match(filename):
            return f"<{tag} {filename}>"

        # For photos/images, include filename if it exists and is not auto-generated
        if filename and not _AUTO_FILENAME_RE.match(filename):
            # Only include for document type; for others, skip auto-names
            if msg.media_type == 'document':
                return f"<{tag} {filename}>"

        return f"<{tag}>"

    def _media_tag(self, msg: Message) -> str:
        """Get the spec media tag name from the message media_type."""
        if msg.media_type:
            return _MEDIA_TYPE_TAG.get(msg.media_type, 'media')
        return 'media'

    def _is_voice(self, msg: Message) -> bool:
        """Check if a media message is a voice message."""
        if msg.media_type == 'audio':
            return True
        content_lower = msg.content.lower()
        if 'ptt' in content_lower or 'voice' in content_lower or 'opus' in content_lower:
            return True
        return False

    def _is_view_once(self, msg: Message) -> bool:
        """Check if a message is a view-once message."""
        content_lower = msg.content.lower()
        return 'view once' in content_lower or 'view-once' in content_lower

    def _extract_filename(self, content: str) -> Optional[str]:
        """Extract filename from message content if present."""
        # Pattern: "filename.ext (file attached)"
        match = re.search(r'(.+?\.\w+)\s*\(file attached\)', content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Pattern: "filename.ext" at the end or standalone
        match = re.search(r'([\w\-]+\.\w{2,5})$', content.strip())
        if match:
            return match.group(1)
        return None

    def _extract_transcription(
        self,
        voice_msg: Message,
        messages: List[Message],
        index: int,
    ) -> Optional[str]:
        """
        Extract transcription text for a voice message.

        Looks for transcription in:
        1. The next message if it starts with [Transcription]:
        2. An inline transcription marker in the voice message content
        """
        # Check if transcription is embedded in the content itself
        content = voice_msg.content
        transcription_match = re.search(
            r'\[Transcription\]:\s*(.+)',
            content,
            re.IGNORECASE,
        )
        if transcription_match:
            return transcription_match.group(1).strip()

        # Check the next message for inline transcription
        if index + 1 < len(messages):
            next_msg = messages[index + 1]
            if next_msg.content.strip().startswith('[Transcription]:'):
                text = next_msg.content.strip()[len('[Transcription]:'):].strip()
                return text if text else None

        return None

    def _format_text_content(self, content: str) -> str:
        """
        Format text content, handling multi-line messages.

        Multi-line messages: first line gets the [HH:MM] Sender: prefix,
        continuation lines are bare (no prefix).
        """
        # Content may already contain newlines from the parser
        # We just return it as-is — the caller adds the prefix for line 1
        return content

    # ------------------------------------------------------------------
    # Header / frontmatter builders
    # ------------------------------------------------------------------

    def _build_frontmatter(self) -> str:
        """Build the minimal YAML frontmatter block."""
        return (
            "---\n"
            "cssclasses:\n"
            "  - whatsapp-transcript\n"
            "  - exclude-from-graph\n"
            "---"
        )

    def _build_integrity_header(
        self,
        chat_jid: str,
        contact_name: str,
        message_count: int,
        media_count: int,
        date_range: str,
        body_sha256: str,
    ) -> str:
        """Build the HTML comment integrity header."""
        generated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            f"<!-- TRANSCRIPT METADATA\n"
            f"chat_jid: {chat_jid}\n"
            f"contact: {contact_name}\n"
            f"generated: {generated}\n"
            f"generator: {self.GENERATOR_VERSION}\n"
            f"message_count: {message_count}\n"
            f"media_count: {media_count}\n"
            f"date_range: {date_range}\n"
            f"body_sha256: {body_sha256}\n"
            f"-->"
        )

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def _date_range(self, messages: List[Message]) -> str:
        """Compute the date range string 'YYYY-MM-DD..YYYY-MM-DD'."""
        if not messages:
            return "none"
        first = messages[0].timestamp.strftime("%Y-%m-%d")
        last = messages[-1].timestamp.strftime("%Y-%m-%d")
        return f"{first}..{last}"

    @staticmethod
    def _sha256(content: str) -> str:
        """Compute SHA-256 hex digest of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
