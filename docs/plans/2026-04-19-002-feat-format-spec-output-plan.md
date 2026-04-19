# `--format spec` Output Option — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--format spec` flag to the exporter CLI that produces `index.md` + `transcript.md` companion note pairs conforming to the WhatsApp Transcript Format Spec.

**Architecture:** A new `SpecFormatter` class sits alongside the existing `OutputBuilder` as a parallel output path. The pipeline's phase 4 dispatches to either the legacy `OutputBuilder` or the new `SpecFormatter` based on the `--format` flag. No existing code is modified — this is purely additive.

**Tech Stack:** Python 3.13, pytest, existing `TranscriptParser` and `Message` dataclass.

**Design spec:** `docs/specs/2026-04-19-whatsapp-sync-service-design.md` (Appium Exporter Changes section)

**Format spec:** `docs/specs/transcript-format-spec.md` (canonical output format)

---

## File Structure

```
whatsapp_chat_autoexport/
  output/
    output_builder.py          # EXISTING — unchanged
    spec_formatter.py          # NEW — formats Messages to spec output
    __init__.py                # MODIFY — add SpecFormatter export
  cli_entry.py                 # MODIFY — add --format flag
  headless.py                  # MODIFY — pass format to PipelineConfig
  pipeline.py                  # MODIFY — dispatch to SpecFormatter when format=spec

tests/
  unit/
    test_spec_formatter.py     # NEW — unit tests for SpecFormatter
  fixtures/
    expected_spec_output/      # NEW — golden file fixtures
```

---

### Task 1: SpecFormatter — transcript.md generation

**Files:**
- Create: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Test: `tests/unit/test_spec_formatter.py`

- [ ] **Step 1: Write the failing test — basic text messages**

```python
# tests/unit/test_spec_formatter.py
"""Tests for SpecFormatter — WhatsApp Transcript Format Spec output."""

from datetime import datetime
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.processing.transcript_parser import Message
from whatsapp_chat_autoexport.output.spec_formatter import SpecFormatter


@pytest.mark.unit
class TestTranscriptFormatting:
    """Tests for transcript.md generation."""

    def test_single_text_message(self):
        """Single text message produces correct spec format."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Do you know Woodville church, Cardiff.",
                raw_line="29/07/2015, 00:05 - AJ Anderson: Do you know Woodville church, Cardiff.",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "## 2015-07-29" in result
        assert "[00:05] AJ Anderson: Do you know Woodville church, Cardiff." in result

    def test_multiple_messages_same_day(self):
        """Multiple messages on same day share one day header."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="First message",
                raw_line="",
            ),
            Message(
                timestamp=datetime(2015, 7, 29, 0, 11),
                sender="Tim Cocking",
                content="Second message",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        # Only one day header
        assert result.count("## 2015-07-29") == 1
        assert "[00:05] AJ Anderson: First message" in result
        assert "[00:11] Tim Cocking: Second message" in result

    def test_messages_across_days(self):
        """Messages on different days get separate day headers."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 23, 59),
                sender="AJ Anderson",
                content="Late message",
                raw_line="",
            ),
            Message(
                timestamp=datetime(2015, 7, 30, 0, 1),
                sender="Tim Cocking",
                content="Early message",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "## 2015-07-29" in result
        assert "## 2015-07-30" in result

    def test_transcript_frontmatter(self):
        """Transcript starts with correct YAML frontmatter."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert result.startswith("---\ncssclasses:\n")
        assert "whatsapp-transcript" in result
        assert "exclude-from-graph" in result

    def test_transcript_metadata_header(self):
        """Transcript contains HTML comment metadata block."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking", chat_jid="447956173473@s.whatsapp.net")
        result = formatter.format_transcript(messages)

        assert "<!-- TRANSCRIPT METADATA" in result
        assert "contact: Tim Cocking" in result
        assert "chat_jid: 447956173473@s.whatsapp.net" in result
        assert "message_count: 1" in result
        assert "body_sha256:" in result
        assert "-->" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'whatsapp_chat_autoexport.output.spec_formatter'`

- [ ] **Step 3: Implement SpecFormatter — transcript.md generation**

