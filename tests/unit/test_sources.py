"""
Test suite for the sources module.

Tests the MessageSource abstraction, AppiumSource adapter, TranscriptSource
reader, and backward compatibility of the extended Message dataclass.
"""

from datetime import datetime
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.processing.transcript_parser import (
    Message,
    MediaReference,
    TranscriptParser,
)
from whatsapp_chat_autoexport.sources import (
    AppiumSource,
    ChatInfo,
    MessageSource,
    TranscriptSource,
)
from whatsapp_chat_autoexport.utils.logger import Logger


# =========================================================================
# Message dataclass backward compatibility
# =========================================================================


@pytest.mark.unit
class TestMessageBackwardCompat:
    """Verify the extended Message dataclass remains backward compatible."""

    def test_existing_fields_unchanged(self):
        """Creating a Message without the new fields still works."""
        msg = Message(
            timestamp=datetime(2024, 6, 15, 10, 30, 0),
            sender="Alice",
            content="Hello",
        )
        assert msg.sender == "Alice"
        assert msg.is_media is False
        assert msg.media_type is None
        assert msg.raw_line == ""
        assert msg.line_number == 0

    def test_new_fields_have_defaults(self):
        """New fields default to None / 'unknown'."""
        msg = Message(
            timestamp=datetime(2024, 6, 15, 10, 30, 0),
            sender="Alice",
            content="Hello",
        )
        assert msg.message_id is None
        assert msg.source == "unknown"

    def test_new_fields_can_be_set(self):
        """New fields can be explicitly provided."""
        msg = Message(
            timestamp=datetime(2024, 6, 15, 10, 30, 0),
            sender="Alice",
            content="Hello",
            message_id="abc123",
            source="mcp",
        )
        assert msg.message_id == "abc123"
        assert msg.source == "mcp"

    def test_frozen_media_reference_still_works(self):
        """MediaReference (frozen) still accepts a Message with new fields."""
        msg = Message(
            timestamp=datetime(2024, 6, 15, 10, 30, 0),
            sender="Alice",
            content="<Media omitted>",
            is_media=True,
            media_type="image",
            message_id="xyz",
            source="appium",
        )
        ref = MediaReference(
            message=msg,
            media_type="image",
            timestamp=msg.timestamp,
            sender=msg.sender,
            line_number=1,
        )
        assert ref.message.message_id == "xyz"


# =========================================================================
# ChatInfo dataclass
# =========================================================================


@pytest.mark.unit
class TestChatInfo:
    """Tests for the ChatInfo dataclass."""

    def test_minimal_construction(self):
        """ChatInfo can be created with just jid and name."""
        info = ChatInfo(jid="alice@s.whatsapp.net", name="Alice")
        assert info.jid == "alice@s.whatsapp.net"
        assert info.name == "Alice"
        assert info.last_message_time is None
        assert info.message_count == 0

    def test_full_construction(self):
        """ChatInfo can be created with all fields."""
        ts = datetime(2024, 6, 15, 10, 30, 0)
        info = ChatInfo(
            jid="alice@s.whatsapp.net",
            name="Alice",
            last_message_time=ts,
            message_count=42,
        )
        assert info.last_message_time == ts
        assert info.message_count == 42


# =========================================================================
# MessageSource abstract class
# =========================================================================


