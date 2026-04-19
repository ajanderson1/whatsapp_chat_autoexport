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


# ---------------------------------------------------------------------------
# format_index — direct chat
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_direct_chat_index():
    """Direct chat index.md has correct frontmatter fields."""
    formatter = SpecFormatter(
        contact_name="Tim Cocking",
        chat_jid="447956173473@s.whatsapp.net",
        chat_type="direct",
    )
    msgs = [
        make_msg("2015-07-29", "00:05:00", "AJ Anderson", "First message"),
        make_msg("2026-03-25", "23:59:00", "Tim Cocking", "Last message"),
    ]

    result = formatter.format_index(msgs)

    assert "type: note" in result
    assert "chat_type: direct" in result
    assert 'contact: "[[Tim Cocking]]"' in result
    assert "jid: 447956173473@s.whatsapp.net" in result
    assert "message_count: 2" in result
    assert "date_first: 2015-07-29" in result
    assert "date_last: 2026-03-25" in result
    # Should NOT include participants for direct chat
    assert "participants:" not in result


@pytest.mark.unit
def test_direct_chat_index_frontmatter_structure():
    """Direct chat index frontmatter includes required keys in correct positions."""
    formatter = SpecFormatter(
        contact_name="Tim Cocking",
        chat_jid="447956173473@s.whatsapp.net",
        chat_type="direct",
    )
    msgs = [make_msg("2024-01-15", "10:00:00", "Tim Cocking", "Hello")]

    result = formatter.format_index(msgs)

    assert result.startswith("---\n")
    assert "tags:" in result
    assert "  - whatsapp" in result
    assert "  - correspondence" in result
    assert "cssclasses:" in result
    assert "  - whatsapp-chat" in result
    # Frontmatter is closed
    first = result.index("---")
    second = result.index("---", first + 3)
    assert second > first


# ---------------------------------------------------------------------------
# format_index — group chat
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_group_chat_index():
    """Group chat index.md uses chat_name and participants list instead of contact."""
    formatter = SpecFormatter(
        contact_name="Brothers",
        chat_jid="12345@g.us",
        chat_type="group",
        participants=["Alice", "Bob", "Charlie"],
    )
    msgs = [
        make_msg("2020-01-01", "09:00:00", "Alice", "Hi"),
        make_msg("2020-06-15", "12:00:00", "Bob", "Bye"),
    ]

    result = formatter.format_index(msgs)

    assert "chat_type: group" in result
    assert "chat_name: Brothers" in result
    assert "participants:" in result
    assert '  - "[[Alice]]"' in result
    assert '  - "[[Bob]]"' in result
    assert '  - "[[Charlie]]"' in result
    # Should NOT include contact for group chat
    assert "contact:" not in result
    assert "message_count: 2" in result
    assert "date_first: 2020-01-01" in result
    assert "date_last: 2020-06-15" in result


# ---------------------------------------------------------------------------
# format_index — body
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_index_body():
    """index.md body contains a summary blockquote and a transcript WikiLink."""
    formatter = SpecFormatter(
        contact_name="Tim Cocking",
        chat_jid="447956173473@s.whatsapp.net",
        chat_type="direct",
    )
    msgs = [
        make_msg("2015-07-29", "00:05:00", "AJ Anderson", "First"),
        make_msg("2026-03-25", "23:59:00", "Tim Cocking", "Last"),
    ]

    result = formatter.format_index(msgs)

    # Body appears after closing ---
    fm_end = result.index("---", result.index("---") + 3) + 3
    body = result[fm_end:]

    assert "[[Tim Cocking]]" in body
    assert "2015-07-29" in body
    assert "2026-03-25" in body
    # WikiLink to transcript
    assert "transcript" in body.lower()
    assert "[[" in body


# ---------------------------------------------------------------------------
# format_index — source provenance
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_index_source_provenance():
    """index.md frontmatter includes sources: block with appium_export type."""
    formatter = SpecFormatter(
        contact_name="Alice",
        chat_type="direct",
    )
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.format_index(msgs)

    assert "sources:" in result
    assert "  - type: appium_export" in result
    assert "    messages: 1" in result


