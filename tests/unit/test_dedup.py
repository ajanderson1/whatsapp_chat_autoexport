"""
Test suite for the deduplication engine.

Tests both full dedup (deduplicate) and incremental dedup (find_new_messages)
across various source combinations, edge cases, and conflict scenarios.
"""

from datetime import datetime

import pytest

from whatsapp_chat_autoexport.processing.transcript_parser import Message
from whatsapp_chat_autoexport.processing.dedup import (
    deduplicate,
    find_new_messages,
    _dedup_key,
    _compound_key,
)


# =========================================================================
# Helpers
# =========================================================================


def _msg(
    ts: datetime,
    sender: str = "Alice",
    content: str = "Hello",
    source: str = "unknown",
    message_id: str | None = None,
    line_number: int = 0,
    is_media: bool = False,
    media_type: str | None = None,
) -> Message:
    """Convenience factory for test messages."""
    return Message(
        timestamp=ts,
        sender=sender,
        content=content,
        source=source,
        message_id=message_id,
        line_number=line_number,
        is_media=is_media,
        media_type=media_type,
    )


# =========================================================================
# deduplicate — basic scenarios
# =========================================================================


@pytest.mark.unit
class TestDeduplicateBasic:
    """Basic deduplication scenarios."""

    def test_empty_input(self):
        """Empty input produces empty output."""
        assert deduplicate([]) == []

    def test_single_message(self):
        """Single message is returned as-is."""
        msg = _msg(datetime(2024, 6, 15, 10, 30), content="Only one")
        result = deduplicate([msg])
        assert len(result) == 1
        assert result[0].content == "Only one"

    def test_no_overlap_all_retained(self):
        """Distinct messages from the same source are all kept."""
        msgs = [
            _msg(datetime(2024, 6, 15, 10, 30), content="First"),
            _msg(datetime(2024, 6, 15, 10, 31), content="Second"),
            _msg(datetime(2024, 6, 15, 10, 32), content="Third"),
        ]
        result = deduplicate(msgs)
        assert len(result) == 3

    def test_full_overlap_no_duplicates(self):
        """Identical messages produce a single copy each."""
        msg_a = _msg(datetime(2024, 6, 15, 10, 30), content="Same")
        msg_b = _msg(datetime(2024, 6, 15, 10, 30), content="Same")
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 1

    def test_partial_overlap(self):
        """Only duplicated messages are collapsed; unique ones survive."""
        shared = _msg(datetime(2024, 6, 15, 10, 30), content="Shared")
        unique_a = _msg(datetime(2024, 6, 15, 10, 29), content="Only A")
        unique_b = _msg(datetime(2024, 6, 15, 10, 31), content="Only B")
        shared_dup = _msg(datetime(2024, 6, 15, 10, 30), content="Shared")

        result = deduplicate([shared, unique_a, unique_b, shared_dup])
        assert len(result) == 3
        contents = {m.content for m in result}
        assert contents == {"Shared", "Only A", "Only B"}

    def test_sorted_chronologically(self):
        """Output is sorted by timestamp regardless of input order."""
        msgs = [
            _msg(datetime(2024, 6, 15, 10, 32), content="Third"),
            _msg(datetime(2024, 6, 15, 10, 30), content="First"),
            _msg(datetime(2024, 6, 15, 10, 31), content="Second"),
        ]
        result = deduplicate(msgs)
        assert [m.content for m in result] == ["First", "Second", "Third"]

    def test_idempotent(self):
        """Running dedup twice produces identical output."""
        msgs = [
            _msg(datetime(2024, 6, 15, 10, 30), content="A", source="appium"),
            _msg(datetime(2024, 6, 15, 10, 30), content="A", source="mcp", message_id="1"),
            _msg(datetime(2024, 6, 15, 10, 31), content="B"),
        ]
        first_pass = deduplicate(msgs)
        second_pass = deduplicate(first_pass)

        assert len(first_pass) == len(second_pass)
        for m1, m2 in zip(first_pass, second_pass):
            assert m1.timestamp == m2.timestamp
            assert m1.sender == m2.sender
            assert m1.content == m2.content
            assert m1.source == m2.source
            assert m1.message_id == m2.message_id


# =========================================================================
# deduplicate — conflict resolution
# =========================================================================


