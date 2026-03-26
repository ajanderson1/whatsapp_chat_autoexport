"""
Test suite for SpecFormatter.

Tests transcript.md output conforming to docs/specs/transcript-format-spec.md.
"""

import hashlib
import re
from datetime import datetime

import pytest

from whatsapp_chat_autoexport.output.spec_formatter import SpecFormatter
from whatsapp_chat_autoexport.processing.transcript_parser import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(
    ts: str,
    sender: str,
    content: str,
    is_media: bool = False,
    media_type: str = None,
    source: str = "test",
) -> Message:
    """Shorthand factory for test Message objects."""
    return Message(
        timestamp=datetime.fromisoformat(ts),
        sender=sender,
        content=content,
        is_media=is_media,
        media_type=media_type,
        source=source,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    """Tests for the minimal YAML frontmatter block."""

    def test_frontmatter_present(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "447956173473@s.whatsapp.net", "Tim Cocking")

        assert result.startswith("---\n")
        assert "cssclasses:" in result

    def test_frontmatter_cssclasses(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        assert "whatsapp-transcript" in result
        assert "exclude-from-graph" in result

    def test_frontmatter_no_extra_fields(self):
        """Frontmatter should only contain cssclasses — nothing else."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        # Extract frontmatter
        fm_end = result.index("---", 3)
        frontmatter = result[4:fm_end].strip()

        # Should only have cssclasses lines
        for line in frontmatter.split("\n"):
            stripped = line.strip()
            if stripped:
                assert stripped in (
                    "cssclasses:",
                    "- whatsapp-transcript",
                    "- exclude-from-graph",
                ), f"Unexpected frontmatter line: {stripped!r}"


# ---------------------------------------------------------------------------
# Integrity header
# ---------------------------------------------------------------------------

class TestIntegrityHeader:
    """Tests for the HTML comment integrity header."""

    def test_header_present(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "447956173473@s.whatsapp.net", "Tim Cocking")

        assert "<!-- TRANSCRIPT METADATA" in result
        assert "-->" in result

    def test_header_contains_chat_jid(self):
        fmt = SpecFormatter()
        jid = "447956173473@s.whatsapp.net"
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, jid, "Tim Cocking")

        assert f"chat_jid: {jid}" in result

    def test_header_contains_contact_name(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Tim Cocking")

        assert "contact: Tim Cocking" in result

    def test_header_contains_generated_timestamp(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        # Should match ISO format with Z suffix
        assert re.search(r"generated: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_header_contains_generator_version(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        assert "generator: wa-sync/1.0.0" in result

    def test_header_message_count(self):
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:06:00", "Tim Cocking", "Hi"),
            _msg("2015-07-29T00:07:00", "AJ Anderson", "How are you?"),
        ]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Tim")

        assert "message_count: 3" in result

    def test_header_media_count(self):
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-08-02T16:56:00", "Tim Cocking", "IMG-20150802-WA0004.jpg", True, "image"),
            _msg("2015-08-02T16:57:00", "Tim Cocking", "See pics"),
        ]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Tim")

        assert "media_count: 1" in result

    def test_header_date_range(self):
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2026-03-25T10:00:00", "Tim Cocking", "Latest"),
        ]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Tim")

        assert "date_range: 2015-07-29..2026-03-25" in result

    def test_header_body_sha256(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        body = fmt.format_messages_only(msgs)
        expected_hash = _sha256(body)

        assert f"body_sha256: {expected_hash}" in result

    def test_body_sha256_matches_body_content(self):
        """The hash in the header must match SHA-256 of everything below the header."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:06:00", "Tim Cocking", "World"),
        ]
        result = fmt.format_transcript(msgs, "jid@s.whatsapp.net", "Test")

        # Extract hash from header
        match = re.search(r"body_sha256: ([a-f0-9]{64})", result)
        assert match, "body_sha256 not found in header"
        header_hash = match.group(1)

        # Compute from format_messages_only
        body = fmt.format_messages_only(msgs)
        computed_hash = _sha256(body)

        assert header_hash == computed_hash


# ---------------------------------------------------------------------------
# Day headers
# ---------------------------------------------------------------------------