# ---------------------------------------------------------------------------
# format_index — media and voice counts
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_index_media_and_voice_counts():
    """index.md frontmatter includes correct media_count and voice_count."""
    formatter = SpecFormatter(contact_name="Alice", chat_type="direct")
    msgs = [
        make_msg("2024-01-15", "10:00:00", "Alice", "Hi"),
        make_msg("2024-01-15", "10:01:00", "Alice", "IMG-001.jpg (file attached)", is_media=True, media_type="image"),
        make_msg("2024-01-15", "10:02:00", "Alice", "PTT-001.opus (file attached)", is_media=True, media_type="audio"),
        make_msg("2024-01-15", "10:03:00", "Alice", "PTT-002.opus (file attached)", is_media=True, media_type="audio"),
    ]

    result = formatter.format_index(msgs)

    assert "media_count: 3" in result
    assert "voice_count: 2" in result


# ---------------------------------------------------------------------------
# format_index — empty messages
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_index_empty_messages():
    """format_index with no messages produces valid output with zero counts."""
    formatter = SpecFormatter(contact_name="Alice", chat_type="direct")

    result = formatter.format_index([])

    assert "message_count: 0" in result
    assert "media_count: 0" in result
    assert "voice_count: 0" in result


# ---------------------------------------------------------------------------
# format_index — timezone field
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_index_timezone():
    """index.md frontmatter includes the configured timezone."""
    formatter = SpecFormatter(
        contact_name="Alice",
        chat_type="direct",
        timezone="America/New_York",
    )
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.format_index(msgs)

    assert "timezone: America/New_York" in result


# ---------------------------------------------------------------------------
# Transcription injection
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_voice_with_transcription_file(tmp_path):
    """Voice message gets an indented [Transcription]: line when a file exists."""
    transcription_content = (
        "# Transcription of: PTT-20240115-WA0001.opus\n"
        "# Transcribed at: 2026-04-19\n"
        "# Language: en\n"
        "# Processing time: 2.3s\n"
        "# Model: scribe_v1\n"
        "\n"
        "Bring a frying pan, spatula, butter and stuff.\n"
    )
    (tmp_path / "PTT-20240115-WA0001_transcription.txt").write_text(transcription_content)

    formatter = SpecFormatter(contact_name="Tim Cocking")
    msgs = [
        make_msg(
            "2024-01-15", "10:15:00", "Tim Cocking",
            "PTT-20240115-WA0001.opus (file attached)",
            is_media=True, media_type="audio",
        )
    ]

    result = formatter.format_transcript(msgs, media_dir=tmp_path)

    assert "[10:15] Tim Cocking: <voice>" in result
    assert "  [Transcription]: Bring a frying pan, spatula, butter and stuff." in result


@pytest.mark.unit
def test_voice_without_transcription_file(tmp_path):
    """Voice message without a matching transcription file renders bare <voice> tag."""
    formatter = SpecFormatter(contact_name="Alice")
    msgs = [
        make_msg(
            "2024-01-15", "10:15:00", "Alice",
            "PTT-20240115-WA0001.opus (file attached)",
            is_media=True, media_type="audio",
        )
    ]

    result = formatter.format_transcript(msgs, media_dir=tmp_path)

    assert "<voice>" in result
    assert "[Transcription]:" not in result


@pytest.mark.unit
def test_transcription_text_strips_metadata(tmp_path):
    """_read_transcription skips # metadata header lines and returns only text."""
    transcription_content = (
        "# Transcription of: PTT-001.opus\n"
        "# Model: whisper-1\n"
        "\n"
        "Hello there.\n"
        "How are you?\n"
    )
    (tmp_path / "PTT-001_transcription.txt").write_text(transcription_content)

    formatter = SpecFormatter(contact_name="Alice")
    msg = make_msg(
        "2024-01-15", "09:00:00", "Alice",
        "PTT-001.opus (file attached)",
        is_media=True, media_type="audio",
    )

    text = formatter._read_transcription(msg, tmp_path)

    assert text == "Hello there. How are you?"
    assert "#" not in text


