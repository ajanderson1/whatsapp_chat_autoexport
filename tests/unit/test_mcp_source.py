"""
Test suite for MCPSource — the MCP bridge MessageSource implementation.

Uses mock BridgeReader instances to avoid needing a real SQLite database.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whatsapp_chat_autoexport.mcp.bridge_reader import (
    BridgeChat,
    BridgeMessage,
    BridgeReaderError,
    DatabaseNotFoundError,
)
from whatsapp_chat_autoexport.sources.mcp_source import MCPSource
from whatsapp_chat_autoexport.sources.base import ChatInfo
from whatsapp_chat_autoexport.processing.transcript_parser import Message
from whatsapp_chat_autoexport.utils.logger import Logger


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_reader():
    """Create a mock BridgeReader with sample data."""
    reader = MagicMock()

    reader.list_chats.return_value = [
        BridgeChat(
            jid="447837370336@s.whatsapp.net",
            name="Alice",
            last_message_time=datetime(2026, 3, 25, 10, 30, 0),
        ),
        BridgeChat(
            jid="group123@g.us",
            name="Family Group",
            last_message_time=datetime(2026, 3, 25, 11, 0, 0),
        ),
    ]

    def get_messages_side_effect(jid, after=None, limit=None):
        all_msgs = {
            "447837370336@s.whatsapp.net": [
                BridgeMessage(
                    id="msg001",
                    chat_jid="447837370336@s.whatsapp.net",
                    sender="447837370336",
                    content="Hello!",
                    timestamp=datetime(2026, 3, 25, 10, 0, 0),
                    is_from_me=False,
                ),
                BridgeMessage(
                    id="msg002",
                    chat_jid="447837370336@s.whatsapp.net",
                    sender="",
                    content="Hi there",
                    timestamp=datetime(2026, 3, 25, 10, 1, 0),
                    is_from_me=True,
                ),
                BridgeMessage(
                    id="msg003",
                    chat_jid="447837370336@s.whatsapp.net",
                    sender="447837370336",
                    content="",
                    timestamp=datetime(2026, 3, 25, 10, 2, 0),
                    is_from_me=False,
                    media_type="image",
                    filename="photo.jpg",
                ),
                BridgeMessage(
                    id="msg004",
                    chat_jid="447837370336@s.whatsapp.net",
                    sender="447837370336",
                    content="",
                    timestamp=datetime(2026, 3, 25, 10, 3, 0),
                    is_from_me=False,
                    media_type="audio",
                    filename="voice.ogg",
                ),
            ],
        }
        msgs = all_msgs.get(jid, [])
        if after is not None:
            msgs = [m for m in msgs if m.timestamp > after]
        if limit is not None:
            msgs = msgs[:limit]
        return msgs

    reader.get_messages.side_effect = get_messages_side_effect
    reader.get_sender_name.return_value = "Alice"

    return reader


@pytest.fixture
def mcp_source(mock_reader):
    """Create an MCPSource with the mock reader."""
    return MCPSource(
        reader=mock_reader,
        user_display_name="Me",
        logger=Logger(log_file_enabled=False),
    )


# =========================================================================
# get_chats
# =========================================================================


@pytest.mark.unit
class TestMCPSourceGetChats:
    """Tests for MCPSource.get_chats()."""

    def test_returns_chat_info_list(self, mcp_source):
        """get_chats returns ChatInfo objects."""
        chats = mcp_source.get_chats()
        assert len(chats) == 2
        assert all(isinstance(c, ChatInfo) for c in chats)

    def test_chat_info_fields(self, mcp_source):
        """ChatInfo objects have correct fields."""
        chats = {c.jid: c for c in mcp_source.get_chats()}
        alice = chats["447837370336@s.whatsapp.net"]
        assert alice.name == "Alice"
        assert alice.last_message_time == datetime(2026, 3, 25, 10, 30, 0)

    def test_chat_with_no_name_uses_jid(self, mock_reader):
        """Chat with None name falls back to JID."""
        mock_reader.list_chats.return_value = [
            BridgeChat(jid="unknown@jid", name=None, last_message_time=None),
        ]
        source = MCPSource(reader=mock_reader, logger=Logger(log_file_enabled=False))
        chats = source.get_chats()
        assert chats[0].name == "unknown@jid"

    def test_bridge_error_returns_empty(self, mock_reader):
        """Bridge errors produce empty list, not exception."""
        mock_reader.list_chats.side_effect = DatabaseNotFoundError("no db")
        source = MCPSource(reader=mock_reader, logger=Logger(log_file_enabled=False))
        assert source.get_chats() == []


# =========================================================================
# get_messages
# =========================================================================


@pytest.mark.unit
class TestMCPSourceGetMessages:
    """Tests for MCPSource.get_messages()."""

    def test_returns_message_objects(self, mcp_source):
        """get_messages returns Message objects."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert len(msgs) == 4
        assert all(isinstance(m, Message) for m in msgs)

    def test_source_tag(self, mcp_source):
        """All messages are tagged source='mcp'."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert all(m.source == "mcp" for m in msgs)

    def test_message_id_populated(self, mcp_source):
        """message_id is populated from WhatsApp message IDs."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert msgs[0].message_id == "msg001"
        assert msgs[1].message_id == "msg002"

    def test_sender_resolution(self, mcp_source):
        """Non-me senders are resolved via BridgeReader."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert msgs[0].sender == "Alice"  # resolved from "447837370336"

    def test_is_from_me_uses_display_name(self, mcp_source):
        """is_from_me messages use the configured user display name."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert msgs[1].sender == "Me"

    def test_media_message_detection(self, mcp_source):
        """Media messages have is_media=True and correct media_type."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        photo = msgs[2]
        assert photo.is_media is True
        assert photo.media_type == "image"

    def test_media_content_tag(self, mcp_source):
        """Media messages with no text content get typed media tags."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        photo = msgs[2]
        assert photo.content == "<image>"

        audio = msgs[3]
        assert audio.content == "<audio>"

    def test_text_message_content(self, mcp_source):
        """Text messages have their content preserved."""
        msgs = mcp_source.get_messages("447837370336@s.whatsapp.net")
        assert msgs[0].content == "Hello!"

    def test_after_filter_passthrough(self, mcp_source, mock_reader):
        """after parameter is passed through to BridgeReader."""
        cutoff = datetime(2026, 3, 25, 10, 1, 0)
        msgs = mcp_source.get_messages(
            "447837370336@s.whatsapp.net", after=cutoff
        )
        assert len(msgs) == 2

    def test_limit_passthrough(self, mcp_source, mock_reader):
        """limit parameter is passed through to BridgeReader."""
        msgs = mcp_source.get_messages(
            "447837370336@s.whatsapp.net", limit=1
        )
        assert len(msgs) == 1

    def test_empty_chat(self, mcp_source):
        """Non-existent chat returns empty list."""
        msgs = mcp_source.get_messages("nonexistent@jid")
        assert msgs == []

    def test_bridge_error_returns_empty(self, mock_reader):
        """Bridge errors produce empty list, not exception."""
        mock_reader.get_messages.side_effect = BridgeReaderError("db error")
        source = MCPSource(reader=mock_reader, logger=Logger(log_file_enabled=False))
        assert source.get_messages("any@jid") == []