@pytest.mark.unit
class TestMessageSourceABC:
    """Verify the abstract interface cannot be instantiated directly."""

    def test_cannot_instantiate(self):
        """MessageSource is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            MessageSource()

    def test_concrete_subclass(self):
        """A concrete subclass that implements all methods can be instantiated."""

        class DummySource(MessageSource):
            def get_chats(self):
                return []

            def get_messages(self, chat_id, after=None, limit=None):
                return []

            def get_media(self, message_id):
                return None

        source = DummySource()
        assert source.get_chats() == []
        assert source.get_messages("test") == []
        assert source.get_media("test") is None


# =========================================================================
# AppiumSource
# =========================================================================


@pytest.mark.unit
class TestAppiumSource:
    """Tests for the AppiumSource adapter."""

    @pytest.fixture
    def appium_export(self, tmp_path):
        """Create a minimal Appium export directory structure."""
        # Chat 1: Alice
        alice_dir = tmp_path / "Alice"
        alice_dir.mkdir()
        transcript = alice_dir / "WhatsApp Chat with Alice.txt"
        transcript.write_text(
            "1/15/24, 10:30 AM - Alice: Hello!\n"
            "1/15/24, 10:31 AM - Me: Hi there\n"
            "1/15/24, 10:32 AM - Alice: image omitted\n"
        )

        # Chat 2: Bob
        bob_dir = tmp_path / "Bob"
        bob_dir.mkdir()
        transcript_b = bob_dir / "WhatsApp Chat with Bob.txt"
        transcript_b.write_text(
            "2/20/24, 3:00 PM - Bob: Hey\n"
        )

        # Non-chat file at root (should be ignored)
        (tmp_path / "readme.txt").write_text("not a chat")

        return tmp_path

    def test_get_chats(self, appium_export):
        """get_chats returns one ChatInfo per chat directory."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        chats = source.get_chats()

        names = {c.name for c in chats}
        assert "Alice" in names
        assert "Bob" in names
        assert len(chats) == 2

    def test_chat_info_has_message_count(self, appium_export):
        """ChatInfo includes the correct message count."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        chats = {c.name: c for c in source.get_chats()}

        assert chats["Alice"].message_count == 3
        assert chats["Bob"].message_count == 1

    def test_chat_info_has_last_message_time(self, appium_export):
        """ChatInfo includes the last message timestamp."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        chats = {c.name: c for c in source.get_chats()}

        assert chats["Alice"].last_message_time is not None
        assert chats["Alice"].last_message_time.minute == 32

    def test_get_messages(self, appium_export):
        """get_messages returns Message objects tagged with source='appium'."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        assert len(messages) == 3
        assert messages[0].sender == "Alice"
        assert messages[0].content == "Hello!"
        assert all(m.source == "appium" for m in messages)

    def test_get_messages_after_filter(self, appium_export):
        """get_messages respects the 'after' parameter."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        cutoff = datetime(2024, 1, 15, 10, 30, 30)
        messages = source.get_messages("Alice", after=cutoff)

        assert len(messages) == 2
        assert all(m.timestamp > cutoff for m in messages)

    def test_get_messages_limit(self, appium_export):
        """get_messages respects the 'limit' parameter."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice", limit=1)

        assert len(messages) == 1

    def test_get_messages_nonexistent_chat(self, appium_export):
        """get_messages returns empty list for a missing chat."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("NonExistent")

        assert messages == []

    def test_get_media_returns_none(self, appium_export):
        """get_media is not supported and returns None."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        assert source.get_media("any_id") is None

    def test_caching(self, appium_export):
        """Repeated calls use the cache and return the same data."""
        source = AppiumSource(appium_export, logger=Logger(log_file_enabled=False))
        msgs_1 = source.get_messages("Alice")
        msgs_2 = source.get_messages("Alice")

        # Cached — same content
        assert len(msgs_1) == len(msgs_2)
        assert all(m1.content == m2.content for m1, m2 in zip(msgs_1, msgs_2))

    def test_missing_export_dir(self, tmp_path):
        """get_chats returns empty list when export_dir doesn't exist."""
        source = AppiumSource(
            tmp_path / "nonexistent", logger=Logger(log_file_enabled=False)
        )
        assert source.get_chats() == []

    def test_produces_same_messages_as_parser(self, appium_export):
        """AppiumSource produces the same messages as TranscriptParser directly."""
        logger = Logger(log_file_enabled=False)
        source = AppiumSource(appium_export, logger=logger)
        source_messages = source.get_messages("Alice")

        parser = TranscriptParser(logger=logger)
        transcript = appium_export / "Alice" / "WhatsApp Chat with Alice.txt"
        parser_messages, _ = parser.parse_transcript(transcript)

        assert len(source_messages) == len(parser_messages)
        for sm, pm in zip(source_messages, parser_messages):
            assert sm.timestamp == pm.timestamp
            # AppiumSource normalises "Me" to user_display_name
            expected_sender = pm.sender if pm.sender != "Me" else "AJ Anderson"
            assert sm.sender == expected_sender
            assert sm.content == pm.content
            assert sm.is_media == pm.is_media


# =========================================================================
# TranscriptSource — legacy .txt format
# =========================================================================