class TestDayHeaders:
    """Tests for day grouping with ## YYYY-MM-DD headers."""

    def test_single_day_header(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        body = fmt.format_messages_only(msgs)

        assert "## 2015-07-29" in body

    def test_multiple_day_headers(self):
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-08-02T16:56:00", "Tim Cocking", "See pics"),
        ]
        body = fmt.format_messages_only(msgs)

        assert "## 2015-07-29" in body
        assert "## 2015-08-02" in body

    def test_day_header_format_iso8601(self):
        fmt = SpecFormatter()
        msgs = [_msg("2026-01-05T09:00:00", "AJ Anderson", "New year")]
        body = fmt.format_messages_only(msgs)

        # Must be YYYY-MM-DD, not other formats
        assert "## 2026-01-05" in body

    def test_blank_line_before_day_header(self):
        """There should be a blank line before each day header (except the first)."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-08-02T16:56:00", "Tim Cocking", "See pics"),
        ]
        body = fmt.format_messages_only(msgs)

        # Between the two days there should be a blank line
        assert "\n\n## 2015-08-02" in body

    def test_blank_line_after_day_header(self):
        """There should be a blank line after each day header."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        body = fmt.format_messages_only(msgs)

        assert "## 2015-07-29\n\n[" in body

    def test_same_day_messages_grouped(self):
        """Messages on the same day should share one header."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "First"),
            _msg("2015-07-29T00:11:00", "Tim Cocking", "Second"),
            _msg("2015-07-29T00:12:00", "Tim Cocking", "Third"),
        ]
        body = fmt.format_messages_only(msgs)

        # Only one day header
        assert body.count("## 2015-07-29") == 1


# ---------------------------------------------------------------------------
# Message format
# ---------------------------------------------------------------------------

class TestMessageFormat:
    """Tests for basic message line formatting."""

    def test_text_message_format(self):
        """[HH:MM] Sender: content"""
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Do you know Woodville church, Cardiff.")]
        body = fmt.format_messages_only(msgs)

        assert "[00:05] AJ Anderson: Do you know Woodville church, Cardiff." in body

    def test_24_hour_time_format(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T16:56:00", "Tim Cocking", "Hello")]
        body = fmt.format_messages_only(msgs)

        assert "[16:56]" in body

    def test_leading_zero_in_time(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T09:05:00", "Tim Cocking", "Morning")]
        body = fmt.format_messages_only(msgs)

        assert "[09:05]" in body

    def test_spec_example_messages(self):
        """Test against the exact example from the spec."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Do you know Woodville church, Cardiff."),
            _msg("2015-07-29T00:11:00", "Tim Cocking", "Wrong. She's a bute."),
            _msg("2015-07-29T00:12:00", "Tim Cocking", "Don't know this church."),
            _msg("2015-07-29T00:13:00", "AJ Anderson",
                 "Met a couple from that church yesterday. Wouldn't have surprised me."),
        ]
        body = fmt.format_messages_only(msgs)

        assert "[00:05] AJ Anderson: Do you know Woodville church, Cardiff." in body
        assert "[00:11] Tim Cocking: Wrong. She's a bute." in body
        assert "[00:12] Tim Cocking: Don't know this church." in body
        assert "[00:13] AJ Anderson: Met a couple from that church yesterday." in body


# ---------------------------------------------------------------------------
# Multi-line messages
# ---------------------------------------------------------------------------

class TestMultiLineMessages:
    """Tests for multi-line message continuation."""

    def test_multiline_preserves_content(self):
        """Multi-line messages: continuation lines with no prefix."""
        fmt = SpecFormatter()
        content = (
            "Could you rifle through my mail.\n"
            "My credit card expires next month so wondering\n"
            "if they sent a new one."
        )
        msgs = [_msg("2015-07-29T13:20:00", "AJ Anderson", content)]
        body = fmt.format_messages_only(msgs)

        assert "[13:20] AJ Anderson: Could you rifle through my mail." in body
        assert "My credit card expires next month so wondering" in body
        assert "if they sent a new one." in body

    def test_multiline_no_timestamp_on_continuation(self):
        """Continuation lines should not have [HH:MM] prefix."""
        fmt = SpecFormatter()
        content = "Line one.\nLine two.\nLine three."
        msgs = [_msg("2015-07-29T13:20:00", "AJ Anderson", content)]
        body = fmt.format_messages_only(msgs)

        lines = body.split("\n")
        # Find continuation lines (after the message line)
        msg_idx = next(i for i, l in enumerate(lines) if "[13:20]" in l)
        continuation_1 = lines[msg_idx + 1]
        continuation_2 = lines[msg_idx + 2]

        assert not continuation_1.startswith("[")
        assert not continuation_2.startswith("[")


