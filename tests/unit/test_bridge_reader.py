"""
Test suite for the MCP bridge reader.

Tests BridgeReader against a temporary SQLite database created with the
same schema as the Go-based WhatsApp MCP bridge.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.mcp.bridge_reader import (
    BridgeReader,
    BridgeChat,
    BridgeMessage,
    BridgeReaderError,
    DatabaseNotFoundError,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def bridge_db(tmp_path):
    """Create a temporary SQLite database with the MCP bridge schema."""
    db_path = tmp_path / "store" / "messages.db"
    db_path.parent.mkdir(parents=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chats (
            jid TEXT PRIMARY KEY,
            name TEXT,
            last_message_time TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT,
            chat_jid TEXT,
            sender TEXT,
            content TEXT,
            timestamp TIMESTAMP,
            is_from_me BOOLEAN,
            media_type TEXT,
            filename TEXT,
            url TEXT,
            media_key BLOB,
            file_sha256 BLOB,
            file_enc_sha256 BLOB,
            file_length INTEGER,
            PRIMARY KEY (id, chat_jid),
            FOREIGN KEY (chat_jid) REFERENCES chats(jid)
        );
        """
    )
    conn.close()
    return db_path


@pytest.fixture
def populated_db(bridge_db):
    """Populate the bridge DB with sample data."""
    conn = sqlite3.connect(str(bridge_db))

    # Insert chats
    conn.execute(
        "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
        ("447837370336@s.whatsapp.net", "Alice", "2026-03-25 10:30:00"),
    )
    conn.execute(
        "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
        ("group123@g.us", "Family Group", "2026-03-25 11:00:00"),
    )

    # Insert messages for Alice
    conn.execute(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("msg001", "447837370336@s.whatsapp.net", "447837370336", "Hello!", "2026-03-25 10:00:00", 0, None, None),
    )
    conn.execute(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("msg002", "447837370336@s.whatsapp.net", "", "Hi there", "2026-03-25 10:01:00", 1, None, None),
    )
    conn.execute(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("msg003", "447837370336@s.whatsapp.net", "447837370336", "", "2026-03-25 10:02:00", 0, "image", "photo.jpg"),
    )
    conn.execute(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("msg004", "447837370336@s.whatsapp.net", "447837370336@s.whatsapp.net", "JID sender", "2026-03-25 10:30:00", 0, None, None),
    )

    # Insert messages for group
    conn.execute(
        "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("grp001", "group123@g.us", "447837370336", "Group msg", "2026-03-25 11:00:00", 0, None, None),
    )

    conn.commit()
    conn.close()
    return bridge_db


def make_reader(db_path):
    """Helper to create a BridgeReader with the test DB path."""
    return BridgeReader(db_path=db_path, store_dir=db_path.parent)


# =========================================================================
# Database not found
# =========================================================================


@pytest.mark.unit
class TestBridgeReaderNotFound:
    """Tests for when the database does not exist."""

    def test_db_not_found_raises(self, tmp_path):
        """Raises DatabaseNotFoundError when DB file is missing."""
        reader = BridgeReader(db_path=tmp_path / "nonexistent.db")
        with pytest.raises(DatabaseNotFoundError):
            reader.list_chats()

    def test_db_not_found_on_get_messages(self, tmp_path):
        """Raises DatabaseNotFoundError on get_messages too."""
        reader = BridgeReader(db_path=tmp_path / "nonexistent.db")
        with pytest.raises(DatabaseNotFoundError):
            reader.get_messages("some_jid")


# =========================================================================
# list_chats
# =========================================================================


@pytest.mark.unit
class TestListChats:
    """Tests for BridgeReader.list_chats()."""

    def test_empty_database(self, bridge_db):
        """Empty database returns empty list."""
        reader = make_reader(bridge_db)
        assert reader.list_chats() == []

    def test_returns_all_chats(self, populated_db):
        """Returns all chats from the database."""
        reader = make_reader(populated_db)
        chats = reader.list_chats()
        assert len(chats) == 2

    def test_chat_fields(self, populated_db):
        """Chat objects have correct fields."""
        reader = make_reader(populated_db)
        chats = {c.jid: c for c in reader.list_chats()}

        alice = chats["447837370336@s.whatsapp.net"]
        assert alice.name == "Alice"
        assert alice.last_message_time == datetime(2026, 3, 25, 10, 30, 0)

        group = chats["group123@g.us"]
        assert group.name == "Family Group"

    def test_sorted_by_last_message_time_desc(self, populated_db):
        """Chats are sorted by last_message_time descending."""
        reader = make_reader(populated_db)
        chats = reader.list_chats()
        # Group (11:00) should come before Alice (10:30)
        assert chats[0].jid == "group123@g.us"
        assert chats[1].jid == "447837370336@s.whatsapp.net"


# =========================================================================
# get_messages
# =========================================================================