```python
# whatsapp_chat_autoexport/output/spec_formatter.py
"""
Spec Format Output — WhatsApp Transcript Format Spec compliant output.

Produces index.md + transcript.md companion note pairs as defined in
docs/specs/transcript-format-spec.md.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..processing.transcript_parser import Message


class SpecFormatter:
    """
    Formats WhatsApp messages into the canonical transcript format spec.

    Produces:
    - transcript.md: day headers, [HH:MM] Sender: content, typed media
    - index.md: YAML frontmatter with metadata and stats
    """

    def __init__(
        self,
        contact_name: str,
        chat_jid: Optional[str] = None,
        chat_type: str = "direct",
        participants: Optional[List[str]] = None,
        timezone: str = "Europe/Stockholm",
    ):
        self.contact_name = contact_name
        self.chat_jid = chat_jid or ""
        self.chat_type = chat_type
        self.participants = participants or []
        self.timezone = timezone

    def format_transcript(self, messages: List[Message]) -> str:
        """
        Format messages into a complete transcript.md string.

        Args:
            messages: Chronologically ordered list of Message objects.

        Returns:
            Complete transcript.md content as a string.
        """
        # Build the message body first (needed for hash)
        body = self._format_message_body(messages)

        # Compute stats
        media_count = sum(1 for m in messages if m.is_media)
        date_first = messages[0].timestamp.strftime("%Y-%m-%d") if messages else ""
        date_last = messages[-1].timestamp.strftime("%Y-%m-%d") if messages else ""

        # Compute body hash
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()

        # Build frontmatter
        frontmatter = (
            "---\n"
            "cssclasses:\n"
            "  - whatsapp-transcript\n"
            "  - exclude-from-graph\n"
            "---\n"
        )

        # Build metadata header
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = (
            f"<!-- TRANSCRIPT METADATA\n"
            f"chat_jid: {self.chat_jid}\n"
            f"contact: {self.contact_name}\n"
            f"generated: {now}\n"
            f"generator: whatsapp-export/spec\n"
            f"message_count: {len(messages)}\n"
            f"media_count: {media_count}\n"
            f"date_range: {date_first}..{date_last}\n"
            f"body_sha256: {body_sha256}\n"
            f"-->\n"
        )

        return frontmatter + "\n" + metadata + "\n" + body

    def _format_message_body(self, messages: List[Message]) -> str:
        """Format the message body with day headers and formatted lines."""
        lines: List[str] = []
        current_date: Optional[str] = None

        for msg in messages:
            msg_date = msg.timestamp.strftime("%Y-%m-%d")

            # New day header
            if msg_date != current_date:
                if current_date is not None:
                    lines.append("")  # blank line before new day
                lines.append(f"## {msg_date}")
                lines.append("")  # blank line after header
                current_date = msg_date

            # Format the message line
            time_str = msg.timestamp.strftime("%H:%M")
            content = self._format_content(msg)
            lines.append(f"[{time_str}] {msg.sender}: {content}")

            # Inline transcription if available
            if msg.is_media and msg.media_type == "audio":
                transcription = self._get_transcription_text(msg)
                if transcription:
                    lines.append(f"  [Transcription]: {transcription}")

        return "\n".join(lines) + "\n"

    def _format_content(self, msg: Message) -> str:
        """Format message content with typed media tags."""
        if not msg.is_media:
            return msg.content

        media_type = msg.media_type or "media"
        type_map = {
            "image": "photo",
            "audio": "voice",
            "video": "video",
            "document": "document",
            "sticker": "sticker",
            "gif": "gif",
        }
        tag = type_map.get(media_type, "media")

        # Extract filename if present and meaningful
        filename = self._extract_filename(msg.content)
        if filename and media_type == "document":
            return f"<{tag} {filename}>"
        return f"<{tag}>"

    def _extract_filename(self, content: str) -> Optional[str]:
        """Extract filename from media message content if present."""
        if "(file attached)" in content:
            return content.replace("(file attached)", "").strip()
        return None

    def _get_transcription_text(self, msg: Message) -> Optional[str]:
        """
        Get transcription text for a voice message.

        This is populated by the caller — SpecFormatter doesn't do file I/O.
        The transcription text is attached to the Message via a convention:
        if msg.content contains transcription data after the media reference.

        For now, returns None — transcription injection is handled by the
        build_output method that reads transcription files.
        """
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/spec_formatter.py tests/unit/test_spec_formatter.py
git commit -m "feat: add SpecFormatter for transcript.md generation

Implements the WhatsApp Transcript Format Spec output: YAML frontmatter,
HTML comment metadata block with body_sha256, ISO day headers, typed
media tags (<photo>, <voice>, etc.), inline [Transcription]: lines."
```

---

### Task 2: SpecFormatter — typed media tags