# ---------------------------------------------------------------------------
# Media messages
# ---------------------------------------------------------------------------

class TestMediaMessages:
    """Tests for typed media tag formatting."""

    def test_photo_tag(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T16:56:00", "Tim Cocking",
                      "IMG-20150802-WA0004.jpg", True, "image")]
        body = fmt.format_messages_only(msgs)

        assert "<photo>" in body
        assert "<Media omitted>" not in body

    def test_video_tag(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T14:22:00", "AJ Anderson",
                      "VID-20150802-WA0001.mp4", True, "video")]
        body = fmt.format_messages_only(msgs)

        assert "<video>" in body

    def test_sticker_tag(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T09:30:00", "Tim Cocking",
                      "sticker omitted", True, "sticker")]
        body = fmt.format_messages_only(msgs)

        assert "<sticker>" in body

    def test_gif_tag(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T09:30:00", "Tim Cocking",
                      "GIF omitted", True, "gif")]
        body = fmt.format_messages_only(msgs)

        assert "<gif>" in body

    def test_document_with_descriptive_filename(self):
        """Documents with descriptive names include the filename."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T11:45:00", "AJ Anderson",
                      "Flight_Booking_Confirmation.pdf (file attached)", True, "document")]
        body = fmt.format_messages_only(msgs)

        assert "<document Flight_Booking_Confirmation.pdf>" in body

    def test_document_with_auto_filename_omitted(self):
        """Auto-generated filenames should not be included for documents."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T11:45:00", "AJ Anderson",
                      "DOC-20150802-WA0001.pdf (file attached)", True, "document")]
        body = fmt.format_messages_only(msgs)

        # Auto-generated name should be stripped
        assert "<document>" in body

    def test_photo_auto_filename_omitted(self):
        """Auto-generated photo filenames should NOT appear."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T16:56:00", "Tim Cocking",
                      "IMG-20150802-WA0004.jpg (file attached)", True, "image")]
        body = fmt.format_messages_only(msgs)

        assert "<photo>" in body
        assert "IMG-20150802" not in body

    def test_unknown_media_type(self):
        """Unknown media type should use <media> tag."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T16:56:00", "Tim Cocking",
                      "some media", True, "unknown_type")]
        body = fmt.format_messages_only(msgs)

        assert "<media>" in body

    def test_no_media_omitted_tag(self):
        """<Media omitted> must never appear in output."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-08-02T16:56:00", "Tim Cocking",
                 "<media omitted>", True, "image"),
            _msg("2015-08-02T16:57:00", "AJ Anderson",
                 "image omitted", True, "image"),
        ]
        body = fmt.format_messages_only(msgs)

        assert "Media omitted" not in body
        assert "media omitted" not in body.lower().replace("<media>", "")
        assert "<photo>" in body

    def test_media_message_line_format(self):
        """Media lines should follow [HH:MM] Sender: <tag> format."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T16:56:00", "Tim Cocking",
                      "IMG-20150802-WA0004.jpg", True, "image")]
        body = fmt.format_messages_only(msgs)

        assert "[16:56] Tim Cocking: <photo>" in body


# ---------------------------------------------------------------------------
# Voice messages + transcription
# ---------------------------------------------------------------------------