@pytest.mark.unit
class TestDeduplicateConflicts:
    """Conflict resolution and source preference tests."""

    def test_mcp_preferred_over_appium(self):
        """When MCP and Appium have the same message, MCP wins."""
        appium_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="appium",
        )
        mcp_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="mcp",
            message_id="msg_001",
        )
        result = deduplicate([appium_msg, mcp_msg])
        assert len(result) == 1
        assert result[0].source == "mcp"
        assert result[0].message_id == "msg_001"

    def test_mcp_preferred_regardless_of_order(self):
        """MCP wins even when it appears first in the list."""
        mcp_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="mcp",
            message_id="msg_001",
        )
        appium_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="appium",
        )
        result = deduplicate([mcp_msg, appium_msg])
        assert len(result) == 1
        assert result[0].source == "mcp"

    def test_same_timestamp_different_content_kept(self):
        """Same timestamp + sender but different content are NOT duplicates."""
        msg_a = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Message A",
            source="appium",
        )
        msg_b = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Message B",
            source="appium",
        )
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 2

    def test_same_content_different_timestamps_kept(self):
        """Same content at different times are NOT duplicates."""
        msg_a = _msg(datetime(2024, 6, 15, 10, 30), content="Repeated")
        msg_b = _msg(datetime(2024, 6, 15, 11, 30), content="Repeated")
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 2

    def test_same_content_same_minute_different_sources_deduped(self):
        """Same content in the same minute from different sources is a duplicate."""
        appium = _msg(
            datetime(2024, 6, 15, 10, 30, 0),
            content="Exact same",
            source="appium",
        )
        mcp = _msg(
            datetime(2024, 6, 15, 10, 30, 45),
            content="Exact same",
            source="mcp",
            message_id="m1",
        )
        result = deduplicate([appium, mcp])
        assert len(result) == 1
        assert result[0].source == "mcp"

    def test_same_message_id_different_sources_mcp_wins(self):
        """Two messages with the same message_id: MCP version kept."""
        transcript_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="transcript",
            message_id="shared_id",
        )
        mcp_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="mcp",
            message_id="shared_id",
        )
        result = deduplicate([transcript_msg, mcp_msg])
        assert len(result) == 1
        assert result[0].source == "mcp"

    def test_mcp_preferred_over_transcript(self):
        """MCP source is preferred over transcript source."""
        transcript_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="transcript",
        )
        mcp_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="mcp",
            message_id="m1",
        )
        result = deduplicate([transcript_msg, mcp_msg])
        assert len(result) == 1
        assert result[0].source == "mcp"

    def test_appium_preferred_over_transcript(self):
        """Appium source is preferred over transcript source."""
        transcript_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="transcript",
        )
        appium_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="appium",
        )
        result = deduplicate([transcript_msg, appium_msg])
        assert len(result) == 1
        assert result[0].source == "appium"


# =========================================================================
# deduplicate — dedup key logic
# =========================================================================


@pytest.mark.unit
class TestDedupKeys:
    """Tests for dedup key generation."""

    def test_message_id_based_dedup(self):
        """Messages with the same message_id are deduplicated."""
        msg_a = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Version A",
            source="mcp",
            message_id="unique_id_1",
        )
        msg_b = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Version B",
            source="mcp",
            message_id="unique_id_1",
        )
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 1

    def test_compound_key_dedup_when_no_message_id(self):
        """Without message_id, compound key (timestamp_minute + sender + content[:80]) is used."""
        msg_a = _msg(
            datetime(2024, 6, 15, 10, 30, 0),
            sender="Alice",
            content="Hello world",
            source="appium",
        )
        msg_b = _msg(
            datetime(2024, 6, 15, 10, 30, 45),
            sender="Alice",
            content="Hello world",
            source="transcript",
        )
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 1

    def test_mixed_sources_some_with_message_id(self):
        """Cross-source dedup: MCP (with ID) and Appium (without) for same message."""
        mcp_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="mcp",
            message_id="m1",
        )
        appium_msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hello",
            source="appium",
        )
        unique_msg = _msg(
            datetime(2024, 6, 15, 10, 31),
            content="Different",
            source="appium",
        )
        # mcp_msg and appium_msg are the same message (same timestamp, sender,
        # content). Even though MCP has message_id and Appium doesn't, both
        # share the same compound key, so they're recognised as duplicates.
        # MCP version wins (higher priority).
        result = deduplicate([mcp_msg, appium_msg, unique_msg])
        assert len(result) == 2
        assert result[0].source == "mcp"
        assert result[0].message_id == "m1"
        assert result[1].content == "Different"

    def test_both_with_message_id_dedup(self):
        """Two sources with the same message_id are properly deduped."""
        mcp = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hi",
            source="mcp",
            message_id="shared",
        )
        transcript = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="Hi",
            source="transcript",
            message_id="shared",
        )
        result = deduplicate([mcp, transcript])
        assert len(result) == 1
        assert result[0].source == "mcp"

    def test_both_without_message_id_dedup(self):
        """Two sources without message_id dedup via compound key."""
        appium = _msg(
            datetime(2024, 6, 15, 10, 30, 0),
            sender="Bob",
            content="Test message",
            source="appium",
        )
        transcript = _msg(
            datetime(2024, 6, 15, 10, 30, 59),
            sender="Bob",
            content="Test message",
            source="transcript",
        )
        result = deduplicate([appium, transcript])
        assert len(result) == 1
        assert result[0].source == "appium"  # appium > transcript

    def test_long_content_truncated_at_80(self):
        """Compound key uses only first 80 chars of content."""
        long_a = "A" * 100
        long_b = "A" * 80 + "B" * 20  # Same first 80 chars, different after
        msg_a = _msg(datetime(2024, 6, 15, 10, 30), content=long_a)
        msg_b = _msg(datetime(2024, 6, 15, 10, 30), content=long_b)

        # Same first 80 chars -> same compound key -> deduped
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 1

    def test_different_senders_not_deduped(self):
        """Same content same time but different senders are distinct."""
        msg_a = _msg(datetime(2024, 6, 15, 10, 30), sender="Alice", content="Hi")
        msg_b = _msg(datetime(2024, 6, 15, 10, 30), sender="Bob", content="Hi")
        result = deduplicate([msg_a, msg_b])
        assert len(result) == 2

    def test_compound_key_deterministic(self):
        """Compound key is deterministic for the same input."""
        msg = _msg(datetime(2024, 6, 15, 10, 30), sender="Alice", content="Test")
        key1 = _compound_key(msg)
        key2 = _compound_key(msg)
        assert key1 == key2

    def test_dedup_key_uses_message_id_when_set(self):
        """_dedup_key returns id-prefixed key when message_id is set."""
        msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            message_id="abc123",
        )
        key = _dedup_key(msg)
        assert key == "id:abc123"

    def test_dedup_key_uses_compound_when_no_id(self):
        """_dedup_key returns ck-prefixed key when message_id is None."""
        msg = _msg(datetime(2024, 6, 15, 10, 30))
        key = _dedup_key(msg)
        assert key.startswith("ck:")