**Files:**
- Modify: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Modify: `tests/unit/test_spec_formatter.py`

- [ ] **Step 1: Write the failing tests — media type classification**

```python
# Add to tests/unit/test_spec_formatter.py

@pytest.mark.unit
class TestMediaFormatting:
    """Tests for typed media tags."""

    def test_photo_message(self):
        """Image media produces <photo> tag."""
        messages = [
            Message(
                timestamp=datetime(2015, 8, 2, 16, 56),
                sender="Tim Cocking",
                content="IMG-20150802-WA0004.jpg (file attached)",
                is_media=True,
                media_type="image",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "[16:56] Tim Cocking: <photo>" in result

    def test_voice_message(self):
        """Audio media produces <voice> tag."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-20240115-WA0001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "[10:15] Tim Cocking: <voice>" in result

    def test_video_message(self):
        """Video media produces <video> tag."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 14, 22),
                sender="AJ Anderson",
                content="VID-20240115-WA0001.mp4 (file attached)",
                is_media=True,
                media_type="video",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="AJ Anderson")
        result = formatter.format_transcript(messages)

        assert "[14:22] AJ Anderson: <video>" in result

    def test_document_with_filename(self):
        """Document media includes filename."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 11, 45),
                sender="AJ Anderson",
                content="Flight_Booking_Confirmation.pdf (file attached)",
                is_media=True,
                media_type="document",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="AJ Anderson")
        result = formatter.format_transcript(messages)

        assert "[11:45] AJ Anderson: <document Flight_Booking_Confirmation.pdf>" in result

    def test_sticker_message(self):
        """Sticker media produces <sticker> tag."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 9, 30),
                sender="Tim Cocking",
                content="sticker omitted",
                is_media=True,
                media_type="sticker",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "[09:30] Tim Cocking: <sticker>" in result

    def test_generic_media_omitted(self):
        """<Media omitted> is classified as <media> not preserved verbatim."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 16, 0),
                sender="Tim Cocking",
                content="<Media omitted>",
                is_media=True,
                media_type=None,
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "<Media omitted>" not in result
        assert "<media>" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_spec_formatter.py::TestMediaFormatting -v`
Expected: Some tests may already pass from Task 1 implementation; verify any failures.

- [ ] **Step 3: Fix any failing tests**

The `_format_content` method from Task 1 should handle most cases. If `_extract_filename` doesn't correctly handle `"sticker omitted"` or `"<Media omitted>"`, update the method:

```python
# In spec_formatter.py, update _extract_filename:
def _extract_filename(self, content: str) -> Optional[str]:
    """Extract filename from media message content if present."""
    if "(file attached)" in content:
        filename = content.replace("(file attached)", "").strip()
        # Only return meaningful filenames (documents, PDFs)
        # Skip auto-generated names like IMG-*, PTT-*, VID-*, AUD-*
        return filename
    return None
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/spec_formatter.py tests/unit/test_spec_formatter.py
git commit -m "test: add typed media tag tests for SpecFormatter

Covers <photo>, <voice>, <video>, <document>, <sticker>, <media>.
Documents use filename inclusion, others use bare tags."
```

---

### Task 3: SpecFormatter — index.md generation

**Files:**
- Modify: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Modify: `tests/unit/test_spec_formatter.py`

- [ ] **Step 1: Write the failing tests — index.md**

```python
# Add to tests/unit/test_spec_formatter.py

@pytest.mark.unit
class TestIndexGeneration:
    """Tests for index.md companion note generation."""

    def test_direct_chat_index(self):
        """Direct chat produces correct index.md frontmatter."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
            Message(
                timestamp=datetime(2026, 3, 25, 14, 30),
                sender="Tim Cocking",
                content="Hey!",
                raw_line="",
            ),
        ]
        media_messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-20240115-WA0001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(
            contact_name="Tim Cocking",
            chat_jid="447956173473@s.whatsapp.net",
            chat_type="direct",
        )
        result = formatter.format_index(messages + media_messages)

        assert "type: note" in result
        assert 'description: "WhatsApp correspondence with Tim Cocking"' in result
        assert "chat_type: direct" in result
        assert 'contact: "[[Tim Cocking]]"' in result
        assert 'jid: "447956173473@s.whatsapp.net"' in result
        assert "message_count: 3" in result
        assert "date_first: 2015-07-29" in result
        assert "date_last: 2026-03-25" in result

    def test_group_chat_index(self):
        """Group chat uses chat_name and participants instead of contact."""
        messages = [
            Message(
                timestamp=datetime(2016, 1, 5, 12, 0),
                sender="Tim Cocking",
                content="Hello brothers",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(
            contact_name="Brothers",
            chat_jid="491749580928-1452027796@g.us",
            chat_type="group",
            participants=["Tim Cocking", "Peter Cocking"],
        )
        result = formatter.format_index(messages)

        assert "chat_type: group" in result
        assert 'chat_name: "Brothers"' in result
        assert "contact:" not in result
        assert '  - "[[Tim Cocking]]"' in result
        assert '  - "[[Peter Cocking]]"' in result

    def test_index_body(self):
        """Index body contains summary line and transcript link."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_index(messages)

        assert "WhatsApp correspondence with [[Tim Cocking]]" in result
        assert "[[" in result and "transcript" in result.lower()

    def test_index_source_provenance(self):
        """Index includes appium_export source."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_index(messages)

        assert "sources:" in result
        assert "type: appium_export" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_spec_formatter.py::TestIndexGeneration -v`
