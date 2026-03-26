"""
Integration tests for the ``whatsapp-rebuild`` command.

Each test creates a temporary SQLite database with the MCP bridge schema,
a temporary output directory, and exercises the rebuild flow
programmatically via ``run_rebuild``. No subprocesses are spawned.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.cli.commands.rebuild import run_rebuild
from whatsapp_chat_autoexport.mcp.state import MCPState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BRIDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    last_message_time TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_jid TEXT,
    sender TEXT,
    content TEXT,
    timestamp TEXT,
    is_from_me INTEGER DEFAULT 0,
    media_type TEXT,
    filename TEXT
);
"""

_NOW = datetime(2026, 3, 26, 14, 0, 0)
_YESTERDAY = _NOW - timedelta(days=1)
_TWO_DAYS_AGO = _NOW - timedelta(days=2)


def _ts(dt: datetime) -> str:
    """Format datetime the way the bridge stores it."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _create_bridge_db(db_path: Path, chats=None, messages=None):
    """Create a minimal MCP bridge SQLite database."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(BRIDGE_SCHEMA)

    if chats:
        conn.executemany(
            "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
            chats,
        )

    if messages:
        conn.executemany(
            "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            messages,
        )

    conn.commit()
    conn.close()


@pytest.fixture
def bridge_db(tmp_path):
    """Create a bridge DB with one chat and sample messages."""
    db_path = tmp_path / "messages.db"
    chats = [
        ("alice@s.whatsapp.net", "Alice Smith", _ts(_NOW)),
    ]
    messages = [
        ("msg_a1", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
         "Hello!", _ts(_TWO_DAYS_AGO), 0, None, None),
        ("msg_a2", "alice@s.whatsapp.net", "",
         "Hi Alice!", _ts(_TWO_DAYS_AGO + timedelta(minutes=1)), 1, None, None),
        ("msg_a3", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
         "How are you?", _ts(_YESTERDAY), 0, None, None),
        ("msg_a4", "alice@s.whatsapp.net", "",
         "I'm good!", _ts(_YESTERDAY + timedelta(minutes=5)), 1, None, None),
        ("msg_a5", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
         "See you later!", _ts(_NOW), 0, None, None),
    ]
    _create_bridge_db(db_path, chats=chats, messages=messages)
    return db_path


@pytest.fixture
def output_dir(tmp_path):
    """Create the vault output directory."""
    out = tmp_path / "vault_output"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRebuildFull:
    """Test full rebuild from MCP bridge."""

    def test_rebuild_creates_files(self, bridge_db, output_dir):
        """Rebuild should create transcript.md + index.md."""
        summary = run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        assert summary["success"] is True
        assert summary["chat_name"] == "Alice Smith"
        assert summary["chat_jid"] == "alice@s.whatsapp.net"
        assert summary["message_count"] == 5

        alice_dir = output_dir / "Alice Smith"
        assert (alice_dir / "transcript.md").exists()
        assert (alice_dir / "index.md").exists()

    def test_rebuild_transcript_format(self, bridge_db, output_dir):
        """Rebuilt transcript should be in v2 format with all messages."""
        run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        content = (output_dir / "Alice Smith" / "transcript.md").read_text()
        assert content.startswith("---\n")
        assert "cssclasses:" in content
        assert "Hello!" in content
        assert "See you later!" in content

    def test_rebuild_index_format(self, bridge_db, output_dir):
        """Rebuilt index.md should have mcp_rebuild source."""
        run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        content = (output_dir / "Alice Smith" / "index.md").read_text()
        assert "mcp_rebuild" in content
        assert "Alice Smith" in content

    def test_rebuild_by_jid(self, bridge_db, output_dir):
        """Should resolve by exact JID match."""
        summary = run_rebuild(
            chat_identifier="alice@s.whatsapp.net",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        assert summary["success"] is True
        assert summary["chat_jid"] == "alice@s.whatsapp.net"


class TestRebuildReplacesExisting:
    """Test that rebuild replaces existing files."""

    def test_rebuild_replaces_transcript(self, bridge_db, output_dir):
        """Rebuild should overwrite an existing transcript.md."""
        # Pre-populate with a dummy transcript
        alice_dir = output_dir / "Alice Smith"
        alice_dir.mkdir(parents=True)
        (alice_dir / "transcript.md").write_text("old content", encoding="utf-8")

        summary = run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        assert summary["success"] is True
        content = (alice_dir / "transcript.md").read_text()
        assert "old content" not in content
        assert "Hello!" in content

    def test_rebuild_replaces_index(self, bridge_db, output_dir):
        """Rebuild should overwrite an existing index.md."""
        alice_dir = output_dir / "Alice Smith"
        alice_dir.mkdir(parents=True)
        (alice_dir / "index.md").write_text("old index", encoding="utf-8")

        run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        content = (alice_dir / "index.md").read_text()
        assert "old index" not in content
        assert "mcp_rebuild" in content


class TestRebuildResetsWatermark:
    """Test that rebuild resets the watermark in state."""

    def test_watermark_reset(self, bridge_db, output_dir):
        """Watermark should be set to the latest message timestamp."""
        state_file = output_dir / ".sync-state.json"

        # Pre-populate state with an old watermark
        old_state = MCPState()
        old_state.set_watermark(
            "alice@s.whatsapp.net",
            _TWO_DAYS_AGO - timedelta(days=10),
        )
        old_state.save(state_file)

        summary = run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_file,
        )

        assert summary["success"] is True

        # Reload state and check watermark
        new_state = MCPState.load(state_file)
        watermark = new_state.get_watermark("alice@s.whatsapp.net")
        assert watermark is not None
        assert watermark >= _NOW

    def test_contact_cache_updated(self, bridge_db, output_dir):
        """Contact cache should be updated with the chat name."""
        state_file = output_dir / ".sync-state.json"

        run_rebuild(
            chat_identifier="Alice Smith",
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_file,
        )

        state = MCPState.load(state_file)
        cached = state.get_contact_name("alice@s.whatsapp.net")
        assert cached == "Alice Smith"


class TestRebuildErrors:
    """Test error handling."""

    def test_chat_not_found(self, bridge_db, output_dir):
        """Should report error when chat is not found."""
        summary = run_rebuild(
            chat_identifier="Nonexistent Person",
            output_dir=output_dir,
            db_path=bridge_db,
        )

        assert summary["success"] is False
        assert "not found" in summary["error"]

    def test_missing_db(self, tmp_path):
        """Should report error when bridge DB does not exist."""
        summary = run_rebuild(
            chat_identifier="Alice",
            output_dir=tmp_path / "output",
            db_path=tmp_path / "nonexistent.db",
        )

        assert summary["success"] is False
        assert summary["error"] is not None

    def test_ambiguous_chat_name(self, tmp_path):
        """Should report error when chat name matches multiple chats."""
        db_path = tmp_path / "messages.db"
        _create_bridge_db(
            db_path,
            chats=[
                ("alice1@s.whatsapp.net", "Alice Smith", _ts(_NOW)),
                ("alice2@s.whatsapp.net", "Alice Jones", _ts(_NOW)),
            ],
            messages=[
                ("msg1", "alice1@s.whatsapp.net", "alice1@s.whatsapp.net",
                 "Hello!", _ts(_NOW), 0, None, None),
                ("msg2", "alice2@s.whatsapp.net", "alice2@s.whatsapp.net",
                 "Hi!", _ts(_NOW), 0, None, None),
            ],
        )

        summary = run_rebuild(
            chat_identifier="Alice",
            output_dir=tmp_path / "output",
            db_path=db_path,
        )

        assert summary["success"] is False
        assert "not found" in summary["error"]