class TestVoiceMessages:
    """Tests for voice message formatting with optional transcription."""

    def test_voice_tag(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T10:15:00", "Tim Cocking",
                      "PTT-20150802-WA0001.opus (file attached)", True, "audio")]
        body = fmt.format_messages_only(msgs)

        assert "[10:15] Tim Cocking: <voice>" in body

    def test_voice_with_transcription_inline(self):
        """Voice message with [Transcription]: in content."""
        fmt = SpecFormatter()
        msgs = [_msg(
            "2015-08-02T10:15:00", "Tim Cocking",
            "PTT-20150802-WA0001.opus [Transcription]: Bring a frying pan.",
            True, "audio",
        )]
        body = fmt.format_messages_only(msgs)

        assert "[10:15] Tim Cocking: <voice>" in body
        assert "  [Transcription]: Bring a frying pan." in body

    def test_voice_with_transcription_next_message(self):
        """Transcription as the next message in the list."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-08-02T10:15:00", "Tim Cocking",
                 "PTT-20150802-WA0001.opus (file attached)", True, "audio"),
            _msg("2015-08-02T10:15:00", "Tim Cocking",
                 "[Transcription]: Bring a frying pan, spatula, butter and stuff."),
        ]
        body = fmt.format_messages_only(msgs)

        assert "  [Transcription]: Bring a frying pan, spatula, butter and stuff." in body

    def test_voice_without_transcription(self):
        """Voice message without transcription — just <voice>, no [Transcription] line."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T10:15:00", "Tim Cocking",
                      "PTT-20150802-WA0001.opus (file attached)", True, "audio")]
        body = fmt.format_messages_only(msgs)

        assert "[10:15] Tim Cocking: <voice>" in body
        assert "[Transcription]" not in body

    def test_transcription_two_space_indent(self):
        """Transcription line must have exactly two-space indent."""
        fmt = SpecFormatter()
        msgs = [_msg(
            "2015-08-02T10:15:00", "Tim Cocking",
            "PTT.opus [Transcription]: Hello there.",
            True, "audio",
        )]
        body = fmt.format_messages_only(msgs)

        # Find the transcription line
        for line in body.split("\n"):
            if "[Transcription]" in line:
                assert line.startswith("  [Transcription]:"), \
                    f"Transcription line should start with two spaces: {line!r}"
                break
        else:
            pytest.fail("Transcription line not found")


# ---------------------------------------------------------------------------
# System events
# ---------------------------------------------------------------------------

class TestSystemEvents:
    """Tests for system event message formatting."""

    def test_system_event_no_sender_prefix(self):
        """System events: [HH:MM] event text (no sender)."""
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T17:54:00", "",
                      "Your security code with Tim Cocking changed. Tap to learn more.")]
        body = fmt.format_messages_only(msgs)

        assert "[17:54] Your security code with Tim Cocking changed." in body
        # Should NOT have a colon after ] followed by empty sender
        assert "[17:54] : " not in body

    def test_system_event_added(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T22:07:00", "",
                      "+49 174 9580928 was added")]
        body = fmt.format_messages_only(msgs)

        assert "[22:07] +49 174 9580928 was added" in body

    def test_system_event_encryption_notice(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:00:00", "",
                      "Messages and calls are end-to-end encrypted.")]
        body = fmt.format_messages_only(msgs)

        assert "[00:00] Messages and calls are end-to-end encrypted." in body


# ---------------------------------------------------------------------------
# View-once messages
# ---------------------------------------------------------------------------

class TestViewOnceMessages:
    """Tests for view-once message formatting."""

    def test_view_once_photo(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T09:30:00", "Tim Cocking",
                      "view once photo", True, "image")]
        body = fmt.format_messages_only(msgs)

        assert "<view-once photo>" in body

    def test_view_once_voice(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-08-02T14:16:00", "AJ Anderson",
                      "view once voice message", True, "audio")]
        body = fmt.format_messages_only(msgs)

        assert "<view-once voice>" in body


# ---------------------------------------------------------------------------
# format_messages_only
# ---------------------------------------------------------------------------