@pytest.mark.unit
class TestTranscriptSourceLegacy:
    """Tests for TranscriptSource reading legacy .txt transcripts."""

    @pytest.fixture
    def legacy_vault(self, tmp_path):
        """Create a vault-like directory with legacy .txt transcripts."""
        # Nested layout: chat_dir/transcript.txt
        alice_dir = tmp_path / "Alice"
        alice_dir.mkdir()
        (alice_dir / "transcript.txt").write_text(
            "1/15/24, 10:30 AM - Alice: Hello!\n"
            "1/15/24, 10:31 AM - Me: Hi there\n"
        )

        # Flat layout: chat_name.txt
        (tmp_path / "Bob.txt").write_text(
            "2/20/24, 3:00 PM - Bob: Hey\n"
            "2/20/24, 3:01 PM - Me: What's up\n"
        )

        return tmp_path

    def test_get_chats_nested(self, legacy_vault):
        """Detects chats in nested directory layout."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        chats = source.get_chats()

        names = {c.name for c in chats}
        assert "Alice" in names

    def test_get_chats_flat(self, legacy_vault):
        """Detects chats in flat file layout."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        chats = source.get_chats()

        names = {c.name for c in chats}
        assert "Bob" in names

    def test_get_messages_legacy(self, legacy_vault):
        """Messages from legacy .txt are parsed and tagged source='transcript'."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        assert len(messages) == 2
        assert messages[0].sender == "Alice"
        assert all(m.source == "transcript" for m in messages)

    def test_get_messages_after_filter(self, legacy_vault):
        """get_messages respects the 'after' parameter for legacy format."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        cutoff = datetime(2024, 1, 15, 10, 30, 30)
        messages = source.get_messages("Alice", after=cutoff)

        assert len(messages) == 1
        assert messages[0].sender == "Me"

    def test_get_messages_limit(self, legacy_vault):
        """get_messages respects the 'limit' parameter."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice", limit=1)

        assert len(messages) == 1

    def test_nonexistent_chat(self, legacy_vault):
        """Returns empty list for unknown chat."""
        source = TranscriptSource(legacy_vault, logger=Logger(log_file_enabled=False))
        assert source.get_messages("Ghost") == []


# =========================================================================
# TranscriptSource — new .md format
# =========================================================================


@pytest.mark.unit
class TestTranscriptSourceMd:
    """Tests for TranscriptSource reading new .md spec transcripts."""

    @pytest.fixture
    def md_vault(self, tmp_path):
        """Create a vault-like directory with .md spec transcripts."""
        alice_dir = tmp_path / "Alice"
        alice_dir.mkdir()
        (alice_dir / "transcript.md").write_text(
            "---\n"
            "cssclasses: [whatsapp-transcript, exclude-from-graph]\n"
            "---\n"
            "<!-- integrity: abc123 -->\n"
            "\n"
            "## 2024-06-15\n"
            "\n"
            "[10:30] Alice: Hello!\n"
            "[10:31] Me: Hi there\n"
            "[10:32] Alice: <photo>\n"
            "[10:33] Alice: <voice>\n"
            "  [Transcription]: This is the voice memo content\n"
            "\n"
            "## 2024-06-16\n"
            "\n"
            "[09:00] Alice: Good morning\n"
        )
        # Also create an index.md that should be ignored
        (alice_dir / "index.md").write_text("---\ntype: whatsapp-chat\n---\n")

        return tmp_path

    def test_get_chats_md(self, md_vault):
        """Detects .md transcripts in nested layout."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        chats = source.get_chats()

        names = {c.name for c in chats}
        assert "Alice" in names
        assert len(chats) == 1

    def test_parse_md_messages(self, md_vault):
        """Messages are parsed correctly from .md format."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        assert len(messages) == 5
        assert messages[0].sender == "Alice"
        assert messages[0].content == "Hello!"
        assert messages[0].timestamp == datetime(2024, 6, 15, 10, 30)

    def test_md_day_headers(self, md_vault):
        """Day headers produce correct dates on messages."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        # First four messages are on 2024-06-15
        assert messages[0].timestamp.date().isoformat() == "2024-06-15"
        assert messages[3].timestamp.date().isoformat() == "2024-06-15"

        # Last message is on 2024-06-16
        assert messages[4].timestamp.date().isoformat() == "2024-06-16"

    def test_md_media_detection(self, md_vault):
        """Typed media tags are detected correctly."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        photo_msg = messages[2]
        assert photo_msg.is_media is True
        assert photo_msg.media_type == "image"

        voice_msg = messages[3]
        assert voice_msg.is_media is True
        assert voice_msg.media_type == "audio"

    def test_md_continuation_lines(self, md_vault):
        """Continuation lines (like [Transcription]) are appended to previous message."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        voice_msg = messages[3]
        assert "[Transcription]" in voice_msg.content

    def test_md_source_tag(self, md_vault):
        """All messages from .md are tagged source='transcript'."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        assert all(m.source == "transcript" for m in messages)

    def test_md_frontmatter_skipped(self, md_vault):
        """YAML frontmatter is not parsed as message content."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        for msg in messages:
            assert "cssclasses" not in msg.content
            assert "---" not in msg.content

    def test_md_comment_skipped(self, md_vault):
        """HTML comments are not parsed as message content."""
        source = TranscriptSource(md_vault, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Alice")

        for msg in messages:
            assert "integrity" not in msg.content


# =========================================================================
# TranscriptSource — edge cases
# =========================================================================


@pytest.mark.unit
class TestTranscriptSourceEdgeCases:
    """Edge case tests for TranscriptSource."""

    def test_empty_md_transcript(self, tmp_path):
        """Empty .md file produces no messages."""
        chat_dir = tmp_path / "Empty"
        chat_dir.mkdir()
        (chat_dir / "transcript.md").write_text("")

        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Empty")

        assert messages == []

    def test_md_no_day_headers(self, tmp_path):
        """Messages before any day header are skipped."""
        chat_dir = tmp_path / "NoDates"
        chat_dir.mkdir()
        (chat_dir / "transcript.md").write_text(
            "[10:30] Alice: No date header above\n"
        )

        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("NoDates")

        assert messages == []

    def test_missing_directory(self, tmp_path):
        """Missing transcript_dir returns empty chats."""
        source = TranscriptSource(
            tmp_path / "nonexistent", logger=Logger(log_file_enabled=False)
        )
        assert source.get_chats() == []

    def test_get_media_returns_none(self, tmp_path):
        """get_media always returns None for transcript sources."""
        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        assert source.get_media("anything") is None

    def test_prefers_md_over_txt(self, tmp_path):
        """When both transcript.md and transcript.txt exist, .md is preferred."""
        chat_dir = tmp_path / "Both"
        chat_dir.mkdir()
        (chat_dir / "transcript.txt").write_text(
            "1/15/24, 10:30 AM - Alice: From txt\n"
        )
        (chat_dir / "transcript.md").write_text(
            "---\ncssclasses: [whatsapp-transcript]\n---\n\n"
            "## 2024-01-15\n\n"
            "[10:30] Alice: From md\n"
        )

        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("Both")

        assert len(messages) == 1
        assert messages[0].content == "From md"

    def test_multiline_md_message(self, tmp_path):
        """Multi-line message content is captured."""
        chat_dir = tmp_path / "MultiLine"
        chat_dir.mkdir()
        (chat_dir / "transcript.md").write_text(
            "---\ncssclasses: [whatsapp-transcript]\n---\n\n"
            "## 2024-01-15\n\n"
            "[10:30] Alice: Line one\n"
            "Line two\n"
            "Line three\n"
            "[10:31] Bob: Next message\n"
        )

        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("MultiLine")

        assert len(messages) == 2
        assert "Line two" in messages[0].content
        assert "Line three" in messages[0].content

    def test_md_all_media_types(self, tmp_path):
        """All spec media tags are detected."""
        chat_dir = tmp_path / "MediaTypes"
        chat_dir.mkdir()
        (chat_dir / "transcript.md").write_text(
            "---\ncssclasses: [whatsapp-transcript]\n---\n\n"
            "## 2024-01-15\n\n"
            "[10:30] A: <photo>\n"
            "[10:31] A: <video>\n"
            "[10:32] A: <voice>\n"
            "[10:33] A: <document>\n"
            "[10:34] A: <sticker>\n"
        )

        source = TranscriptSource(tmp_path, logger=Logger(log_file_enabled=False))
        messages = source.get_messages("MediaTypes")

        expected_types = ["image", "video", "audio", "document", "sticker"]
        actual_types = [m.media_type for m in messages]
        assert actual_types == expected_types
        assert all(m.is_media for m in messages)