@pytest.mark.unit
class TestGetMessages:
    """Tests for BridgeReader.get_messages()."""

    def test_empty_chat(self, bridge_db):
        """Non-existent chat JID returns empty list."""
        reader = make_reader(bridge_db)
        assert reader.get_messages("nonexistent@s.whatsapp.net") == []

    def test_returns_all_messages_for_chat(self, populated_db):
        """Returns all messages for a given chat JID."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net")
        assert len(msgs) == 4

    def test_messages_chronological_order(self, populated_db):
        """Messages are returned oldest-first."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net")
        timestamps = [m.timestamp for m in msgs]
        assert timestamps == sorted(timestamps)

    def test_after_filter(self, populated_db):
        """Only messages after the cutoff are returned."""
        reader = make_reader(populated_db)
        cutoff = datetime(2026, 3, 25, 10, 1, 0)
        msgs = reader.get_messages("447837370336@s.whatsapp.net", after=cutoff)
        assert len(msgs) == 2
        assert all(m.timestamp > cutoff for m in msgs)

    def test_limit(self, populated_db):
        """Respects the limit parameter."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net", limit=2)
        assert len(msgs) == 2

    def test_after_and_limit_combined(self, populated_db):
        """Both after and limit work together."""
        reader = make_reader(populated_db)
        cutoff = datetime(2026, 3, 25, 10, 0, 0)
        msgs = reader.get_messages(
            "447837370336@s.whatsapp.net", after=cutoff, limit=1
        )
        assert len(msgs) == 1

    def test_message_fields(self, populated_db):
        """Message objects have correctly populated fields."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net")

        first = msgs[0]
        assert first.id == "msg001"
        assert first.chat_jid == "447837370336@s.whatsapp.net"
        assert first.sender == "447837370336"
        assert first.content == "Hello!"
        assert first.is_from_me is False
        assert first.media_type is None

    def test_media_message_fields(self, populated_db):
        """Media messages have media_type and filename set."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net")

        media_msg = msgs[2]  # msg003
        assert media_msg.media_type == "image"
        assert media_msg.filename == "photo.jpg"

    def test_is_from_me_flag(self, populated_db):
        """is_from_me is correctly parsed."""
        reader = make_reader(populated_db)
        msgs = reader.get_messages("447837370336@s.whatsapp.net")

        assert msgs[0].is_from_me is False
        assert msgs[1].is_from_me is True


# =========================================================================
# get_sender_name
# =========================================================================


@pytest.mark.unit
class TestGetSenderName:
    """Tests for BridgeReader.get_sender_name()."""

    def test_exact_jid_match(self, populated_db):
        """Full JID resolves to display name."""
        reader = make_reader(populated_db)
        assert reader.get_sender_name("447837370336@s.whatsapp.net") == "Alice"

    def test_phone_number_like_match(self, populated_db):
        """Bare phone number resolves via LIKE match."""
        reader = make_reader(populated_db)
        assert reader.get_sender_name("447837370336") == "Alice"

    def test_unknown_sender_fallback(self, populated_db):
        """Unknown sender falls back to raw value."""
        reader = make_reader(populated_db)
        assert reader.get_sender_name("999999999") == "999999999"

    def test_caching(self, populated_db):
        """Repeated lookups use the cache."""
        reader = make_reader(populated_db)
        name1 = reader.get_sender_name("447837370336")
        name2 = reader.get_sender_name("447837370336")
        assert name1 == name2 == "Alice"
        # Verify it's in the cache
        assert "447837370336" in reader._name_cache

    def test_db_not_found_graceful(self, tmp_path):
        """Returns raw value when DB is not found (graceful degradation)."""
        reader = BridgeReader(db_path=tmp_path / "nonexistent.db")
        assert reader.get_sender_name("447837370336") == "447837370336"


# =========================================================================
# download_media
# =========================================================================


@pytest.mark.unit
class TestDownloadMedia:
    """Tests for BridgeReader.download_media()."""

    def test_media_file_exists(self, populated_db):
        """Returns path when media file exists on disk."""
        reader = make_reader(populated_db)
        store_dir = populated_db.parent

        # Create the expected media file
        sanitised = "447837370336_s_whatsapp_net"
        media_dir = store_dir / sanitised
        media_dir.mkdir(parents=True)
        media_file = media_dir / "photo.jpg"
        media_file.write_bytes(b"fake image data")

        result = reader.download_media("msg003", "447837370336@s.whatsapp.net")
        assert result is not None
        assert result.name == "photo.jpg"

    def test_media_file_not_on_disk(self, populated_db):
        """Returns None when media file doesn't exist on disk."""
        reader = make_reader(populated_db)
        result = reader.download_media("msg003", "447837370336@s.whatsapp.net")
        assert result is None

    def test_no_filename_in_db(self, populated_db):
        """Returns None when message has no filename."""
        reader = make_reader(populated_db)
        result = reader.download_media("msg001", "447837370336@s.whatsapp.net")
        assert result is None

    def test_nonexistent_message(self, populated_db):
        """Returns None for a message ID that doesn't exist."""
        reader = make_reader(populated_db)
        result = reader.download_media("nonexistent", "447837370336@s.whatsapp.net")
        assert result is None

    def test_db_not_found_graceful(self, tmp_path):
        """Returns None when DB is not found."""
        reader = BridgeReader(db_path=tmp_path / "nonexistent.db")
        result = reader.download_media("msg001", "some@jid")
        assert result is None

    def test_flat_store_fallback(self, populated_db):
        """Falls back to flat store directory when JID subdir doesn't exist."""
        reader = make_reader(populated_db)
        store_dir = populated_db.parent

        # Create the file in the flat store directory (no JID subdir)
        media_file = store_dir / "photo.jpg"
        media_file.write_bytes(b"flat media data")

        result = reader.download_media("msg003", "447837370336@s.whatsapp.net")
        assert result is not None
        assert result.name == "photo.jpg"