Expected: FAIL with `AttributeError: 'SpecFormatter' object has no attribute 'format_index'`

- [ ] **Step 3: Implement format_index**

```python
# Add to SpecFormatter class in spec_formatter.py:

    def format_index(self, messages: List[Message]) -> str:
        """
        Format an index.md companion note.

        Args:
            messages: All messages for this chat (for computing stats).

        Returns:
            Complete index.md content as a string.
        """
        # Compute stats
        media_count = sum(1 for m in messages if m.is_media)
        voice_count = sum(
            1 for m in messages if m.is_media and m.media_type == "audio"
        )
        date_first = messages[0].timestamp.strftime("%Y-%m-%d") if messages else ""
        date_last = messages[-1].timestamp.strftime("%Y-%m-%d") if messages else ""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Build frontmatter
        lines = [
            "---",
            "type: note",
        ]

        if self.chat_type == "group":
            lines.append(f'description: "WhatsApp group chat — {self.contact_name}"')
        else:
            lines.append(
                f'description: "WhatsApp correspondence with {self.contact_name}"'
            )

        lines.extend([
            "tags:",
            "  - whatsapp",
            "  - correspondence",
        ])
        if self.chat_type == "group":
            lines.append("  - group_chat")

        lines.extend([
            "cssclasses:",
            "  - whatsapp-chat",
            "",
            f"chat_type: {self.chat_type}",
        ])

        if self.chat_type == "group":
            lines.append(f'chat_name: "{self.contact_name}"')
            lines.append("participants:")
            for p in self.participants:
                lines.append(f'  - "[[{p}]]"')
        else:
            lines.append(f'contact: "[[{self.contact_name}]]"')

        if self.chat_jid:
            lines.append(f'jid: "{self.chat_jid}"')

        lines.extend([
            "",
            f"message_count: {len(messages)}",
            f"media_count: {media_count}",
            f"voice_count: {voice_count}",
            f"date_first: {date_first}",
            f"date_last: {date_last}",
            f"last_synced: {now}",
            "",
            "sources:",
            "  - type: appium_export",
            f"    date: {today}",
            f"    messages: {len(messages)}",
            "coverage_gaps: 0",
            "",
            f"timezone: {self.timezone}",
            "---",
        ])

        # Body
        if self.chat_type == "group":
            summary_line = f"> WhatsApp group chat — {self.contact_name}"
        else:
            summary_line = f"> WhatsApp correspondence with [[{self.contact_name}]]"

        period = f"{date_first} to {date_last}" if date_first else "unknown"
        summary_line += f"\n> Period: {period} | {len(messages):,} messages"

        # Transcript link (Obsidian wiki-link)
        folder = f"People/Correspondence/Whatsapp/{self.contact_name}"
        transcript_link = f"[[{folder}/transcript|Full Transcript]]"

        body = f"\n{summary_line}\n\n{transcript_link}\n"

        return "\n".join(lines) + body

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/spec_formatter.py tests/unit/test_spec_formatter.py
git commit -m "feat: add index.md generation to SpecFormatter

Companion note with YAML frontmatter: chat type, contact WikiLink, JID,
message stats, source provenance, coverage gaps. Supports direct and
group chat variants."
```

---

### Task 4: SpecFormatter — transcription injection from files

**Files:**
- Modify: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Modify: `tests/unit/test_spec_formatter.py`

- [ ] **Step 1: Write the failing test — transcription injection**