# =========================================================================
# deduplicate — transcription lines
# =========================================================================


@pytest.mark.unit
class TestTranscriptionLines:
    """[Transcription] lines travel with their parent voice message."""

    def test_transcription_travels_with_parent(self):
        """Voice message with embedded transcription is kept intact."""
        voice = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="<voice>\n  [Transcription]: Hello from voice",
            source="mcp",
            message_id="v1",
            is_media=True,
            media_type="audio",
        )
        result = deduplicate([voice])
        assert len(result) == 1
        assert "[Transcription]" in result[0].content

    def test_transcription_not_stripped_on_dedup(self):
        """When deduping voice messages, transcription is preserved on the winner."""
        appium_voice = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="audio omitted",
            source="appium",
            is_media=True,
            media_type="audio",
        )
        mcp_voice = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="<voice>\n  [Transcription]: Actual transcription text",
            source="mcp",
            message_id="v1",
            is_media=True,
            media_type="audio",
        )
        # These have different content, so compound key won't match.
        # They are genuinely different representations of the same message
        # but compound key treats them as different (different content).
        # This is correct — they'll both be kept, and downstream logic
        # can reconcile. If they shared a message_id they'd dedup.
        result = deduplicate([appium_voice, mcp_voice])
        # Without shared message_id or matching compound key, both kept
        assert len(result) == 2

    def test_voice_with_same_id_keeps_transcription(self):
        """Same message_id: MCP voice with transcription wins over bare Appium."""
        appium_voice = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="audio omitted",
            source="appium",
            message_id="v1",
            is_media=True,
            media_type="audio",
        )
        mcp_voice = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="<voice>\n  [Transcription]: Transcribed text",
            source="mcp",
            message_id="v1",
            is_media=True,
            media_type="audio",
        )
        result = deduplicate([appium_voice, mcp_voice])
        assert len(result) == 1
        assert result[0].source == "mcp"
        assert "[Transcription]" in result[0].content

    def test_multiline_transcription_preserved(self):
        """Multi-line transcription content is not lost."""
        msg = _msg(
            datetime(2024, 6, 15, 10, 30),
            content="<voice>\n  [Transcription]: Line one\nLine two\nLine three",
            source="mcp",
            message_id="v1",
        )
        result = deduplicate([msg])
        assert "Line one" in result[0].content
        assert "Line two" in result[0].content
        assert "Line three" in result[0].content


# =========================================================================
# find_new_messages — incremental dedup
# =========================================================================


