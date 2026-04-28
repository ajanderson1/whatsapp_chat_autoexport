"""
Test suite for IndexBuilder.

Tests index.md companion note generation conforming to
docs/specs/transcript-format-spec.md.
"""

import re
from datetime import datetime

import pytest
import yaml

from whatsapp_chat_autoexport.output.index_builder import IndexBuilder
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


def _parse_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from markdown content."""
    assert content.startswith("---"), "Content should start with ---"
    end = content.index("---", 3)
    fm_text = content[3:end].strip()
    return yaml.safe_load(fm_text) or {}


def _extract_body(content: str) -> str:
    """Extract body text after frontmatter."""
    end = content.index("---", 3) + 3
    return content[end:].strip()


# ---------------------------------------------------------------------------
# Direct chat index.md
# ---------------------------------------------------------------------------

class TestDirectChatIndex:
    """Tests for direct chat index.md generation."""

    @pytest.fixture
    def builder(self):
        return IndexBuilder()

    @pytest.fixture
    def sample_messages(self):
        return [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:11:00", "Tim Cocking", "Hi there"),
            _msg("2026-03-25T10:00:00", "Tim Cocking",
                 "IMG.jpg", True, "image"),
            _msg("2026-03-25T10:01:00", "Tim Cocking",
                 "PTT.opus", True, "audio"),
        ]

    def test_type_is_note(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "447956173473@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["type"] == "note"

    def test_description_direct(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["description"] == "WhatsApp correspondence with Tim Cocking"

    def test_tags_direct(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert "whatsapp" in fm["tags"]
        assert "correspondence" in fm["tags"]
        assert "group_chat" not in fm["tags"]

    def test_cssclasses(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert "whatsapp-chat" in fm["cssclasses"]

    def test_chat_type_direct(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["chat_type"] == "direct"

    def test_contact_wikilink(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["contact"] == "[[Tim Cocking]]"

    def test_phone_field(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
            phone="+44 7956 173473",
        )
        fm = _parse_frontmatter(result)
        assert fm["phone"] == "+44 7956 173473"

    def test_jid_field(self, builder, sample_messages):
        jid = "447956173473@s.whatsapp.net"
        result = builder.build_index(
            sample_messages, jid, "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["jid"] == jid

    def test_message_count(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["message_count"] == 4

    def test_media_count(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["media_count"] == 2

    def test_voice_count(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["voice_count"] == 1

    def test_date_first(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        # YAML may parse as date object
        assert str(fm["date_first"]) == "2015-07-29"

    def test_date_last(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert str(fm["date_last"]) == "2026-03-25"

    def test_last_synced_present(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert "last_synced" in fm
        # Should be an ISO datetime string
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", str(fm["last_synced"]))

    def test_sources_list(self, builder, sample_messages):
        sources = [
            {"type": "appium_export", "date": "2026-03-26", "messages": 16950},
        ]
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
            sources=sources,
        )
        fm = _parse_frontmatter(result)
        assert len(fm["sources"]) == 1
        assert fm["sources"][0]["type"] == "appium_export"
        assert fm["sources"][0]["messages"] == 16950

    def test_coverage_gaps_default(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["coverage_gaps"] == 0

    def test_timezone_field(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
            timezone="Europe/London",
        )
        fm = _parse_frontmatter(result)
        assert fm["timezone"] == "Europe/London"

    def test_timezone_default(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["timezone"] == "Europe/Stockholm"

    def test_languages_field(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
            languages=["en", "sv"],
        )
        fm = _parse_frontmatter(result)
        assert fm["languages"] == ["en", "sv"]

    def test_languages_default(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert fm["languages"] == ["en"]

    def test_summary_field(self, builder, sample_messages):
        summary_text = "Close personal friendship spanning 11 years."
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
            summary=summary_text,
        )
        assert "Close personal friendship" in result

    def test_summary_empty_default(self, builder, sample_messages):
        result = builder.build_index(
            sample_messages, "jid@s.whatsapp.net", "Tim Cocking",
        )
        fm = _parse_frontmatter(result)
        assert "summary" in fm


# ---------------------------------------------------------------------------
# Group chat index.md
# ---------------------------------------------------------------------------

class TestGroupChatIndex:
    """Tests for group chat index.md generation."""

    @pytest.fixture
    def builder(self):
        return IndexBuilder()

    @pytest.fixture
    def group_messages(self):
        return [
            _msg("2016-01-05T10:00:00", "Tim Cocking", "Hello group"),
            _msg("2016-01-05T10:01:00", "Peter Cocking", "Hi"),
            _msg("2026-03-25T10:00:00", "AJ Anderson", "Latest"),
        ]

    def test_chat_type_group(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "491749580928-1452027796@g.us", "Brothers",
            chat_type="group",
            participants=["[[Tim Cocking]]", "[[Peter Cocking]]"],
        )
        fm = _parse_frontmatter(result)
        assert fm["chat_type"] == "group"

    def test_description_group(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
        )
        fm = _parse_frontmatter(result)
        assert "group chat" in fm["description"].lower()
        assert "Brothers" in fm["description"]

    def test_group_chat_tag(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
        )
        fm = _parse_frontmatter(result)
        assert "group_chat" in fm["tags"]

    def test_chat_name_field(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
        )
        fm = _parse_frontmatter(result)
        assert fm["chat_name"] == "Brothers"

    def test_participants_list(self, builder, group_messages):
        participants = ["[[Tim Cocking]]", "[[Peter Cocking]]", "+49 174 9580928"]
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
            participants=participants,
        )
        fm = _parse_frontmatter(result)
        assert fm["participants"] == participants

    def test_no_contact_field_for_group(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
        )
        fm = _parse_frontmatter(result)
        assert "contact" not in fm

    def test_no_phone_field_for_group(self, builder, group_messages):
        result = builder.build_index(
            group_messages, "jid@g.us", "Brothers",
            chat_type="group",
        )
        fm = _parse_frontmatter(result)
        assert "phone" not in fm


# ---------------------------------------------------------------------------
# Body section
# ---------------------------------------------------------------------------

class TestIndexBody:
    """Tests for the body section of index.md."""

    @pytest.fixture
    def builder(self):
        return IndexBuilder()

    def test_body_has_blockquote(self, builder):
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(msgs, "jid@s.whatsapp.net", "Tim Cocking")
        body = _extract_body(result)

        assert body.startswith(">")

    def test_body_has_wikilink_direct(self, builder):
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(msgs, "jid@s.whatsapp.net", "Tim Cocking")
        body = _extract_body(result)

        assert "[[Tim Cocking]]" in body

    def test_body_has_period_line(self, builder):
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2026-03-25T10:00:00", "Tim Cocking", "Latest"),
        ]
        result = builder.build_index(msgs, "jid@s.whatsapp.net", "Tim Cocking")
        body = _extract_body(result)

        assert "Period: 2015-07-29 to 2026-03-25" in body
        assert "2 messages" in body

    def test_body_has_transcript_link(self, builder):
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(msgs, "jid@s.whatsapp.net", "Tim Cocking")
        body = _extract_body(result)

        assert "[[People/Correspondence/Whatsapp/Tim Cocking/transcript|Full Transcript]]" in body

    def test_body_group_chat(self, builder):
        msgs = [_msg("2016-01-05T10:00:00", "Tim Cocking", "Hello group")]
        result = builder.build_index(
            msgs, "jid@g.us", "Brothers",
            chat_type="group",
        )
        body = _extract_body(result)

        assert "group chat" in body.lower()
        assert "Brothers" in body

    def test_body_message_count_formatted(self, builder):
        """Large message counts should use comma separator."""
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")] * 1500
        result = builder.build_index(msgs, "jid@s.whatsapp.net", "Tim Cocking")
        body = _extract_body(result)

        assert "1,500 messages" in body


# ---------------------------------------------------------------------------
# Empty messages
# ---------------------------------------------------------------------------

class TestEmptyMessages:
    """Tests for edge case with no messages."""

    def test_empty_messages_produces_valid_yaml(self):
        builder = IndexBuilder()
        result = builder.build_index(
            [], "jid@s.whatsapp.net", "Nobody",
        )
        fm = _parse_frontmatter(result)

        assert fm["message_count"] == 0
        assert fm["media_count"] == 0
        assert fm["voice_count"] == 0

    def test_empty_messages_date_fields(self):
        builder = IndexBuilder()
        result = builder.build_index(
            [], "jid@s.whatsapp.net", "Nobody",
        )
        fm = _parse_frontmatter(result)

        assert fm.get("date_first") is None
        assert fm.get("date_last") is None


# ---------------------------------------------------------------------------
# update_index
# ---------------------------------------------------------------------------

class TestUpdateIndex:
    """Tests for updating an existing index.md."""

    @pytest.fixture
    def builder(self):
        return IndexBuilder()

    @pytest.fixture
    def existing_index(self, builder):
        """Build an initial index to update."""
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2015-07-29T00:06:00", "Tim Cocking", "Hi"),
        ]
        return builder.build_index(
            msgs, "447956173473@s.whatsapp.net", "Tim Cocking",
            sources=[{"type": "appium_export", "date": "2026-03-01", "messages": 2}],
        )

    def test_update_increments_message_count(self, builder, existing_index):
        new_msgs = [
            _msg("2026-03-26T10:00:00", "Tim Cocking", "New message 1"),
            _msg("2026-03-26T10:01:00", "AJ Anderson", "New message 2"),
            _msg("2026-03-26T10:02:00", "Tim Cocking", "New message 3"),
        ]
        result = builder.update_index(existing_index, new_msgs)
        fm = _parse_frontmatter(result)

        assert fm["message_count"] == 5  # 2 + 3

    def test_update_increments_media_count(self, builder, existing_index):
        new_msgs = [
            _msg("2026-03-26T10:00:00", "Tim Cocking",
                 "IMG.jpg", True, "image"),
        ]
        result = builder.update_index(existing_index, new_msgs)
        fm = _parse_frontmatter(result)

        assert fm["media_count"] == 1  # 0 + 1

    def test_update_extends_date_range(self, builder, existing_index):
        new_msgs = [
            _msg("2026-03-26T10:00:00", "Tim Cocking", "Latest"),
        ]
        result = builder.update_index(existing_index, new_msgs)
        fm = _parse_frontmatter(result)

        # date_first should remain 2015-07-29 (from existing)
        assert str(fm["date_first"]) == "2015-07-29"
        # date_last should extend to 2026-03-26
        assert str(fm["date_last"]) == "2026-03-26"

    def test_update_appends_source(self, builder, existing_index):
        new_msgs = [
            _msg("2026-03-26T10:00:00", "Tim Cocking", "New"),
        ]
        source = {"type": "mcp_bridge", "date": "2026-03-26", "messages": 1}
        result = builder.update_index(existing_index, new_msgs, source_entry=source)
        fm = _parse_frontmatter(result)

        assert len(fm["sources"]) == 2
        assert fm["sources"][-1]["type"] == "mcp_bridge"

    def test_update_refreshes_last_synced(self, builder, existing_index):
        new_msgs = [
            _msg("2026-03-26T10:00:00", "Tim Cocking", "New"),
        ]
        result = builder.update_index(existing_index, new_msgs)
        fm = _parse_frontmatter(result)

        # last_synced should be recent (within the test run)
        synced = str(fm["last_synced"])
        today = datetime.now().strftime("%Y-%m-%d")
        assert synced.startswith(today)

    def test_update_preserves_body(self, builder, existing_index):
        """Update should preserve the body section."""
        new_msgs = [_msg("2026-03-26T10:00:00", "Tim Cocking", "New")]
        result = builder.update_index(existing_index, new_msgs)

        body = _extract_body(result)
        assert "Tim Cocking" in body
        assert "Full Transcript" in body

    def test_update_no_source_entry(self, builder, existing_index):
        """Update without a new source entry should not modify sources list."""
        new_msgs = [_msg("2026-03-26T10:00:00", "Tim Cocking", "New")]
        result = builder.update_index(existing_index, new_msgs)
        fm = _parse_frontmatter(result)

        assert len(fm["sources"]) == 1  # original source only

    def test_update_invalid_frontmatter(self, builder):
        """If existing content has no frontmatter, return unchanged."""
        content = "Just some text without frontmatter."
        new_msgs = [_msg("2026-03-26T10:00:00", "Tim Cocking", "New")]
        result = builder.update_index(content, new_msgs)

        assert result == content


# ---------------------------------------------------------------------------
# Spec examples
# ---------------------------------------------------------------------------

class TestSpecExamples:
    """Test against examples from transcript-format-spec.md."""

    def test_spec_direct_chat_fields(self):
        """Verify all fields from the spec's direct chat example are present."""
        builder = IndexBuilder()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2026-03-25T10:00:00", "Tim Cocking",
                 "IMG.jpg", True, "image"),
        ]
        sources = [
            {"type": "appium_export", "date": "2026-03-26", "messages": 16950},
        ]
        result = builder.build_index(
            msgs, "447956173473@s.whatsapp.net", "Tim Cocking",
            chat_type="direct",
            sources=sources,
            phone="+44 7956 173473",
            timezone="Europe/Stockholm",
            languages=["en"],
            summary="Close personal friendship spanning 11 years.",
        )
        fm = _parse_frontmatter(result)

        # All required fields from the spec
        assert fm["type"] == "note"
        assert "whatsapp" in fm["tags"]
        assert "correspondence" in fm["tags"]
        assert "whatsapp-chat" in fm["cssclasses"]
        assert fm["chat_type"] == "direct"
        assert fm["contact"] == "[[Tim Cocking]]"
        assert fm["phone"] == "+44 7956 173473"
        assert fm["jid"] == "447956173473@s.whatsapp.net"
        assert fm["message_count"] == 2
        assert fm["media_count"] == 1
        assert fm["voice_count"] == 0
        assert "last_synced" in fm
        assert fm["sources"][0]["type"] == "appium_export"
        assert fm["coverage_gaps"] == 0
        assert fm["timezone"] == "Europe/Stockholm"
        assert fm["languages"] == ["en"]

    def test_spec_group_chat_fields(self):
        """Verify all fields from the spec's group chat example are present."""
        builder = IndexBuilder()
        msgs = [
            _msg("2016-01-05T10:00:00", "Tim Cocking", "Hello group"),
            _msg("2016-01-05T10:01:00", "Peter Cocking", "Hi"),
        ]
        participants = [
            "[[Tim Cocking]]",
            "[[Peter Cocking]]",
            "[[Paul Ashley Cocking]]",
            "+49 174 9580928",
        ]
        result = builder.build_index(
            msgs, "491749580928-1452027796@g.us", "Brothers",
            chat_type="group",
            participants=participants,
        )
        fm = _parse_frontmatter(result)

        assert fm["type"] == "note"
        assert "group_chat" in fm["tags"]
        assert fm["chat_type"] == "group"
        assert fm["chat_name"] == "Brothers"
        assert fm["participants"] == participants
        assert fm["jid"] == "491749580928-1452027796@g.us"
        assert "contact" not in fm

    def test_spec_body_format(self):
        """Match the body example from the spec."""
        builder = IndexBuilder()
        msgs = [
            _msg("2015-07-29T00:05:00", "AJ Anderson", "Hello"),
            _msg("2026-03-25T10:00:00", "Tim Cocking", "Latest"),
        ]
        result = builder.build_index(
            msgs, "jid@s.whatsapp.net", "Tim Cocking",
        )
        body = _extract_body(result)

        assert "> WhatsApp correspondence with [[Tim Cocking]]" in body
        assert "> Period: 2015-07-29 to 2026-03-25 | 2 messages" in body
        assert "[[People/Correspondence/Whatsapp/Tim Cocking/transcript|Full Transcript]]" in body


