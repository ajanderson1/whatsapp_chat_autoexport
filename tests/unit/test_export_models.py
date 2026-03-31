"""Tests for export layer data models."""

import pytest

from whatsapp_chat_autoexport.export.models import ChatMetadata


class TestChatMetadata:
    """Tests for ChatMetadata dataclass."""

    def test_all_fields_populated(self):
        """Create ChatMetadata with all fields populated."""
        chat = ChatMetadata(
            name="John Doe",
            timestamp="12:34 PM",
            message_preview="Hey, how are you?",
            is_muted=True,
            is_group=True,
            group_sender="Alice",
            has_type_indicator=True,
            photo_description="John Doe picture",
        )
        assert chat.name == "John Doe"
        assert chat.timestamp == "12:34 PM"
        assert chat.message_preview == "Hey, how are you?"
        assert chat.is_muted is True
        assert chat.is_group is True
        assert chat.group_sender == "Alice"
        assert chat.has_type_indicator is True
        assert chat.photo_description == "John Doe picture"

    def test_name_only_defaults(self):
        """Create ChatMetadata with only name — all optional fields are None/False."""
        chat = ChatMetadata(name="Jane")
        assert chat.name == "Jane"
        assert chat.timestamp is None
        assert chat.message_preview is None
        assert chat.is_muted is False
        assert chat.is_group is False
        assert chat.group_sender is None
        assert chat.has_type_indicator is False
        assert chat.photo_description is None

    def test_str_returns_name(self):
        """str(ChatMetadata) returns the name field."""
        chat = ChatMetadata(name="John")
        assert str(chat) == "John"

    def test_str_with_full_metadata(self):
        """str() still returns just the name even with all fields set."""
        chat = ChatMetadata(
            name="Group Chat",
            timestamp="Yesterday",
            message_preview="Last message",
            is_muted=True,
            is_group=True,
        )
        assert str(chat) == "Group Chat"

    def test_empty_string_name(self):
        """Empty string name is allowed (WhatsApp may have empty-named chats)."""
        chat = ChatMetadata(name="")
        assert chat.name == ""
        assert str(chat) == ""

    def test_equality(self):
        """Dataclass equality compares all fields."""
        a = ChatMetadata(name="Test", timestamp="12:00")
        b = ChatMetadata(name="Test", timestamp="12:00")
        c = ChatMetadata(name="Test", timestamp="13:00")
        assert a == b
        assert a != c

    def test_list_operations(self):
        """ChatMetadata works in lists with indexing and slicing."""
        chats = [
            ChatMetadata(name="Alice"),
            ChatMetadata(name="Bob"),
            ChatMetadata(name="Charlie"),
        ]
        assert chats[0].name == "Alice"
        assert [c.name for c in chats[1:]] == ["Bob", "Charlie"]
        assert len(chats) == 3