# ---------------------------------------------------------------------------
# build_output
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_creates_index_and_transcript(tmp_path):
    """build_output creates index.md and transcript.md inside a contact sub-directory."""
    formatter = SpecFormatter(contact_name="Alice", chat_jid="alice@s.whatsapp.net")
    msgs = [
        make_msg("2024-01-15", "10:00:00", "Alice", "Hello"),
        make_msg("2024-01-15", "10:05:00", "Bob", "Hi there"),
    ]

    result = formatter.build_output(msgs, dest_dir=tmp_path)

    contact_dir = tmp_path / "Alice"
    assert contact_dir.is_dir()
    assert (contact_dir / "index.md").is_file()
    assert (contact_dir / "transcript.md").is_file()

    assert result["contact_name"] == "Alice"
    assert result["output_dir"] == contact_dir
    assert result["transcript_path"] == contact_dir / "transcript.md"
    assert result["index_path"] == contact_dir / "index.md"
    assert result["total_messages"] == 2
    assert result["media_messages"] == 0
    assert result["media_copied"] == 0
    assert result["transcriptions_copied"] == 0


@pytest.mark.unit
def test_build_copies_transcriptions(tmp_path):
    """build_output copies *_transcription.txt files to a transcriptions/ sub-directory."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001_transcription.txt").write_text("Hello world")
    (media_dir / "PTT-002_transcription.txt").write_text("Another transcription")

    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.build_output(msgs, dest_dir=tmp_path, media_dir=media_dir)

    transcriptions_dir = tmp_path / "Alice" / "transcriptions"
    assert transcriptions_dir.is_dir()
    assert (transcriptions_dir / "PTT-001_transcription.txt").is_file()
    assert (transcriptions_dir / "PTT-002_transcription.txt").is_file()
    assert result["transcriptions_copied"] == 2
    assert result["media_copied"] == 0


@pytest.mark.unit
def test_build_copies_media(tmp_path):
    """build_output copies non-transcription files to a media/ sub-directory."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001.opus").write_bytes(b"\x00\x01\x02")
    (media_dir / "IMG-001.jpg").write_bytes(b"\xff\xd8\xff")
    (media_dir / "PTT-001_transcription.txt").write_text("A voice message")

    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.build_output(msgs, dest_dir=tmp_path, media_dir=media_dir)

    media_out_dir = tmp_path / "Alice" / "media"
    assert media_out_dir.is_dir()
    assert (media_out_dir / "PTT-001.opus").is_file()
    assert (media_out_dir / "IMG-001.jpg").is_file()
    # Transcription file must NOT be in media/
    assert not (media_out_dir / "PTT-001_transcription.txt").exists()
    assert result["media_copied"] == 2
    assert result["transcriptions_copied"] == 1


@pytest.mark.unit
def test_build_no_media_flag(tmp_path):
    """When copy_media=False, no media/ directory is created."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001.opus").write_bytes(b"\x00\x01\x02")
    (media_dir / "IMG-001.jpg").write_bytes(b"\xff\xd8\xff")

    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.build_output(
        msgs, dest_dir=tmp_path, media_dir=media_dir, copy_media=False
    )

    assert not (tmp_path / "Alice" / "media").exists()
    assert result["media_copied"] == 0


@pytest.mark.unit
def test_build_no_transcriptions_flag(tmp_path):
    """When include_transcriptions=False, no transcriptions/ directory is created."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001_transcription.txt").write_text("Hello world")

    formatter = SpecFormatter(contact_name="Alice")
    msgs = [make_msg("2024-01-15", "10:00:00", "Alice", "Hi")]

    result = formatter.build_output(
        msgs, dest_dir=tmp_path, media_dir=media_dir, include_transcriptions=False
    )

    assert not (tmp_path / "Alice" / "transcriptions").exists()
    assert result["transcriptions_copied"] == 0
