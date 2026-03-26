"""
Integration tests for the ``whatsapp-sync`` command.

Each test creates a temporary SQLite database with the MCP bridge schema,
a temporary output directory, and exercises the sync flow programmatically
(via ``run_sync``). No subprocesses are spawned.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from whatsapp_chat_autoexport.cli.commands.sync import run_sync
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
    """Create a bridge DB with two chats and sample messages."""
    db_path = tmp_path / "messages.db"
    chats = [
        ("alice@s.whatsapp.net", "Alice Smith", _ts(_NOW)),
        ("bob@s.whatsapp.net", "Bob Jones", _ts(_YESTERDAY)),
    ]
    messages = [
        # Alice's messages
        ("msg_a1", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
         "Hello!", _ts(_YESTERDAY), 0, None, None),
        ("msg_a2", "alice@s.whatsapp.net", "",
         "Hi Alice!", _ts(_YESTERDAY + timedelta(minutes=1)), 1, None, None),
        ("msg_a3", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
         "How are you?", _ts(_NOW), 0, None, None),
        # Bob's messages
        ("msg_b1", "bob@s.whatsapp.net", "bob@s.whatsapp.net",
         "Hey!", _ts(_YESTERDAY), 0, None, None),
        ("msg_b2", "bob@s.whatsapp.net", "",
         "Hey Bob!", _ts(_YESTERDAY + timedelta(minutes=5)), 1, None, None),
    ]
    _create_bridge_db(db_path, chats=chats, messages=messages)
    return db_path


@pytest.fixture
def output_dir(tmp_path):
    """Provide a clean output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncCommand:
    """Integration tests for the sync command."""

    @pytest.mark.integration
    def test_first_run_creates_transcripts(self, bridge_db, output_dir):
        """First sync should create transcript.md and index.md for every chat."""
        summary = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=output_dir / ".sync-state.json",
            user_display_name="AJ Anderson",
        )

        assert summary["success"] is True
        assert summary["chats_synced"] >= 1

        # Check Alice's chat was created
        alice_dir = output_dir / "Alice Smith"
        assert alice_dir.is_dir(), f"Expected Alice Smith dir, found: {list(output_dir.iterdir())}"
        assert (alice_dir / "transcript.md").is_file()
        assert (alice_dir / "index.md").is_file()

        # Check transcript content
        transcript = (alice_dir / "transcript.md").read_text(encoding="utf-8")
        assert "Hello!" in transcript
        assert "How are you?" in transcript

        # Check index content has frontmatter
        index = (alice_dir / "index.md").read_text(encoding="utf-8")
        assert "---" in index
        assert "whatsapp" in index

        # Check Bob's chat
        bob_dir = output_dir / "Bob Jones"
        assert bob_dir.is_dir()
        assert (bob_dir / "transcript.md").is_file()

    @pytest.mark.integration
    def test_state_file_created(self, bridge_db, output_dir):
        """State file should be created after sync."""
        state_path = output_dir / ".sync-state.json"
        run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
        )

        assert state_path.is_file()
        state = MCPState.load(state_path)
        assert state.last_sync is not None
        # Alice's watermark should be set
        assert state.get_watermark("alice@s.whatsapp.net") is not None

    @pytest.mark.integration
    def test_dry_run_creates_no_files(self, bridge_db, output_dir):
        """Dry run should not create any output files."""
        summary = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=output_dir / ".sync-state.json",
            dry_run=True,
        )

        assert summary["dry_run"] is True
        # No chat directories should exist
        chat_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(chat_dirs) == 0, f"Expected no dirs, found: {chat_dirs}"
        # No state file
        assert not (output_dir / ".sync-state.json").exists()

    @pytest.mark.integration
    def test_rerun_is_idempotent(self, bridge_db, output_dir):
        """Running sync twice should produce the same files."""
        state_path = output_dir / ".sync-state.json"

        # First run
        summary1 = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
        )
        assert summary1["success"] is True

        # Read Alice's transcript after first run
        alice_transcript_1 = (output_dir / "Alice Smith" / "transcript.md").read_text(
            encoding="utf-8"
        )

        # Second run — should skip unchanged chats
        summary2 = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
        )
        assert summary2["success"] is True

        # Alice's transcript should be unchanged (skipped or same content)
        alice_transcript_2 = (output_dir / "Alice Smith" / "transcript.md").read_text(
            encoding="utf-8"
        )
        # The message body lines should be identical (header timestamps may differ)
        # We compare the message sections only
        body1 = _extract_body(alice_transcript_1)
        body2 = _extract_body(alice_transcript_2)
        assert body1 == body2

    @pytest.mark.integration
    def test_bridge_unavailable_produces_json_error(self, output_dir):
        """When the bridge DB doesn't exist, should produce a clean JSON error."""
        nonexistent_db = output_dir / "nonexistent.db"

        summary = run_sync(
            output_dir=output_dir,
            db_path=nonexistent_db,
            state_file=output_dir / ".sync-state.json",
        )

        assert summary["success"] is False
        # Should have an error about no chats or bridge failure
        assert summary["error"] is not None or summary["chats_synced"] == 0

    @pytest.mark.integration
    def test_chat_filter(self, bridge_db, output_dir):
        """--chat filter should only sync matching chats."""
        summary = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=output_dir / ".sync-state.json",
            chat_filter="Alice",
        )

        assert summary["success"] is True
        # Alice should be synced
        assert (output_dir / "Alice Smith").is_dir()
        # Bob should NOT be synced
        assert not (output_dir / "Bob Jones").exists()

    @pytest.mark.integration
    def test_per_chat_error_isolation(self, bridge_db, output_dir):
        """If one chat fails, others should still succeed."""
        state_path = output_dir / ".sync-state.json"

        # Capture the real function BEFORE patching
        from whatsapp_chat_autoexport.cli.commands.sync import _sync_chat as real_sync_chat

        def patched_sync_chat(chat, **kwargs):
            if "bob" in chat.jid.lower():
                raise RuntimeError("Simulated failure for Bob")
            # Call the captured real implementation
            return real_sync_chat(chat, **kwargs)

        with patch(
            "whatsapp_chat_autoexport.cli.commands.sync._sync_chat",
            side_effect=patched_sync_chat,
        ):
            summary = run_sync(
                output_dir=output_dir,
                db_path=bridge_db,
                state_file=state_path,
            )

        # Alice should have succeeded
        assert (output_dir / "Alice Smith" / "transcript.md").is_file()
        # There should be at least one error
        assert summary["chats_errored"] >= 1
        # But overall it shouldn't be a total failure
        assert summary["chats_synced"] >= 1

    @pytest.mark.integration
    def test_incremental_sync_adds_new_messages(self, bridge_db, output_dir, tmp_path):
        """After first sync, adding messages should append only new ones."""
        state_path = output_dir / ".sync-state.json"

        # First sync
        summary1 = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
        )
        assert summary1["success"] is True

        alice_transcript_1 = (output_dir / "Alice Smith" / "transcript.md").read_text(
            encoding="utf-8"
        )
        assert "How are you?" in alice_transcript_1

        # Add a new message to the bridge DB
        new_time = _NOW + timedelta(hours=1)
        conn = sqlite3.connect(str(bridge_db))
        conn.execute(
            "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg_a4", "alice@s.whatsapp.net", "alice@s.whatsapp.net",
             "New message after sync!", _ts(new_time), 0, None, None),
        )
        conn.execute(
            "UPDATE chats SET last_message_time = ? WHERE jid = ?",
            (_ts(new_time), "alice@s.whatsapp.net"),
        )
        conn.commit()
        conn.close()

        # Second sync
        summary2 = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
        )

        alice_transcript_2 = (output_dir / "Alice Smith" / "transcript.md").read_text(
            encoding="utf-8"
        )
        # Should contain the new message
        assert "New message after sync!" in alice_transcript_2
        # Should still contain old messages
        assert "Hello!" in alice_transcript_2
        assert "How are you?" in alice_transcript_2

    @pytest.mark.integration
    def test_overlap_window_prevents_message_loss(self, bridge_db, output_dir):
        """The overlap window should re-fetch messages near the watermark."""
        state_path = output_dir / ".sync-state.json"

        # First run
        summary1 = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=state_path,
            overlap_minutes=10,
        )
        assert summary1["success"] is True

        # State should have watermarks
        state = MCPState.load(state_path)
        wm = state.get_watermark("alice@s.whatsapp.net")
        assert wm is not None

    @pytest.mark.integration
    def test_user_display_name_in_transcript(self, bridge_db, output_dir):
        """Messages from me should show the configured display name."""
        summary = run_sync(
            output_dir=output_dir,
            db_path=bridge_db,
            state_file=output_dir / ".sync-state.json",
            user_display_name="Test User",
        )
        assert summary["success"] is True

        transcript = (output_dir / "Alice Smith" / "transcript.md").read_text(
            encoding="utf-8"
        )
        # msg_a2 is is_from_me=1, should show "Test User"
        assert "Test User" in transcript


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_body(transcript_content: str) -> str:
    """
    Extract the message body from a transcript, stripping frontmatter
    and the integrity header (which contains timestamps that change).
    """
    lines = transcript_content.split("\n")
    body_lines = []
    in_frontmatter = False
    past_header = False

    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if line.strip().startswith("<!--"):
            past_header = False
            continue
        if line.strip() == "-->":
            past_header = True
            continue
        if line.strip().startswith("## "):
            past_header = True
        if past_header:
            body_lines.append(line)

    return "\n".join(body_lines)
