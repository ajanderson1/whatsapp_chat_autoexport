"""
Test suite for SpecFormatter — transcript.md generation conforming to
the WhatsApp Transcript Format Spec.
"""

from datetime import datetime, timezone

import pytest

from whatsapp_chat_autoexport.output.spec_formatter import SpecFormatter
from whatsapp_chat_autoexport.processing.transcript_parser import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_msg(
    date_str: str,
    time_str: str,
    sender: str,
    content: str,
    is_media: bool = False,
    media_type: str | None = None,
) -> Message:
    """Create a Message with a naive datetime for testing."""
    dt = datetime.fromisoformat(f"{date_str}T{time_str}")
    return Message(
        timestamp=dt,
        sender=sender,
        content=content,
        is_media=is_media,
        media_type=media_type,
    )


# ---------------------------------------------------------------------------
# Basic formatting
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_text_message():
    """Single message produces a day header and a formatted message line."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:30:00", "Alice", "Hello world")]

    result = formatter.format_transcript(msgs)

    assert "## 2024-01-15" in result
    assert "[10:30] Alice: Hello world" in result


@pytest.mark.unit
def test_multiple_messages_same_day():
    """Multiple messages on the same day share exactly one day header."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [
        make_msg("2024-01-15", "09:00:00", "Alice", "First"),
        make_msg("2024-01-15", "09:05:00", "Bob", "Second"),
        make_msg("2024-01-15", "09:10:00", "Alice", "Third"),
    ]

    result = formatter.format_transcript(msgs)

    assert result.count("## 2024-01-15") == 1
    assert "[09:00] Alice: First" in result
    assert "[09:05] Bob: Second" in result
    assert "[09:10] Alice: Third" in result


@pytest.mark.unit
def test_messages_across_days():
    """Messages on different days each get their own day header."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [
        make_msg("2024-01-14", "22:00:00", "Alice", "Yesterday"),
        make_msg("2024-01-15", "08:00:00", "Bob", "Today"),
    ]

    result = formatter.format_transcript(msgs)

    assert "## 2024-01-14" in result
    assert "## 2024-01-15" in result
    # Headers appear in chronological order
    assert result.index("## 2024-01-14") < result.index("## 2024-01-15")


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_transcript_frontmatter():
    """Output starts with YAML frontmatter containing required cssclasses."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.format_transcript(msgs)

    assert result.startswith("---\n")
    assert "cssclasses:" in result
    assert "  - whatsapp-transcript" in result
    assert "  - exclude-from-graph" in result
    # Frontmatter must be closed
    # Find the second occurrence of ---
    first = result.index("---")
    second = result.index("---", first + 3)
    assert second > first


# ---------------------------------------------------------------------------
# Metadata comment block
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_transcript_metadata_header():
    """Output contains HTML comment metadata block with required fields."""
    formatter = SpecFormatter(
        contact_name="Tim Cocking",
        chat_jid="447956173473@s.whatsapp.net",
    )
    msgs = [
        make_msg("2015-07-29", "00:05:00", "AJ Anderson", "Do you know Woodville church"),
        make_msg("2026-03-25", "23:59:00", "Tim Cocking", "Last message"),
    ]

    result = formatter.format_transcript(msgs)

    assert "<!-- TRANSCRIPT METADATA" in result
    assert "chat_jid: 447956173473@s.whatsapp.net" in result
    assert "contact: Tim Cocking" in result
    assert "generated:" in result
    assert "generator: whatsapp-export/spec" in result
    assert "message_count: 2" in result
    assert "media_count: 0" in result
    assert "date_range: 2015-07-29..2026-03-25" in result
    assert "body_sha256:" in result
    assert "-->" in result


# ---------------------------------------------------------------------------
# Media type mapping
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_media_image_tag():
    """Image media messages render as <photo>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "IMG-001.jpg (file attached)", is_media=True, media_type="image")]

    result = formatter.format_transcript(msgs)

    assert "<photo>" in result


@pytest.mark.unit
def test_media_audio_tag():
    """Audio media messages render as <voice>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "PTT-001.opus (file attached)", is_media=True, media_type="audio")]

    result = formatter.format_transcript(msgs)

    assert "<voice>" in result


@pytest.mark.unit
def test_media_video_tag():
    """Video media messages render as <video>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "VID-001.mp4 (file attached)", is_media=True, media_type="video")]

    result = formatter.format_transcript(msgs)

    assert "<video>" in result


@pytest.mark.unit
def test_media_document_tag_with_filename():
    """Document media messages render as <document filename>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "report.pdf (file attached)", is_media=True, media_type="document")]

    result = formatter.format_transcript(msgs)

    assert "<document report.pdf>" in result


@pytest.mark.unit
def test_media_sticker_tag():
    """Sticker media messages render as <sticker>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "sticker omitted", is_media=True, media_type="sticker")]

    result = formatter.format_transcript(msgs)

    assert "<sticker>" in result


@pytest.mark.unit
def test_media_unknown_tag():
    """Unknown media type renders as <media>."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "something omitted", is_media=True, media_type=None)]

    result = formatter.format_transcript(msgs)

    assert "<media>" in result


# ---------------------------------------------------------------------------
# media_count in metadata
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_media_count_in_metadata():
    """media_count reflects the number of media messages."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [
        make_msg("2024-01-15", "10:00:00", "Alice", "Hi"),
        make_msg("2024-01-15", "10:01:00", "Alice", "PTT-001.opus (file attached)", is_media=True, media_type="audio"),
        make_msg("2024-01-15", "10:02:00", "Alice", "IMG-001.jpg (file attached)", is_media=True, media_type="image"),
    ]

    result = formatter.format_transcript(msgs)

    assert "media_count: 2" in result


# ---------------------------------------------------------------------------
# Empty message list
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_messages():
    """Empty message list produces valid frontmatter and metadata, no day headers."""
    formatter = SpecFormatter(contact_name="Nobody")
    result = formatter.format_transcript([])

    assert "---" in result
    assert "<!-- TRANSCRIPT METADATA" in result
    assert "message_count: 0" in result
    assert "## " not in result


# ---------------------------------------------------------------------------
# chat_jid defaults to None gracefully
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_no_chat_jid():
    """When chat_jid is not provided, the field is omitted or empty."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.format_transcript(msgs)

    # Should still produce valid output; chat_jid line present but may be empty
    assert "contact: Alice" in result
    assert "<!-- TRANSCRIPT METADATA" in result
