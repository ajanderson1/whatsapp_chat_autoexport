"""
Index Builder module for WhatsApp Chat Auto-Export.

Generates index.md companion notes conforming to the format specification
defined in docs/specs/transcript-format-spec.md.

The index.md is the vault-native interface: queryable by Dataview,
linked in the knowledge graph, and safe for LLM context.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional

import yaml

from ..processing.transcript_parser import Message


class IndexBuilder:
    """
    Builds index.md companion notes for WhatsApp chat transcripts.

    Produces YAML frontmatter with identity, stats, provenance, and
    LLM context fields, plus a minimal body with WikiLinks.
    """

    def __init__(self, user_display_name: str = "AJ Anderson"):
        """
        Initialise the builder.

        Args:
            user_display_name: Display name for the vault owner.
        """
        self.user_display_name = user_display_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_index(
        self,
        messages: List[Message],
        chat_jid: str,
        contact_name: str,
        chat_type: str = "direct",
        sources: Optional[List[Dict]] = None,
        phone: Optional[str] = None,
        participants: Optional[List[str]] = None,
        timezone: str = "Europe/Stockholm",
        languages: Optional[List[str]] = None,
        summary: Optional[str] = None,
    ) -> str:
        """
        Build a complete index.md file.

        Args:
            messages: List of Message objects for computing stats.
            chat_jid: WhatsApp JID.
            contact_name: Display name (direct) or group name (group).
            chat_type: "direct" or "group".
            sources: List of source provenance dicts, e.g.
                     [{"type": "appium_export", "date": "2026-03-26", "messages": 16950}]
            phone: Phone number in E.164 format (direct chats).
            participants: List of participant names/WikiLinks (group chats).
            timezone: IANA timezone string.
            languages: List of language codes.
            summary: Human-readable summary of the chat.

        Returns:
            Complete index.md content as a string.
        """
        if languages is None:
            languages = ["en"]
        if sources is None:
            sources = []

        stats = self._compute_stats(messages)
        frontmatter = self._build_frontmatter(
            chat_jid=chat_jid,
            contact_name=contact_name,
            chat_type=chat_type,
            stats=stats,
            sources=sources,
            phone=phone,
            participants=participants,
            timezone=timezone,
            languages=languages,
            summary=summary,
        )
        body = self._build_body(contact_name, chat_type, stats)

        return f"{frontmatter}\n{body}\n"

    def update_index(
        self,
        existing_content: str,
        new_messages: List[Message],
        source_entry: Optional[Dict] = None,
    ) -> str:
        """
        Update an existing index.md with new message stats and source info.

        Parses the existing frontmatter, updates numeric stats, appends
        a new source entry, and regenerates the file.

        Args:
            existing_content: Current index.md content.
            new_messages: New messages to incorporate into stats.
            source_entry: New source provenance dict to append,
                          e.g. {"type": "mcp_bridge", "date": "2026-03-26", "messages": 42}

        Returns:
            Updated index.md content as a string.
        """
        frontmatter, body = self._split_frontmatter(existing_content)
        if frontmatter is None:
            # No valid frontmatter found — return unchanged
            return existing_content

        data = yaml.safe_load(frontmatter) or {}

        # Update stats
        new_stats = self._compute_stats(new_messages)
        data["message_count"] = data.get("message_count", 0) + new_stats["message_count"]
        data["media_count"] = data.get("media_count", 0) + new_stats["media_count"]
        data["voice_count"] = data.get("voice_count", 0) + new_stats["voice_count"]

        # Update date range
        if new_stats["date_first"]:
            existing_first = data.get("date_first")
            if existing_first is None or str(new_stats["date_first"]) < str(existing_first):
                data["date_first"] = new_stats["date_first"]

            existing_last = data.get("date_last")
            if existing_last is None or str(new_stats["date_last"]) > str(existing_last):
                data["date_last"] = new_stats["date_last"]

        # Update last_synced
        data["last_synced"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # Append source entry
        if source_entry:
            sources = data.get("sources", [])
            if not isinstance(sources, list):
                sources = []
            sources.append(source_entry)
            data["sources"] = sources

        # Rebuild the file
        new_frontmatter = self._dump_frontmatter(data)
        return f"{new_frontmatter}\n{body}\n"

    # ------------------------------------------------------------------
    # Frontmatter construction
    # ------------------------------------------------------------------

    def _build_frontmatter(
        self,
        chat_jid: str,
        contact_name: str,
        chat_type: str,
        stats: Dict,
        sources: List[Dict],
        phone: Optional[str],
        participants: Optional[List[str]],
        timezone: str,
        languages: List[str],
        summary: Optional[str],
    ) -> str:
        """Build the YAML frontmatter string manually for field ordering."""
        lines = ["---"]

        # Type and description
        lines.append("type: note")
        safe_name = contact_name.replace('"', '\\"')
        if chat_type == "group":
            lines.append(f'description: "WhatsApp group chat — {safe_name}"')
        else:
            lines.append(f'description: "WhatsApp correspondence with {safe_name}"')

        # Tags
        lines.append("tags:")
        lines.append("  - whatsapp")
        lines.append("  - correspondence")
        if chat_type == "group":
            lines.append("  - group_chat")

        # CSS classes
        lines.append("cssclasses:")
        lines.append("  - whatsapp-chat")

        # Identity
        lines.append("")
        lines.append(f"chat_type: {chat_type}")

        if chat_type == "group":
            lines.append(f'chat_name: "{safe_name}"')
            if participants:
                lines.append("participants:")
                for p in participants:
                    safe_p = str(p).replace('"', '\\"')
                    lines.append(f'  - "{safe_p}"')
        else:
            lines.append(f'contact: "[[{safe_name}]]"')
            if phone:
                lines.append(f'phone: "{phone}"')

        lines.append(f'jid: "{chat_jid}"')

        # Stats
        lines.append("")
        lines.append(f"message_count: {stats['message_count']}")
        lines.append(f"media_count: {stats['media_count']}")
        lines.append(f"voice_count: {stats['voice_count']}")
        if stats['date_first'] is not None:
            lines.append(f"date_first: {stats['date_first']}")
        if stats['date_last'] is not None:
            lines.append(f"date_last: {stats['date_last']}")
        lines.append(f'last_synced: "{datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}"')

        # Sources
        lines.append("")
        if sources:
            lines.append("sources:")
            for src in sources:
                lines.append(f"  - type: {src['type']}")
                lines.append(f"    date: {src['date']}")
                lines.append(f"    messages: {src['messages']}")
        else:
            lines.append("sources: []")
        lines.append("coverage_gaps: 0")

        # LLM context
        lines.append("")
        lines.append(f"timezone: {timezone}")
        lines.append("languages:")
        for lang in languages:
            lines.append(f"  - {lang}")
        if summary:
            lines.append(f"summary: >-")
            # Wrap summary at ~72 chars with 2-space indent
            wrapped = self._wrap_text(summary, width=72, indent="  ")
            lines.append(wrapped)
        else:
            lines.append('summary: ""')

        lines.append("---")
        return "\n".join(lines)

    def _build_body(self, contact_name: str, chat_type: str, stats: Dict) -> str:
        """Build the markdown body section."""
        date_first = stats["date_first"]
        date_last = stats["date_last"]
        msg_count = stats["message_count"]

        # Format message count with comma separator
        msg_display = f"{msg_count:,}"

        if chat_type == "group":
            quote_line = f"> WhatsApp group chat — {contact_name}"
        else:
            quote_line = f"> WhatsApp correspondence with [[{contact_name}]]"

        period_line = f"> Period: {date_first} to {date_last} | {msg_display} messages"

        # WikiLink to transcript — uses Obsidian relative path
        chat_folder = contact_name
        transcript_link = (
            f"[[People/Correspondence/Whatsapp/{chat_folder}/transcript|Full Transcript]]"
        )

        return f"{quote_line}\n{period_line}\n\n{transcript_link}"

    # ------------------------------------------------------------------
    # Stats computation
    # ------------------------------------------------------------------

    def _compute_stats(self, messages: List[Message]) -> Dict:
        """Compute message statistics from a list of Messages."""
        if not messages:
            return {
                "message_count": 0,
                "media_count": 0,
                "voice_count": 0,
                "date_first": None,
                "date_last": None,
            }

        media_count = 0
        voice_count = 0

        for msg in messages:
            if msg.is_media:
                media_count += 1
                if msg.media_type in ('audio',):
                    voice_count += 1

        timestamps = [msg.timestamp for msg in messages]
        date_first = min(timestamps).strftime("%Y-%m-%d")
        date_last = max(timestamps).strftime("%Y-%m-%d")

        return {
            "message_count": len(messages),
            "media_count": media_count,
            "voice_count": voice_count,
            "date_first": date_first,
            "date_last": date_last,
        }

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _split_frontmatter(content: str):
        """
        Split content into (frontmatter_yaml, body) strings.

        Returns (None, content) if no valid frontmatter found.
        """
        if not content.startswith("---"):
            return None, content

        # Find the closing ---
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None, content

        # Find the actual end (after the closing ---)
        frontmatter = content[3:end_idx].strip()
        body = content[end_idx + 3:].strip()
        return frontmatter, body

    @staticmethod
    def _dump_frontmatter(data: Dict) -> str:
        """Dump a dict as YAML frontmatter with --- delimiters."""
        yaml_str = yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=1000,  # prevent unwanted wrapping
        ).strip()
        return f"---\n{yaml_str}\n---"

    @staticmethod
    def _wrap_text(text: str, width: int = 72, indent: str = "  ") -> str:
        """Simple word-wrap with indent for YAML block scalars."""
        words = text.split()
        lines = []
        current_line = indent

        for word in words:
            if len(current_line) + len(word) + 1 > width + len(indent):
                lines.append(current_line)
                current_line = indent + word
            else:
                if current_line == indent:
                    current_line += word
                else:
                    current_line += " " + word

        if current_line.strip():
            lines.append(current_line)

        return "\n".join(lines)