class TestFormatMessagesOnly:
    """Tests for the format_messages_only method."""

    def test_empty_messages(self):
        fmt = SpecFormatter()
        result = fmt.format_messages_only([])

        assert result == ""

    def test_returns_string(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_messages_only(msgs)

        assert isinstance(result, str)

    def test_no_frontmatter_in_body(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_messages_only(msgs)

        assert "---" not in result
        assert "cssclasses" not in result

    def test_no_integrity_header_in_body(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = fmt.format_messages_only(msgs)

        assert "<!-- TRANSCRIPT METADATA" not in result
        assert "body_sha256" not in result


# ---------------------------------------------------------------------------
# format_transcript integration
# ---------------------------------------------------------------------------

class TestFormatTranscript:
    """Tests for the full format_transcript method."""

    def test_complete_structure(self):
        """Full output has frontmatter, header, blank line, body."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:06:00", "Tim Cocking", "Hi"),
        ]
        result = fmt.format_transcript(msgs, "447956173473@s.whatsapp.net", "Tim Cocking")

        # Frontmatter
        assert result.startswith("---\n")
        # Integrity header
        assert "<!-- TRANSCRIPT METADATA" in result
        # Day header
        assert "## 2015-07-29" in result
        # Messages
        assert "[00:05] AJ Anderson: Hello" in result
        assert "[00:06] Tim Cocking: Hi" in result

    def test_empty_messages_produces_valid_output(self):
        fmt = SpecFormatter()
        result = fmt.format_transcript([], "jid@s.whatsapp.net", "Nobody")

        assert "---" in result
        assert "<!-- TRANSCRIPT METADATA" in result
        assert "message_count: 0" in result
        assert "date_range: none" in result

    def test_hash_deterministic(self):
        """Same input should produce same body_sha256."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:06:00", "Tim Cocking", "World"),
        ]

        body1 = fmt.format_messages_only(msgs)
        body2 = fmt.format_messages_only(msgs)

        assert _sha256(body1) == _sha256(body2)


# ---------------------------------------------------------------------------
# Spec example: full transcript section
# ---------------------------------------------------------------------------

class TestSpecExamples:
    """Test against the exact examples from transcript-format-spec.md."""

    def test_spec_photo_section(self):
        """Match the photo section from the spec."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-08-02T16:56:00", "Tim Cocking",
                 "IMG-20150802-WA0004.jpg (file attached)", True, "image"),
            _msg("2015-08-02T16:56:00", "Tim Cocking",
                 "IMG-20150802-WA0005.jpg (file attached)", True, "image"),
            _msg("2015-08-02T16:56:00", "Tim Cocking",
                 "IMG-20150802-WA0006.jpg (file attached)", True, "image"),
            _msg("2015-08-02T16:56:00", "Tim Cocking",
                 "IMG-20150802-WA0007.jpg (file attached)", True, "image"),
            _msg("2015-08-02T16:56:00", "Tim Cocking", "See pics"),
        ]
        body = fmt.format_messages_only(msgs)

        # All photos should use <photo> tag without filename
        assert body.count("<photo>") == 4
        assert "See pics" in body
        assert "IMG-" not in body

    def test_spec_voice_transcription_example(self):
        """Match the voice + transcription example from the spec."""
        fmt = SpecFormatter()
        transcription_text = (
            "Bring a frying pan, spatula, butter and stuff, "
            "and a knife if you want to fry it up with some black pudding."
        )
        msgs = [_msg(
            "2015-08-02T10:15:00", "Tim Cocking",
            f"PTT.opus [Transcription]: {transcription_text}",
            True, "audio",
        )]
        body = fmt.format_messages_only(msgs)

        assert "[10:15] Tim Cocking: <voice>" in body
        assert f"  [Transcription]: {transcription_text}" in body

    def test_spec_document_example(self):
        """Match document with descriptive filename from spec."""
        fmt = SpecFormatter()
        msgs = [_msg(
            "2015-08-02T11:45:00", "AJ Anderson",
            "Flight_Booking_Confirmation.pdf (file attached)",
            True, "document",
        )]
        body = fmt.format_messages_only(msgs)

        assert "<document Flight_Booking_Confirmation.pdf>" in body

    def test_spec_system_events(self):
        """Match system event examples from the spec."""
        fmt = SpecFormatter()
        msgs = [
            _msg("2015-07-29T17:54:00", "",
                 "Your security code with Tim Cocking changed. Tap to learn more."),
            _msg("2015-07-29T22:07:00", "",
                 "+49 174 9580928 was added"),
            _msg("2015-07-29T00:00:00", "",
                 "Messages and calls are end-to-end encrypted."),
        ]
        body = fmt.format_messages_only(msgs)

        assert "[17:54] Your security code with Tim Cocking changed. Tap to learn more." in body
        assert "[22:07] +49 174 9580928 was added" in body
        assert "[00:00] Messages and calls are end-to-end encrypted." in body


# ---------------------------------------------------------------------------
# User display name
# ---------------------------------------------------------------------------

class TestUserDisplayName:
    """Tests for user display name resolution."""

    def test_custom_user_display_name(self):
        fmt = SpecFormatter(user_display_name="Andrew Anderson")
        msgs = [_msg("2015-07-29T00:05:00", "Me", "Hello")]
        body = fmt.format_messages_only(msgs)

        assert "Andrew Anderson: Hello" in body
        assert "Me:" not in body

    def test_default_user_display_name(self):
        fmt = SpecFormatter()
        msgs = [_msg("2015-07-29T00:05:00", "Me", "Hello")]
        body = fmt.format_messages_only(msgs)

        assert "AJ Anderson: Hello" in body