```python
# Add to tests/unit/test_spec_formatter.py

@pytest.mark.unit
class TestTranscriptionInjection:
    """Tests for inline voice transcription in transcript.md."""

    def test_voice_with_transcription_file(self, tmp_path):
        """Voice message gets [Transcription]: line from file."""
        # Create a transcription file
        transcription_dir = tmp_path / "media"
        transcription_dir.mkdir()
        transcription_file = transcription_dir / "PTT-20240115-WA0001_transcription.txt"
        transcription_file.write_text(
            "# Transcription of: PTT-20240115-WA0001.opus\n"
            "# Transcribed at: 2026-04-19\n"
            "\n"
            "Bring a frying pan, spatula, butter and stuff.\n"
        )

        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-20240115-WA0001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages, media_dir=transcription_dir)

        assert "[10:15] Tim Cocking: <voice>" in result
        assert "  [Transcription]: Bring a frying pan, spatula, butter and stuff." in result

    def test_voice_without_transcription_file(self):
        """Voice message without transcription file gets bare <voice> tag."""
        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-20240115-WA0001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages)

        assert "[10:15] Tim Cocking: <voice>" in result
        assert "[Transcription]:" not in result

    def test_transcription_text_strips_metadata(self, tmp_path):
        """Transcription text skips # metadata lines."""
        transcription_dir = tmp_path / "media"
        transcription_dir.mkdir()
        transcription_file = transcription_dir / "PTT-20240115-WA0001_transcription.txt"
        transcription_file.write_text(
            "# Transcription of: PTT-20240115-WA0001.opus\n"
            "# Transcribed at: 2026-04-19\n"
            "# Language: en\n"
            "# Processing time: 2.3s\n"
            "# Model: scribe_v1\n"
            "\n"
            "Hello there, how are you?\n"
        )

        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-20240115-WA0001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        result = formatter.format_transcript(messages, media_dir=transcription_dir)

        assert "  [Transcription]: Hello there, how are you?" in result
        assert "# Transcription of" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_spec_formatter.py::TestTranscriptionInjection -v`
Expected: FAIL — `format_transcript()` doesn't accept `media_dir` parameter yet.

- [ ] **Step 3: Update format_transcript to accept media_dir and inject transcriptions**

```python
# Update the format_transcript signature and _format_message_body in spec_formatter.py:

    def format_transcript(
        self,
        messages: List[Message],
        media_dir: Optional[Path] = None,
    ) -> str:
        """
        Format messages into a complete transcript.md string.

        Args:
            messages: Chronologically ordered list of Message objects.
            media_dir: Optional directory containing transcription files.

        Returns:
            Complete transcript.md content as a string.
        """
        body = self._format_message_body(messages, media_dir=media_dir)
        # ... rest unchanged

    def _format_message_body(
        self,
        messages: List[Message],
        media_dir: Optional[Path] = None,
    ) -> str:
        """Format the message body with day headers and formatted lines."""
        lines: List[str] = []
        current_date: Optional[str] = None

        for msg in messages:
            msg_date = msg.timestamp.strftime("%Y-%m-%d")

            if msg_date != current_date:
                if current_date is not None:
                    lines.append("")
                lines.append(f"## {msg_date}")
                lines.append("")
                current_date = msg_date

            time_str = msg.timestamp.strftime("%H:%M")
            content = self._format_content(msg)
            lines.append(f"[{time_str}] {msg.sender}: {content}")

            # Inline transcription for voice messages
            if msg.is_media and msg.media_type == "audio" and media_dir:
                transcription = self._read_transcription(msg, media_dir)
                if transcription:
                    lines.append(f"  [Transcription]: {transcription}")

        return "\n".join(lines) + "\n"

    def _read_transcription(self, msg: Message, media_dir: Path) -> Optional[str]:
        """Read transcription text from a _transcription.txt file."""
        filename = self._extract_filename(msg.content)
        if not filename:
            return None

        stem = Path(filename).stem
        transcription_path = media_dir / f"{stem}_transcription.txt"

        if not transcription_path.exists():
            return None

        try:
            text_lines = []
            for line in transcription_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    text_lines.append(stripped)
            return " ".join(text_lines) if text_lines else None
        except Exception:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/spec_formatter.py tests/unit/test_spec_formatter.py
git commit -m "feat: add transcription injection to SpecFormatter

Reads *_transcription.txt files from media_dir, strips # metadata lines,
injects as indented [Transcription]: lines below <voice> tags."
```

---

### Task 5: SpecFormatter — build_output method (full output)

