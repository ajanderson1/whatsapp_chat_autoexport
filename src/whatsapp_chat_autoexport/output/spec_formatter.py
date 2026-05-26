"""
SpecFormatter — generates transcript.md content conforming to the
WhatsApp Transcript Format Spec.

Usage::

    formatter = SpecFormatter(
        contact_name="Tim Cocking",
        chat_jid="447956173473@s.whatsapp.net",
    )
    md_text = formatter.format_transcript(messages)
"""

from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..processing.transcript_parser import Message


# Map from Message.media_type to the spec tag (excluding document, handled separately)
_MEDIA_TAG = {
    "image": "photo",
    "audio": "voice",
    "video": "video",
    "sticker": "sticker",
}


class SpecFormatter:
    """
    Formats a list of WhatsApp Message objects into a transcript.md string
    conforming to the WhatsApp Transcript Format Spec.

    Parameters
    ----------
    contact_name:
        Display name for the contact / chat.
    chat_jid:
        WhatsApp JID (e.g. ``447956173473@s.whatsapp.net``).  May be ``None``.
    chat_type:
        ``"direct"`` or ``"group"``.
    participants:
        Optional list of participant names (used for group chats).
    timezone:
        IANA timezone label stored in metadata (default ``"Europe/Stockholm"``).
    """

    def __init__(
        self,
        contact_name: str,
        chat_jid: Optional[str] = None,
        chat_type: str = "direct",
        participants: Optional[List[str]] = None,
        timezone: str = "Europe/Stockholm",
    ) -> None:
        self.contact_name = contact_name
        self.chat_jid = chat_jid
        self.chat_type = chat_type
        self.participants = participants or []
        self.timezone = timezone

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_index(self, messages: List[Message]) -> str:
        """
        Return complete index.md content for *messages*.

        The index.md is a companion note to the transcript that stores metadata,
        counts, provenance, and a summary in YAML frontmatter plus a short body.

        Parameters
        ----------
        messages:
            Ordered list of Message objects.

        Returns
        -------
        str
            Full Markdown string ready to be written to ``index.md``.
        """
        now = datetime.now(tz=timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        last_synced_str = now.strftime("%Y-%m-%dT%H:%M:%S")

        message_count = len(messages)
        media_count = sum(1 for m in messages if m.is_media)
        voice_count = sum(1 for m in messages if m.is_media and m.media_type == "audio")

        if messages:
            date_first = messages[0].timestamp.date().isoformat()
            date_last = messages[-1].timestamp.date().isoformat()
        else:
            date_first = today_str
            date_last = today_str

        # Build description based on chat type
        if self.chat_type == "group":
            description = f'WhatsApp group chat: {self.contact_name}'
        else:
            description = f'WhatsApp correspondence with {self.contact_name}'

        lines: List[str] = ["---"]
        lines.append("type: note")
        lines.append(f'description: "{description}"')
        lines.append("tags:")
        lines.append("  - whatsapp")
        lines.append("  - correspondence")
        lines.append("cssclasses:")
        lines.append("  - whatsapp-chat")
        lines.append("")

        lines.append(f"chat_type: {self.chat_type}")

        if self.chat_type == "group":
            lines.append(f"chat_name: {self.contact_name}")
            lines.append("participants:")
            for participant in self.participants:
                lines.append(f'  - "[[{participant}]]"')
        else:
            lines.append(f'contact: "[[{self.contact_name}]]"')
            if self.chat_jid:
                lines.append(f"jid: {self.chat_jid}")

        lines.append("")
        lines.append(f"message_count: {message_count}")
        lines.append(f"media_count: {media_count}")
        lines.append(f"voice_count: {voice_count}")
        lines.append(f"date_first: {date_first}")
        lines.append(f"date_last: {date_last}")
        lines.append(f"last_synced: {last_synced_str}")
        lines.append("")
        lines.append("sources:")
        lines.append("  - type: appium_export")
        lines.append(f"    date: {today_str}")
        lines.append(f"    messages: {message_count}")
        lines.append("coverage_gaps: 0")
        lines.append("")
        lines.append(f"timezone: {self.timezone}")
        lines.append("---")

        # Body
        if self.chat_type == "group":
            summary = f"> WhatsApp group chat: [[{self.contact_name}]]"
        else:
            summary = f"> WhatsApp correspondence with [[{self.contact_name}]]"

        period_line = f"> Period: {date_first} to {date_last} | {message_count:,} messages"

        if self.chat_type == "group":
            transcript_link = (
                f"[[People/Correspondence/Whatsapp/{self.contact_name}/transcript|Full Transcript]]"
            )
        else:
            transcript_link = (
                f"[[People/Correspondence/Whatsapp/{self.contact_name}/transcript|Full Transcript]]"
            )

        body_parts = [summary, period_line, "", transcript_link]
        body = "\n".join(body_parts)

        frontmatter = "\n".join(lines)
        return frontmatter + "\n\n" + body + "\n"

    def format_transcript(self, messages: List[Message], media_dir: Optional[Path] = None) -> str:
        """
        Return complete transcript.md content for *messages*.

        Parameters
        ----------
        messages:
            Ordered list of Message objects.
        media_dir:
            Optional path to a directory containing ``*_transcription.txt``
            files for voice messages.  When provided, each voice message line
            is followed by an indented ``[Transcription]: …`` line.

        Returns
        -------
        str
            Full Markdown string ready to be written to ``transcript.md``.
        """
        frontmatter = self._build_frontmatter()
        body = self._format_message_body(messages, media_dir=media_dir)
        metadata = self._build_metadata(messages, body)

        parts = [frontmatter, metadata]
        if body:
            parts.append(body)

        return "\n".join(parts) + "\n"

    def build_output(
        self,
        messages: List[Message],
        dest_dir: Path,
        media_dir: Optional[Path] = None,
        include_transcriptions: bool = True,
        copy_media: bool = True,
    ) -> dict:
        """
        Build a complete output directory for a chat.

        Creates the following structure under *dest_dir*::

            dest_dir/<contact_name>/
                index.md
                transcript.md
                transcriptions/   (if include_transcriptions and transcription files exist)
                media/            (if copy_media and non-transcription media files exist)

        Parameters
        ----------
        messages:
            Ordered list of Message objects.
        dest_dir:
            Parent directory under which the contact sub-directory is created.
        media_dir:
            Optional path to a directory containing media and transcription files.
            When provided, files are conditionally copied to the output.
        include_transcriptions:
            When True (default), copy ``*_transcription.txt`` files from *media_dir*
            to a ``transcriptions/`` sub-directory.  Existing files are skipped.
        copy_media:
            When True (default), copy non-transcription files from *media_dir* to a
            ``media/`` sub-directory.  Existing files are skipped.

        Returns
        -------
        dict
            Summary dictionary with the following keys:

            - ``contact_name`` (str)
            - ``output_dir`` (Path): the contact sub-directory created
            - ``transcript_path`` (Path)
            - ``index_path`` (Path)
            - ``total_messages`` (int)
            - ``media_messages`` (int)
            - ``media_copied`` (int)
            - ``transcriptions_copied`` (int)
        """
        contact_dir = dest_dir / self.contact_name
        contact_dir.mkdir(parents=True, exist_ok=True)

        # Write transcript.md
        transcript_content = self.format_transcript(messages, media_dir=media_dir)
        transcript_path = contact_dir / "transcript.md"
        transcript_path.write_text(transcript_content, encoding="utf-8")

        # Write index.md
        index_content = self.format_index(messages)
        index_path = contact_dir / "index.md"
        index_path.write_text(index_content, encoding="utf-8")

        media_copied = 0
        transcriptions_copied = 0

        if media_dir is not None and media_dir.is_dir():
            media_files = list(media_dir.iterdir())

            if include_transcriptions:
                transcription_files = [
                    f for f in media_files
                    if f.is_file() and f.name.endswith("_transcription.txt")
                ]
                if transcription_files:
                    transcriptions_dir = contact_dir / "transcriptions"
                    transcriptions_dir.mkdir(exist_ok=True)
                    for src in transcription_files:
                        dest = transcriptions_dir / src.name
                        if not dest.exists():
                            shutil.copy2(src, dest)
                            transcriptions_copied += 1

            if copy_media:
                non_transcription_files = [
                    f for f in media_files
                    if f.is_file() and not f.name.endswith("_transcription.txt")
                ]
                if non_transcription_files:
                    media_out_dir = contact_dir / "media"
                    media_out_dir.mkdir(exist_ok=True)
                    for src in non_transcription_files:
                        dest = media_out_dir / src.name
                        if not dest.exists():
                            shutil.copy2(src, dest)
                            media_copied += 1

        total_messages = len(messages)
        media_messages = sum(1 for m in messages if m.is_media)

        return {
            "contact_name": self.contact_name,
            "output_dir": contact_dir,
            "transcript_path": transcript_path,
            "index_path": index_path,
            "total_messages": total_messages,
            "media_messages": media_messages,
            "media_copied": media_copied,
            "transcriptions_copied": transcriptions_copied,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_frontmatter(self) -> str:
        return (
            "---\n"
            "cssclasses:\n"
            "  - whatsapp-transcript\n"
            "  - exclude-from-graph\n"
            "---"
        )

    def _build_metadata(self, messages: List[Message], body: str = "") -> str:
        generated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        message_count = len(messages)
        media_count = sum(1 for m in messages if m.is_media)

        if messages:
            first_date = messages[0].timestamp.date().isoformat()
            last_date = messages[-1].timestamp.date().isoformat()
            date_range = f"{first_date}..{last_date}"
        else:
            date_range = ""

        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()

        chat_jid_line = f"chat_jid: {self.chat_jid}" if self.chat_jid else "chat_jid:"

        lines = [
            "<!-- TRANSCRIPT METADATA",
            chat_jid_line,
            f"contact: {self.contact_name}",
            f"generated: {generated}",
            "generator: whatsapp-export/spec",
            f"message_count: {message_count}",
            f"media_count: {media_count}",
            f"date_range: {date_range}",
            f"body_sha256: {body_sha256}",
            "-->",
        ]
        return "\n".join(lines)

    def _format_message_body(self, messages: List[Message], media_dir: Optional[Path] = None) -> str:
        """Build day-grouped message lines."""
        if not messages:
            return ""

        sections: List[str] = []
        current_date: Optional[str] = None
        day_lines: List[str] = []

        for msg in messages:
            date_str = msg.timestamp.date().isoformat()
            if date_str != current_date:
                if current_date is not None:
                    sections.append(f"## {current_date}\n\n" + "\n".join(day_lines))
                current_date = date_str
                day_lines = []
            line = self._format_line(msg)
            day_lines.append(line)
            if media_dir is not None and msg.is_media and msg.media_type == "audio":
                transcription = self._read_transcription(msg, media_dir)
                if transcription:
                    day_lines.append(f"  [Transcription]: {transcription}")

        if current_date is not None:
            sections.append(f"## {current_date}\n\n" + "\n".join(day_lines))

        return "\n\n".join(sections)

    def _read_transcription(self, msg: Message, media_dir: Path) -> str:
        """
        Read a ``*_transcription.txt`` file for *msg* from *media_dir*.

        Lines beginning with ``#`` (metadata headers) are skipped.  The
        remaining non-empty lines are joined with a single space and returned.
        Returns an empty string if no transcription file exists.
        """
        filename = self._extract_filename(msg.content)
        if not filename:
            return ""
        stem = Path(filename).stem
        transcription_path = media_dir / f"{stem}_transcription.txt"
        if not transcription_path.exists():
            return ""
        lines = transcription_path.read_text(encoding="utf-8").splitlines()
        text_lines = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
        return " ".join(text_lines)

    def _format_line(self, msg: Message) -> str:
        """Format a single message as ``[HH:MM] Sender: content``."""
        time_str = msg.timestamp.strftime("%H:%M")
        content = self._format_content(msg)
        return f"[{time_str}] {msg.sender}: {content}"

    def _format_content(self, msg: Message) -> str:
        """
        Return the formatted content string for a message.

        Text messages are returned as-is.  Media messages are converted to
        typed tags per the spec.
        """
        if not msg.is_media:
            return msg.content

        media_type = msg.media_type

        if media_type == "document":
            filename = self._extract_filename(msg.content)
            if filename:
                return f"<document {filename}>"
            return "<document>"

        tag = _MEDIA_TAG.get(media_type or "", "media")
        return f"<{tag}>"

    def _extract_filename(self, content: str) -> str:
        """
        Extract a filename from a WhatsApp "(file attached)" content string.

        Example: ``"report.pdf (file attached)"`` → ``"report.pdf"``
        """
        match = re.match(r"^(.+?)\s+\(file attached\)", content)
        if match:
            return match.group(1).strip()
        # Fallback: return content up to first space if no parenthesis pattern
        return content.split()[0] if content.split() else ""