@pytest.mark.unit
class TestFindNewMessages:
    """Tests for incremental dedup (find_new_messages)."""

    def test_empty_new_messages(self):
        """No new messages returns empty list."""
        existing = [_msg(datetime(2024, 6, 15, 10, 30), content="Old")]
        assert find_new_messages([], existing) == []

    def test_empty_existing_tail(self):
        """No existing tail means everything is new."""
        new = [
            _msg(datetime(2024, 6, 15, 10, 30), content="A"),
            _msg(datetime(2024, 6, 15, 10, 31), content="B"),
        ]
        result = find_new_messages(new, [])
        assert len(result) == 2

    def test_both_empty(self):
        """Both empty returns empty."""
        assert find_new_messages([], []) == []

    def test_no_overlap_all_new(self):
        """When new messages don't overlap with existing, all are returned."""
        existing = [_msg(datetime(2024, 6, 15, 10, 30), content="Old")]
        new = [
            _msg(datetime(2024, 6, 15, 10, 31), content="New A"),
            _msg(datetime(2024, 6, 15, 10, 32), content="New B"),
        ]
        result = find_new_messages(new, existing)
        assert len(result) == 2

    def test_full_overlap_nothing_new(self):
        """When all new messages match existing, nothing is returned."""
        msgs = [
            _msg(datetime(2024, 6, 15, 10, 30), content="Same"),
            _msg(datetime(2024, 6, 15, 10, 31), content="Also same"),
        ]
        result = find_new_messages(msgs, msgs)
        assert len(result) == 0

    def test_partial_overlap(self):
        """Only genuinely new messages are returned."""
        existing = [
            _msg(datetime(2024, 6, 15, 10, 30), content="Old"),
            _msg(datetime(2024, 6, 15, 10, 31), content="Overlap"),
        ]
        new = [
            _msg(datetime(2024, 6, 15, 10, 31), content="Overlap"),
            _msg(datetime(2024, 6, 15, 10, 32), content="Brand new"),
        ]
        result = find_new_messages(new, existing)
        assert len(result) == 1
        assert result[0].content == "Brand new"

    def test_sorted_chronologically(self):
        """Returned new messages are sorted by timestamp."""
        existing = [_msg(datetime(2024, 6, 15, 10, 30), content="Old")]
        new = [
            _msg(datetime(2024, 6, 15, 10, 33), content="Third"),
            _msg(datetime(2024, 6, 15, 10, 31), content="First"),
            _msg(datetime(2024, 6, 15, 10, 32), content="Second"),
        ]
        result = find_new_messages(new, existing)
        assert [m.content for m in result] == ["First", "Second", "Third"]

    def test_message_id_based_overlap(self):
        """Overlap detection works via message_id."""
        existing = [
            _msg(
                datetime(2024, 6, 15, 10, 30),
                content="Existing",
                source="mcp",
                message_id="m1",
            ),
        ]
        new = [
            _msg(
                datetime(2024, 6, 15, 10, 30),
                content="Existing",
                source="mcp",
                message_id="m1",
            ),
            _msg(
                datetime(2024, 6, 15, 10, 31),
                content="New one",
                source="mcp",
                message_id="m2",
            ),
        ]
        result = find_new_messages(new, existing)
        assert len(result) == 1
        assert result[0].message_id == "m2"

    def test_compound_key_based_overlap(self):
        """Overlap detection works via compound key when no message_id."""
        existing = [
            _msg(
                datetime(2024, 6, 15, 10, 30),
                sender="Alice",
                content="Hello",
                source="transcript",
            ),
        ]
        new = [
            _msg(
                datetime(2024, 6, 15, 10, 30, 30),
                sender="Alice",
                content="Hello",
                source="mcp",
            ),
            _msg(
                datetime(2024, 6, 15, 10, 31),
                sender="Alice",
                content="New message",
                source="mcp",
            ),
        ]
        result = find_new_messages(new, existing)
        assert len(result) == 1
        assert result[0].content == "New message"

    def test_single_new_message(self):
        """Single new message that doesn't overlap is returned."""
        existing = [_msg(datetime(2024, 6, 15, 10, 30), content="Old")]
        new = [_msg(datetime(2024, 6, 15, 10, 31), content="New")]
        result = find_new_messages(new, existing)
        assert len(result) == 1
        assert result[0].content == "New"

    def test_transcription_not_lost_in_incremental(self):
        """Voice messages with transcription survive incremental dedup."""
        existing = [_msg(datetime(2024, 6, 15, 10, 29), content="Earlier")]
        new = [
            _msg(
                datetime(2024, 6, 15, 10, 30),
                content="<voice>\n  [Transcription]: Voice text",
                source="mcp",
                message_id="v1",
                is_media=True,
                media_type="audio",
            ),
        ]
        result = find_new_messages(new, existing)
        assert len(result) == 1
        assert "[Transcription]" in result[0].content