**Files:**
- Modify: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Modify: `tests/unit/test_spec_formatter.py`

- [ ] **Step 1: Write the failing test — full output build**

```python
# Add to tests/unit/test_spec_formatter.py

@pytest.mark.unit
class TestBuildOutput:
    """Tests for full output directory creation."""

    def test_build_creates_index_and_transcript(self, tmp_path):
        """build_output creates index.md and transcript.md in contact folder."""
        messages = [
            Message(
                timestamp=datetime(2015, 7, 29, 0, 5),
                sender="AJ Anderson",
                content="Hello",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        dest = tmp_path / "output"

        result = formatter.build_output(
            messages=messages,
            dest_dir=dest,
        )

        contact_dir = dest / "Tim Cocking"
        assert (contact_dir / "index.md").exists()
        assert (contact_dir / "transcript.md").exists()
        assert result["contact_name"] == "Tim Cocking"
        assert result["total_messages"] == 1

    def test_build_copies_transcriptions(self, tmp_path):
        """build_output copies transcription files to transcriptions/ dir."""
        # Create source transcription
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "PTT-001_transcription.txt").write_text("Hello world\n")

        messages = [
            Message(
                timestamp=datetime(2024, 1, 15, 10, 15),
                sender="Tim Cocking",
                content="PTT-001.opus (file attached)",
                is_media=True,
                media_type="audio",
                raw_line="",
            ),
        ]
        formatter = SpecFormatter(contact_name="Tim Cocking")
        dest = tmp_path / "output"

        formatter.build_output(
            messages=messages,
            dest_dir=dest,
            media_dir=media_dir,
            include_transcriptions=True,
        )

        transcription_dest = dest / "Tim Cocking" / "transcriptions" / "PTT-001_transcription.txt"
        assert transcription_dest.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_spec_formatter.py::TestBuildOutput -v`
Expected: FAIL — `build_output` method doesn't exist yet.

- [ ] **Step 3: Implement build_output**

```python
# Add to SpecFormatter class in spec_formatter.py:

    def build_output(
        self,
        messages: List[Message],
        dest_dir: Path,
        media_dir: Optional[Path] = None,
        include_transcriptions: bool = True,
        copy_media: bool = True,
    ) -> dict:
        """
        Build complete spec-format output for a chat.

        Creates:
        - dest_dir/<contact_name>/index.md
        - dest_dir/<contact_name>/transcript.md
        - dest_dir/<contact_name>/transcriptions/ (if include_transcriptions)

        Args:
            messages: All messages for this chat.
            dest_dir: Root output directory.
            media_dir: Source directory with media and transcription files.
            include_transcriptions: Copy transcription files to output.
            copy_media: Copy media files to output.

        Returns:
            Summary dict with paths and stats.
        """
        import shutil

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

        # Copy transcription files
        copied_transcriptions = 0
        if include_transcriptions and media_dir:
            transcriptions_dir = contact_dir / "transcriptions"
            transcriptions_dir.mkdir(exist_ok=True)

            for f in media_dir.glob("*_transcription.txt"):
                dest_file = transcriptions_dir / f.name
                if not dest_file.exists():
                    shutil.copy2(f, dest_file)
                    copied_transcriptions += 1

        # Copy media files
        copied_media = 0
        if copy_media and media_dir:
            media_out = contact_dir / "media"
            media_out.mkdir(exist_ok=True)

            for f in media_dir.iterdir():
                if f.is_file() and not f.name.endswith("_transcription.txt"):
                    dest_file = media_out / f.name
                    if not dest_file.exists():
                        shutil.copy2(f, dest_file)
                        copied_media += 1

        media_count = sum(1 for m in messages if m.is_media)
        return {
            "contact_name": self.contact_name,
            "output_dir": contact_dir,
            "transcript_path": transcript_path,
            "index_path": index_path,
            "total_messages": len(messages),
            "media_messages": media_count,
            "media_copied": copied_media,
            "transcriptions_copied": copied_transcriptions,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/unit/test_spec_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/spec_formatter.py tests/unit/test_spec_formatter.py
git commit -m "feat: add build_output to SpecFormatter

Creates complete contact folder: index.md, transcript.md, copies
transcription and media files. Returns summary dict matching
OutputBuilder's interface."
```

---

### Task 6: Wire --format flag into CLI and pipeline