# =========================================================================
# get_media
# =========================================================================


@pytest.mark.unit
class TestMCPSourceGetMedia:
    """Tests for MCPSource.get_media()."""

    def test_get_media_delegates_to_reader(self, mcp_source, mock_reader):
        """get_media queries for chat_jid and delegates to reader."""
        # Set up mock connection for chat_jid lookup
        mock_conn = MagicMock()
        mock_row = {"chat_jid": "alice@jid"}
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = mock_row
        mock_conn.execute.return_value = mock_cursor
        mock_reader._connect.return_value = mock_conn
        mock_reader.download_media.return_value = Path("/fake/path.jpg")

        result = mcp_source.get_media("msg001")
        assert result == Path("/fake/path.jpg")
        mock_reader.download_media.assert_called_once_with("msg001", "alice@jid")

    def test_get_media_returns_none_for_unknown(self, mcp_source, mock_reader):
        """Returns None when message_id not found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor
        mock_reader._connect.return_value = mock_conn

        result = mcp_source.get_media("nonexistent")
        assert result is None


# =========================================================================
# Media type normalisation
# =========================================================================


@pytest.mark.unit
class TestMediaTypeNormalisation:
    """Tests for MCPSource._normalise_media_type()."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("image", "image"),
            ("audio", "audio"),
            ("video", "video"),
            ("document", "document"),
            ("sticker", "sticker"),
            ("image/jpeg", "image"),
            ("audio/ogg", "audio"),
            ("video/mp4", "video"),
            ("application/pdf", "document"),
            ("IMAGE", "image"),
            (None, None),
            ("", None),
        ],
    )
    def test_normalise(self, raw, expected):
        """Media types are normalised correctly."""
        assert MCPSource._normalise_media_type(raw) == expected