# ---------------------------------------------------------------------------
# YAML validity
# ---------------------------------------------------------------------------

class TestYamlValidity:
    """Tests that generated frontmatter is valid YAML."""

    def test_direct_chat_valid_yaml(self):
        builder = IndexBuilder()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(
            msgs, "jid@s.whatsapp.net", "Tim Cocking",
            phone="+44 7956 173473",
            sources=[{"type": "appium_export", "date": "2026-03-26", "messages": 100}],
        )

        # Should parse without error
        fm = _parse_frontmatter(result)
        assert isinstance(fm, dict)

    def test_group_chat_valid_yaml(self):
        builder = IndexBuilder()
        msgs = [_msg("2016-01-05T10:00:00", "Tim Cocking", "Hello")]
        result = builder.build_index(
            msgs, "jid@g.us", "Brothers",
            chat_type="group",
            participants=["[[Tim Cocking]]", "+49 174 9580928"],
        )

        fm = _parse_frontmatter(result)
        assert isinstance(fm, dict)

    def test_special_characters_in_name(self):
        """Contact names with special YAML chars should be properly escaped."""
        builder = IndexBuilder()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(
            msgs, "jid@s.whatsapp.net", "O'Brien: The \"Great\"",
        )

        # Should parse without error
        fm = _parse_frontmatter(result)
        assert isinstance(fm, dict)

    def test_empty_sources_valid_yaml(self):
        builder = IndexBuilder()
        msgs = [_msg("2015-07-29T00:05:00", "AJ Anderson", "Hello")]
        result = builder.build_index(
            msgs, "jid@s.whatsapp.net", "Tim Cocking",
            sources=[],
        )

        fm = _parse_frontmatter(result)
        assert isinstance(fm, dict)