**Files:**
- Modify: `whatsapp_chat_autoexport/cli_entry.py`
- Modify: `whatsapp_chat_autoexport/headless.py`
- Modify: `whatsapp_chat_autoexport/pipeline.py`
- Modify: `whatsapp_chat_autoexport/output/__init__.py`
- Modify: `tests/unit/test_cli_entry.py`

- [ ] **Step 1: Write the failing test — CLI flag parsing**

```python
# Add to tests/unit/test_cli_entry.py

@pytest.mark.unit
def test_format_flag_default_is_legacy():
    """--format defaults to 'legacy'."""
    from whatsapp_chat_autoexport.cli_entry import create_parser

    parser = create_parser()
    args = parser.parse_args(["--headless", "--output", "/tmp/out", "--auto-select"])
    assert args.format == "legacy"


@pytest.mark.unit
def test_format_flag_spec():
    """--format spec is accepted."""
    from whatsapp_chat_autoexport.cli_entry import create_parser

    parser = create_parser()
    args = parser.parse_args([
        "--headless", "--output", "/tmp/out", "--auto-select", "--format", "spec"
    ])
    assert args.format == "spec"


@pytest.mark.unit
def test_format_flag_invalid_rejected():
    """--format with invalid value is rejected."""
    from whatsapp_chat_autoexport.cli_entry import create_parser

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--headless", "--output", "/tmp/out", "--format", "xml"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/unit/test_cli_entry.py::test_format_flag_default_is_legacy tests/unit/test_cli_entry.py::test_format_flag_spec tests/unit/test_cli_entry.py::test_format_flag_invalid_rejected -v`
Expected: FAIL — `format` attribute doesn't exist on args.

- [ ] **Step 3: Add --format flag to CLI parser**

```python
# In cli_entry.py, add to the output_group section (after --delete-from-drive):

    output_group.add_argument(
        "--format",
        type=str,
        choices=["legacy", "spec"],
        default="legacy",
        metavar="FORMAT",
        help="Output format: 'legacy' (transcript.txt) or 'spec' (index.md + transcript.md)",
    )
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `poetry run pytest tests/unit/test_cli_entry.py::test_format_flag_default_is_legacy tests/unit/test_cli_entry.py::test_format_flag_spec tests/unit/test_cli_entry.py::test_format_flag_invalid_rejected -v`
Expected: All 3 PASS

- [ ] **Step 5: Add output_format to PipelineConfig**

```python
# In pipeline.py, add to PipelineConfig dataclass:

    # Output format
    output_format: str = "legacy"  # "legacy" or "spec"
```

- [ ] **Step 6: Pass format through headless.py to PipelineConfig**

```python
# In headless.py run_headless(), add to the PipelineConfig constructor:

            output_format=getattr(args, "format", "legacy"),

# In headless.py run_pipeline_only(), add to the PipelineConfig constructor:

        output_format=getattr(args, "format", "legacy"),
```

- [ ] **Step 7: Dispatch to SpecFormatter in pipeline phase 4**

```python
# In pipeline.py, modify _phase4_build_outputs:

    def _phase4_build_outputs(self, transcript_files: List[tuple]) -> List[Path]:
        """Phase 4: Build final organized outputs."""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 4: Build Final Outputs")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would build final outputs")
            return []

        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        if self.config.output_format == "spec":
            return self._phase4_build_spec_outputs(transcript_files)

        # Legacy format (default)
        results = self.output_builder.batch_build_outputs(
            transcript_files,
            self.config.output_dir,
            include_transcriptions=self.config.include_transcriptions,
            copy_media=self.config.include_media,
            on_progress=self.on_progress
        )
        output_dirs = [r['output_dir'] for r in results]
        self.logger.success(f"Created {len(output_dirs)} output(s) in: {self.config.output_dir}")
        return output_dirs

    def _phase4_build_spec_outputs(self, transcript_files: List[tuple]) -> List[Path]:
        """Build outputs in spec format (index.md + transcript.md)."""
        from .output.spec_formatter import SpecFormatter

        output_dirs = []
        total = len(transcript_files)

        for i, (transcript_path, media_dir) in enumerate(transcript_files, 1):
            contact_name = self.output_builder._extract_contact_name(transcript_path)
            self.logger.info(f"\n[{i}/{total}] Building spec output: {contact_name}")

            messages, media_refs = self.output_builder.parser.parse_transcript(
                transcript_path
            )

            formatter = SpecFormatter(contact_name=contact_name)
            summary = formatter.build_output(
                messages=messages,
                dest_dir=self.config.output_dir,
                media_dir=media_dir if media_dir.exists() else None,
                include_transcriptions=self.config.include_transcriptions,
                copy_media=self.config.include_media,
            )

            output_dirs.append(summary["output_dir"])
            self._fire_progress(
                "build_output",
                f"Built spec output for {contact_name}",
                i, total, contact_name,
            )

        self.logger.success(
            f"Created {len(output_dirs)} spec output(s) in: {self.config.output_dir}"
        )
        return output_dirs
```

- [ ] **Step 8: Export SpecFormatter from __init__.py**

```python
# In whatsapp_chat_autoexport/output/__init__.py, add:
from .spec_formatter import SpecFormatter

__all__ = ["OutputBuilder", "SpecFormatter"]
```

- [ ] **Step 9: Run full test suite**

Run: `poetry run pytest -v`
Expected: All existing tests PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add whatsapp_chat_autoexport/cli_entry.py whatsapp_chat_autoexport/headless.py whatsapp_chat_autoexport/pipeline.py whatsapp_chat_autoexport/output/__init__.py tests/unit/test_cli_entry.py
git commit -m "feat: wire --format spec flag through CLI to pipeline

New --format flag (legacy|spec) on the whatsapp CLI. Pipeline phase 4
dispatches to SpecFormatter when format=spec. Legacy format unchanged
and remains the default."
```

---

### Task 7: Integration test — end-to-end spec output

**Files:**
- Create: `tests/integration/test_spec_output.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_spec_output.py
"""Integration test: full pipeline with --format spec produces correct output."""

from pathlib import Path

import pytest

from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig


@pytest.mark.integration
def test_pipeline_spec_format_produces_companion_notes(
    sample_export_dir, temp_output_dir
):
    """Pipeline with output_format='spec' creates index.md + transcript.md."""
    config = PipelineConfig(
        skip_download=True,
        download_dir=sample_export_dir,
        output_dir=temp_output_dir,
        output_format="spec",
        include_media=False,
        include_transcriptions=True,
        transcribe_audio_video=False,
        cleanup_temp=False,
    )

    pipeline = WhatsAppPipeline(config)
    results = pipeline.run(source_dir=sample_export_dir)

    assert results["success"]

    # Find at least one output directory
    output_dirs = list(temp_output_dir.iterdir())
    assert len(output_dirs) > 0

    # Check the first output has the spec structure
    contact_dir = output_dirs[0]
    index_md = contact_dir / "index.md"
    transcript_md = contact_dir / "transcript.md"

    assert index_md.exists(), f"index.md missing in {contact_dir}"
    assert transcript_md.exists(), f"transcript.md missing in {contact_dir}"

    # Verify index.md has frontmatter
    index_content = index_md.read_text()
    assert "type: note" in index_content
    assert "whatsapp" in index_content

    # Verify transcript.md has spec format
    transcript_content = transcript_md.read_text()
    assert "cssclasses:" in transcript_content
    assert "whatsapp-transcript" in transcript_content
    assert "## 20" in transcript_content  # day header


@pytest.mark.integration
def test_pipeline_legacy_format_unchanged(sample_export_dir, temp_output_dir):
    """Pipeline with default format still produces transcript.txt."""
    config = PipelineConfig(
        skip_download=True,
        download_dir=sample_export_dir,
        output_dir=temp_output_dir,
        output_format="legacy",
        include_media=False,
        include_transcriptions=False,
        transcribe_audio_video=False,
        cleanup_temp=False,
    )

    pipeline = WhatsAppPipeline(config)
    results = pipeline.run(source_dir=sample_export_dir)

    assert results["success"]

    output_dirs = list(temp_output_dir.iterdir())
    assert len(output_dirs) > 0

    contact_dir = output_dirs[0]
    assert (contact_dir / "transcript.txt").exists()
    assert not (contact_dir / "transcript.md").exists()
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run pytest tests/integration/test_spec_output.py -v`
Expected: Both tests PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run pytest -v`
Expected: All tests PASS, no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_spec_output.py
git commit -m "test: add integration tests for --format spec pipeline

Verifies end-to-end: sample export → pipeline → index.md + transcript.md.
Also verifies legacy format is unchanged."
```

---

## Post-Implementation Checklist

- [ ] `poetry run pytest -v` — all tests pass
- [ ] `poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing` — coverage >= 90%
- [ ] `poetry run whatsapp --help` shows `--format` flag
- [ ] Manual test: `poetry run whatsapp --pipeline-only sample_data/ /tmp/spec-test --format spec --no-transcribe` produces correct output
