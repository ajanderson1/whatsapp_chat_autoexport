# WhatsApp Sync Service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A continuously-running service (Go bridge + Python daemon) that maintains a complete, append-only WhatsApp chat archive in the Obsidian journal, deployed on Pi 5.

**Architecture:** Go bridge (whatsmeow) writes messages to SQLite + downloads voice audio. Python daemon polls SQLite every 60s, formats to spec, transcribes voice via ElevenLabs, writes to journal repo, pushes Kuma heartbeats. SQLite is the only contract between Go and Python.

**Tech Stack:** Go 1.22+ (whatsmeow), Python 3.13 (Poetry), SQLite, httpx, ElevenLabs API, systemd, pytest.

**Design spec:** `docs/specs/2026-04-19-whatsapp-sync-service-design.md`

**Repo:** `/Users/ajanderson/GitHub/projects/whatsapp_sync` (new repo)

---

## Dependency: Exporter --format spec

This plan depends on `docs/plans/2026-04-19-002-feat-format-spec-output-plan.md` being completed first. The `SpecFormatter` class in the exporter repo defines the canonical output format. The Python daemon in this plan must produce byte-compatible output.

The `SpecFormatter` test fixtures (expected output for known message inputs) serve as the shared format compliance test. The daemon's `formatter.py` must pass the same assertions.

---

## File Structure

```
whatsapp_sync/                  # repo root
├── bridge/                     # Go binary
│   ├── go.mod
│   ├── go.sum
│   ├── main.go                 # entry point, event loop, config
│   ├── db.go                   # SQLite schema + write methods
│   ├── health.go               # /health HTTP endpoint
│   ├── kuma.go                 # Kuma push client
│   └── config.yaml.example     # example config
├── daemon/                     # Python package
│   ├── pyproject.toml
│   ├── whatsapp_sync/
│   │   ├── __init__.py
│   │   ├── daemon.py           # main loop, signal handling
│   │   ├── bridge_reader.py    # SQLite reader -> Message objects
│   │   ├── formatter.py        # Messages -> spec format strings
│   │   ├── vault_writer.py     # atomic file writes, index.md updates
│   │   ├── dedup.py            # message deduplication
│   │   ├── transcriber.py      # ElevenLabs wrapper
│   │   ├── voice_queue.py      # persistent retry queue
│   │   ├── gap_detector.py     # connection gap analysis
│   │   ├── health.py           # Kuma push client (4 monitors)
│   │   ├── config.py           # YAML config loader
│   │   └── state.py            # state.json read/write
│   └── tests/
│       ├── conftest.py
│       ├── test_bridge_reader.py
│       ├── test_formatter.py
│       ├── test_vault_writer.py
│       ├── test_dedup.py
│       ├── test_voice_queue.py
│       ├── test_gap_detector.py
│       ├── test_health.py
│       └── test_daemon.py
├── config.yaml.example         # daemon config example
├── .env.example                # API keys, Kuma URLs
├── systemd/                    # service unit files
│   ├── whatsapp-bridge.service
│   └── whatsapp-sync.service
└── README.md
```

---

## Phase 1: Project Scaffolding

### Task 1: Initialize repo and Python project

**Files:**
- Create: `whatsapp_sync/daemon/pyproject.toml`
- Create: `whatsapp_sync/daemon/whatsapp_sync/__init__.py`
- Create: `whatsapp_sync/daemon/tests/conftest.py`
- Create: `whatsapp_sync/.gitignore`
- Create: `whatsapp_sync/README.md`

- [ ] **Step 1: Create repo directory**

```bash
mkdir -p /Users/ajanderson/GitHub/projects/whatsapp_sync
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git init
```

- [ ] **Step 2: Create .gitignore**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/

# Go
bridge/whatsapp-bridge
bridge/store/

# Data
data/
*.db
*.db-journal
state.json

# Environment
.env

# IDE
.idea/
.vscode/

# Logs
logs/
```

- [ ] **Step 3: Create pyproject.toml**

```toml
# daemon/pyproject.toml
[tool.poetry]
name = "whatsapp-sync"
version = "0.1.0"
description = "WhatsApp sync daemon — polls whatsmeow bridge SQLite, writes to Obsidian vault"
authors = ["AJ Anderson"]
readme = "README.md"
packages = [{include = "whatsapp_sync"}]

[tool.poetry.dependencies]
python = "^3.13"
pyyaml = "^6.0"
httpx = "^0.28"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^6.0"

[tool.poetry.scripts]
whatsapp-sync = "whatsapp_sync.daemon:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: Fast isolated unit tests",
    "integration: Integration tests",
]

[tool.coverage.run]
source = ["whatsapp_sync"]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 90
show_missing = true

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 4: Create __init__.py**

```python
# daemon/whatsapp_sync/__init__.py
"""WhatsApp Sync Daemon — polls bridge SQLite, writes to Obsidian vault."""
```

- [ ] **Step 5: Create conftest.py**

```python
# daemon/tests/conftest.py
"""Shared test fixtures for whatsapp_sync tests."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with the bridge schema."""
    db_path = tmp_path / "messages.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            chat_jid TEXT NOT NULL,
            sender_jid TEXT NOT NULL,
            sender_name TEXT,
            content TEXT,
            timestamp INTEGER NOT NULL,
            is_from_me BOOLEAN NOT NULL,
            media_type TEXT,
            media_path TEXT,
            raw_proto BLOB
        );

        CREATE TABLE connection_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            detail TEXT
        );

        CREATE TABLE chats (
            jid TEXT PRIMARY KEY,
            name TEXT,
            is_group BOOLEAN NOT NULL,
            last_message_at INTEGER,
            participant_jids TEXT
        );
    """)
    conn.close()
    return db_path


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary vault directory structure."""
    vault = tmp_path / "Journal"
    whatsapp_dir = vault / "People" / "Correspondence" / "Whatsapp"
    whatsapp_dir.mkdir(parents=True)
    return vault


@pytest.fixture
def tmp_state(tmp_path):
    """Path for a temporary state.json file."""
    return tmp_path / "state.json"


@pytest.fixture
def sample_messages_in_db(tmp_db):
    """Populate the test database with sample messages."""
    conn = sqlite3.connect(tmp_db)
    now = int(datetime(2026, 4, 19, 14, 30).timestamp())

    # Insert a chat
    conn.execute(
        "INSERT INTO chats (jid, name, is_group, last_message_at) VALUES (?, ?, ?, ?)",
        ("447956173473@s.whatsapp.net", "Tim Cocking", False, now),
    )

    # Insert messages
    messages = [
        ("msg001", "447956173473@s.whatsapp.net", "447956173473@s.whatsapp.net",
         "Tim Cocking", "Hey mate", now - 120, False, None, None),
        ("msg002", "447956173473@s.whatsapp.net", "me",
         "AJ Anderson", "How's it going?", now - 60, True, None, None),
        ("msg003", "447956173473@s.whatsapp.net", "447956173473@s.whatsapp.net",
         "Tim Cocking", None, now, False, "audio",
         "/data/voice/msg003.ogg"),
    ]

    for m in messages:
        conn.execute(
            "INSERT INTO messages (id, chat_jid, sender_jid, sender_name, content, "
            "timestamp, is_from_me, media_type, media_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            m,
        )

    # Insert connection log
    conn.execute(
        "INSERT INTO connection_log (event, timestamp, detail) VALUES (?, ?, ?)",
        ("connected", now - 3600, "initial connection"),
    )

    conn.commit()
    conn.close()
    return tmp_db
```

- [ ] **Step 6: Install dependencies**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon
poetry install --with dev
```

- [ ] **Step 7: Verify pytest runs**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest -v`
Expected: `no tests ran` (collected 0 items) — no errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add .
git commit -m "chore: initialize whatsapp_sync repo

Python daemon scaffold with Poetry, pytest, shared SQLite fixtures.
Go bridge directory placeholder."
```

---

## Phase 2: Python Daemon Core

### Task 2: bridge_reader — read messages from SQLite

**Files:**
- Create: `daemon/whatsapp_sync/bridge_reader.py`
- Create: `daemon/tests/test_bridge_reader.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_bridge_reader.py
"""Tests for bridge_reader — SQLite message reading."""

from datetime import datetime

import pytest

from whatsapp_sync.bridge_reader import BridgeReader, Message


@pytest.mark.unit
class TestBridgeReader:

    def test_get_chats(self, sample_messages_in_db):
        """Returns all chats with metadata."""
        reader = BridgeReader(sample_messages_in_db)
        chats = reader.get_chats()

        assert len(chats) == 1
        assert chats[0]["jid"] == "447956173473@s.whatsapp.net"
        assert chats[0]["name"] == "Tim Cocking"
        assert chats[0]["is_group"] is False

    def test_get_messages_all(self, sample_messages_in_db):
        """Returns all messages for a chat in chronological order."""
        reader = BridgeReader(sample_messages_in_db)
        messages = reader.get_messages("447956173473@s.whatsapp.net")

        assert len(messages) == 3
        assert messages[0].id == "msg001"
        assert messages[1].id == "msg002"
        assert messages[2].id == "msg003"
        # Chronological order
        assert messages[0].timestamp < messages[1].timestamp

    def test_get_messages_after_watermark(self, sample_messages_in_db):
        """Returns only messages after the given timestamp."""
        reader = BridgeReader(sample_messages_in_db)
        all_msgs = reader.get_messages("447956173473@s.whatsapp.net")

        # Use timestamp of msg002 as watermark
        watermark = all_msgs[1].timestamp
        filtered = reader.get_messages(
            "447956173473@s.whatsapp.net",
            after=watermark,
        )

        # Should get msg002 (overlap) and msg003
        assert len(filtered) >= 1
        assert all(m.timestamp >= watermark for m in filtered)

    def test_get_messages_with_overlap(self, sample_messages_in_db):
        """Overlap window fetches messages before the watermark."""
        reader = BridgeReader(sample_messages_in_db)
        all_msgs = reader.get_messages("447956173473@s.whatsapp.net")

        watermark = all_msgs[2].timestamp  # msg003
        filtered = reader.get_messages(
            "447956173473@s.whatsapp.net",
            after=watermark,
            overlap_seconds=600,  # 10 min overlap
        )

        # Overlap should include earlier messages
        assert len(filtered) >= 2

    def test_message_dataclass_fields(self, sample_messages_in_db):
        """Message objects have all expected fields."""
        reader = BridgeReader(sample_messages_in_db)
        messages = reader.get_messages("447956173473@s.whatsapp.net")

        msg = messages[0]
        assert msg.id == "msg001"
        assert msg.sender_name == "Tim Cocking"
        assert msg.content == "Hey mate"
        assert isinstance(msg.timestamp, int)
        assert msg.is_from_me is False
        assert msg.media_type is None

    def test_voice_message_has_media_path(self, sample_messages_in_db):
        """Voice messages include media_path."""
        reader = BridgeReader(sample_messages_in_db)
        messages = reader.get_messages("447956173473@s.whatsapp.net")

        voice_msg = messages[2]
        assert voice_msg.media_type == "audio"
        assert voice_msg.media_path == "/data/voice/msg003.ogg"

    def test_empty_chat_returns_empty_list(self, tmp_db):
        """Non-existent chat returns empty message list."""
        reader = BridgeReader(tmp_db)
        messages = reader.get_messages("nonexistent@s.whatsapp.net")
        assert messages == []

    def test_get_changed_chats(self, sample_messages_in_db):
        """Returns chats with last_message_at > given watermarks."""
        reader = BridgeReader(sample_messages_in_db)
        all_chats = reader.get_chats()

        # Watermark older than all messages — chat should be returned
        watermarks = {"447956173473@s.whatsapp.net": 0}
        changed = reader.get_changed_chats(watermarks)
        assert len(changed) == 1

        # Watermark equal to latest — chat should NOT be returned
        watermarks = {"447956173473@s.whatsapp.net": all_chats[0]["last_message_at"]}
        changed = reader.get_changed_chats(watermarks)
        assert len(changed) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_bridge_reader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement BridgeReader**

```python
# daemon/whatsapp_sync/bridge_reader.py
"""Reads messages from the whatsmeow bridge SQLite database."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Message:
    """A WhatsApp message read from the bridge database."""

    id: str
    chat_jid: str
    sender_jid: str
    sender_name: Optional[str]
    content: Optional[str]
    timestamp: int  # Unix epoch seconds
    is_from_me: bool
    media_type: Optional[str]
    media_path: Optional[str]


class BridgeReader:
    """Reads from the whatsmeow bridge SQLite database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_chats(self) -> List[Dict]:
        """Return all chats with metadata."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT jid, name, is_group, last_message_at, participant_jids "
                "FROM chats ORDER BY last_message_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_messages(
        self,
        chat_jid: str,
        after: Optional[int] = None,
        overlap_seconds: int = 0,
    ) -> List[Message]:
        """
        Return messages for a chat, optionally filtered by timestamp.

        Args:
            chat_jid: Chat JID to query.
            after: Only return messages at or after this Unix timestamp.
            overlap_seconds: Subtract this from `after` to re-fetch
                             recent messages for dedup safety.
        """
        conn = self._connect()
        try:
            if after is not None:
                effective_after = after - overlap_seconds
                rows = conn.execute(
                    "SELECT id, chat_jid, sender_jid, sender_name, content, "
                    "timestamp, is_from_me, media_type, media_path "
                    "FROM messages WHERE chat_jid = ? AND timestamp >= ? "
                    "ORDER BY timestamp ASC",
                    (chat_jid, effective_after),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, chat_jid, sender_jid, sender_name, content, "
                    "timestamp, is_from_me, media_type, media_path "
                    "FROM messages WHERE chat_jid = ? ORDER BY timestamp ASC",
                    (chat_jid,),
                ).fetchall()

            return [
                Message(
                    id=r["id"],
                    chat_jid=r["chat_jid"],
                    sender_jid=r["sender_jid"],
                    sender_name=r["sender_name"],
                    content=r["content"],
                    timestamp=r["timestamp"],
                    is_from_me=bool(r["is_from_me"]),
                    media_type=r["media_type"],
                    media_path=r["media_path"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def get_changed_chats(self, watermarks: Dict[str, int]) -> List[Dict]:
        """Return chats whose last_message_at exceeds their stored watermark."""
        all_chats = self.get_chats()
        changed = []
        for chat in all_chats:
            jid = chat["jid"]
            stored = watermarks.get(jid, 0)
            if chat["last_message_at"] and chat["last_message_at"] > stored:
                changed.append(chat)
        return changed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_bridge_reader.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/bridge_reader.py daemon/tests/test_bridge_reader.py
git commit -m "feat: add BridgeReader — SQLite message reader

Reads messages, chats, and changed-chat detection from whatsmeow bridge
SQLite. Supports watermark filtering with configurable overlap window."
```

---

### Task 3: formatter — Messages to spec format

**Files:**
- Create: `daemon/whatsapp_sync/formatter.py`
- Create: `daemon/tests/test_formatter.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_formatter.py
"""Tests for formatter — bridge Messages to spec format."""

from datetime import datetime

import pytest

from whatsapp_sync.bridge_reader import Message
from whatsapp_sync.formatter import format_messages, format_index


def _make_msg(id, sender, content, ts_epoch, media_type=None, media_path=None, is_from_me=False):
    """Helper to create Message objects."""
    return Message(
        id=id,
        chat_jid="447956173473@s.whatsapp.net",
        sender_jid="sender@s.whatsapp.net",
        sender_name=sender,
        content=content,
        timestamp=ts_epoch,
        is_from_me=is_from_me,
        media_type=media_type,
        media_path=media_path,
    )


@pytest.mark.unit
class TestFormatMessages:

    def test_single_text_message(self):
        """Single message produces day header + formatted line."""
        ts = int(datetime(2015, 7, 29, 0, 5).timestamp())
        messages = [_make_msg("m1", "AJ Anderson", "Hello", ts)]

        result = format_messages(messages)

        assert "## 2015-07-29" in result
        assert "[00:05] AJ Anderson: Hello" in result

    def test_multiple_messages_same_day(self):
        """Same-day messages share one day header."""
        ts1 = int(datetime(2015, 7, 29, 0, 5).timestamp())
        ts2 = int(datetime(2015, 7, 29, 0, 11).timestamp())
        messages = [
            _make_msg("m1", "AJ Anderson", "First", ts1),
            _make_msg("m2", "Tim Cocking", "Second", ts2),
        ]

        result = format_messages(messages)
        assert result.count("## 2015-07-29") == 1

    def test_messages_across_days(self):
        """Different days get separate headers."""
        ts1 = int(datetime(2015, 7, 29, 23, 59).timestamp())
        ts2 = int(datetime(2015, 7, 30, 0, 1).timestamp())
        messages = [
            _make_msg("m1", "AJ Anderson", "Late", ts1),
            _make_msg("m2", "Tim Cocking", "Early", ts2),
        ]

        result = format_messages(messages)
        assert "## 2015-07-29" in result
        assert "## 2015-07-30" in result

    def test_voice_message_tag(self):
        """Audio messages get <voice> tag."""
        ts = int(datetime(2024, 1, 15, 10, 15).timestamp())
        messages = [_make_msg("m1", "Tim Cocking", None, ts, media_type="audio")]

        result = format_messages(messages)
        assert "[10:15] Tim Cocking: <voice>" in result

    def test_photo_message_tag(self):
        """Image messages get <photo> tag."""
        ts = int(datetime(2024, 1, 15, 16, 56).timestamp())
        messages = [_make_msg("m1", "Tim Cocking", None, ts, media_type="image")]

        result = format_messages(messages)
        assert "[16:56] Tim Cocking: <photo>" in result

    def test_video_message_tag(self):
        """Video messages get <video> tag."""
        ts = int(datetime(2024, 1, 15, 14, 22).timestamp())
        messages = [_make_msg("m1", "AJ Anderson", None, ts, media_type="video")]

        result = format_messages(messages)
        assert "[14:22] AJ Anderson: <video>" in result

    def test_document_message_tag(self):
        """Document messages get <document> tag."""
        ts = int(datetime(2024, 1, 15, 11, 45).timestamp())
        messages = [_make_msg("m1", "AJ Anderson", "report.pdf", ts, media_type="document")]

        result = format_messages(messages)
        assert "<document>" in result

    def test_is_from_me_uses_configured_name(self):
        """Messages from self use the configured owner name."""
        ts = int(datetime(2024, 1, 15, 10, 0).timestamp())
        messages = [_make_msg("m1", None, "Hello", ts, is_from_me=True)]

        result = format_messages(messages, owner_name="AJ Anderson")
        assert "[10:00] AJ Anderson: Hello" in result


@pytest.mark.unit
class TestFormatIndex:

    def test_direct_chat_index(self):
        """Direct chat index has correct frontmatter."""
        ts = int(datetime(2015, 7, 29, 0, 5).timestamp())
        messages = [_make_msg("m1", "Tim Cocking", "Hey", ts)]

        result = format_index(
            messages=messages,
            contact_name="Tim Cocking",
            chat_jid="447956173473@s.whatsapp.net",
            chat_type="direct",
        )

        assert "type: note" in result
        assert 'contact: "[[Tim Cocking]]"' in result
        assert "chat_type: direct" in result
        assert "message_count: 1" in result

    def test_group_chat_index(self):
        """Group chat index uses participants."""
        ts = int(datetime(2016, 1, 5, 12, 0).timestamp())
        messages = [_make_msg("m1", "Tim Cocking", "Hello", ts)]

        result = format_index(
            messages=messages,
            contact_name="Brothers",
            chat_jid="group@g.us",
            chat_type="group",
            participants=["Tim Cocking", "Peter Cocking"],
        )

        assert "chat_type: group" in result
        assert 'chat_name: "Brothers"' in result
        assert '  - "[[Tim Cocking]]"' in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_formatter.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement formatter.py**

```python
# daemon/whatsapp_sync/formatter.py
"""
Format bridge Messages into the WhatsApp Transcript Format Spec.

Produces strings for transcript.md and index.md content. Pure functions —
no file I/O, no side effects.
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .bridge_reader import Message


_MEDIA_TAG_MAP = {
    "image": "photo",
    "audio": "voice",
    "video": "video",
    "document": "document",
    "sticker": "sticker",
    "gif": "gif",
}


def format_messages(
    messages: List[Message],
    owner_name: str = "AJ Anderson",
    transcriptions: Optional[Dict[str, str]] = None,
) -> str:
    """
    Format messages into spec-format body text.

    Args:
        messages: Chronologically ordered messages.
        owner_name: Display name for is_from_me messages.
        transcriptions: Optional dict of message_id -> transcription text.

    Returns:
        Formatted message body (day headers + message lines).
    """
    if transcriptions is None:
        transcriptions = {}

    lines: List[str] = []
    current_date: Optional[str] = None

    for msg in messages:
        dt = datetime.fromtimestamp(msg.timestamp)
        msg_date = dt.strftime("%Y-%m-%d")

        # Day header
        if msg_date != current_date:
            if current_date is not None:
                lines.append("")
            lines.append(f"## {msg_date}")
            lines.append("")
            current_date = msg_date

        # Sender name
        sender = owner_name if msg.is_from_me else (msg.sender_name or msg.sender_jid)

        # Content
        if msg.media_type:
            tag = _MEDIA_TAG_MAP.get(msg.media_type, "media")
            content = f"<{tag}>"
        else:
            content = msg.content or ""

        time_str = dt.strftime("%H:%M")
        lines.append(f"[{time_str}] {sender}: {content}")

        # Inline transcription
        if msg.media_type == "audio" and msg.id in transcriptions:
            lines.append(f"  [Transcription]: {transcriptions[msg.id]}")

    return "\n".join(lines) + "\n" if lines else ""


def format_transcript_file(
    messages: List[Message],
    contact_name: str,
    chat_jid: str = "",
    owner_name: str = "AJ Anderson",
    transcriptions: Optional[Dict[str, str]] = None,
) -> str:
    """
    Format a complete transcript.md file with frontmatter and metadata.

    Args:
        messages: All messages for this chat.
        contact_name: Chat/contact display name.
        chat_jid: WhatsApp JID.
        owner_name: Display name for is_from_me messages.
        transcriptions: Optional dict of message_id -> transcription text.

    Returns:
        Complete transcript.md content.
    """
    body = format_messages(messages, owner_name=owner_name, transcriptions=transcriptions)

    media_count = sum(1 for m in messages if m.media_type)
    date_first = datetime.fromtimestamp(messages[0].timestamp).strftime("%Y-%m-%d") if messages else ""
    date_last = datetime.fromtimestamp(messages[-1].timestamp).strftime("%Y-%m-%d") if messages else ""
    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    frontmatter = (
        "---\n"
        "cssclasses:\n"
        "  - whatsapp-transcript\n"
        "  - exclude-from-graph\n"
        "---\n"
    )

    metadata = (
        f"<!-- TRANSCRIPT METADATA\n"
        f"chat_jid: {chat_jid}\n"
        f"contact: {contact_name}\n"
        f"generated: {now}\n"
        f"generator: whatsapp-sync/1.0.0\n"
        f"message_count: {len(messages)}\n"
        f"media_count: {media_count}\n"
        f"date_range: {date_first}..{date_last}\n"
        f"body_sha256: {body_sha256}\n"
        f"-->\n"
    )

    return frontmatter + "\n" + metadata + "\n" + body


def format_index(
    messages: List[Message],
    contact_name: str,
    chat_jid: str = "",
    chat_type: str = "direct",
    participants: Optional[List[str]] = None,
    timezone_str: str = "Europe/Stockholm",
    source_type: str = "mcp_bridge",
) -> str:
    """
    Format an index.md companion note.

    Args:
        messages: All messages (for stats).
        contact_name: Chat/contact display name.
        chat_jid: WhatsApp JID.
        chat_type: "direct" or "group".
        participants: Group chat participant names.
        timezone_str: Timezone string for frontmatter.
        source_type: Source provenance type.

    Returns:
        Complete index.md content.
    """
    if participants is None:
        participants = []

    media_count = sum(1 for m in messages if m.media_type)
    voice_count = sum(1 for m in messages if m.media_type == "audio")
    date_first = datetime.fromtimestamp(messages[0].timestamp).strftime("%Y-%m-%d") if messages else ""
    date_last = datetime.fromtimestamp(messages[-1].timestamp).strftime("%Y-%m-%d") if messages else ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = ["---", "type: note"]

    if chat_type == "group":
        lines.append(f'description: "WhatsApp group chat — {contact_name}"')
    else:
        lines.append(f'description: "WhatsApp correspondence with {contact_name}"')

    lines.extend([
        "tags:", "  - whatsapp", "  - correspondence",
    ])
    if chat_type == "group":
        lines.append("  - group_chat")

    lines.extend(["cssclasses:", "  - whatsapp-chat", "", f"chat_type: {chat_type}"])

    if chat_type == "group":
        lines.append(f'chat_name: "{contact_name}"')
        lines.append("participants:")
        for p in participants:
            lines.append(f'  - "[[{p}]]"')
    else:
        lines.append(f'contact: "[[{contact_name}]]"')

    if chat_jid:
        lines.append(f'jid: "{chat_jid}"')

    lines.extend([
        "", f"message_count: {len(messages)}", f"media_count: {media_count}",
        f"voice_count: {voice_count}", f"date_first: {date_first}",
        f"date_last: {date_last}", f"last_synced: {now}",
        "", "sources:", f"  - type: {source_type}", f"    date: {today}",
        f"    messages: {len(messages)}", "coverage_gaps: 0",
        "", f"timezone: {timezone_str}", "---",
    ])

    # Body
    if chat_type == "group":
        summary = f"> WhatsApp group chat — {contact_name}"
    else:
        summary = f"> WhatsApp correspondence with [[{contact_name}]]"

    period = f"{date_first} to {date_last}" if date_first else "unknown"
    summary += f"\n> Period: {period} | {len(messages):,} messages"

    folder = f"People/Correspondence/Whatsapp/{contact_name}"
    link = f"[[{folder}/transcript|Full Transcript]]"

    return "\n".join(lines) + f"\n\n{summary}\n\n{link}\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_formatter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/formatter.py daemon/tests/test_formatter.py
git commit -m "feat: add formatter — bridge Messages to spec format

Pure functions: format_messages(), format_transcript_file(), format_index().
Produces day headers, typed media tags, inline transcriptions, index.md
companion notes. No file I/O."
```

---

### Task 4: dedup — message deduplication

**Files:**
- Create: `daemon/whatsapp_sync/dedup.py`
- Create: `daemon/tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_dedup.py
"""Tests for dedup — message deduplication."""

from datetime import datetime

import pytest

from whatsapp_sync.bridge_reader import Message
from whatsapp_sync.dedup import deduplicate, compute_content_hash


def _msg(id, sender, content, ts, **kwargs):
    return Message(
        id=id, chat_jid="chat@s.whatsapp.net", sender_jid="s@s.whatsapp.net",
        sender_name=sender, content=content,
        timestamp=int(datetime(*ts).timestamp()),
        is_from_me=False, media_type=kwargs.get("media_type"),
        media_path=kwargs.get("media_path"),
    )


@pytest.mark.unit
class TestDeduplicate:

    def test_no_overlap_keeps_all(self):
        """No overlap → all new messages returned."""
        existing_ids = set()
        new = [_msg("m1", "Tim", "Hey", (2026, 4, 19, 10, 0))]

        result = deduplicate(new, existing_ids)
        assert len(result) == 1

    def test_full_overlap_removes_all(self):
        """Full overlap → empty list."""
        existing_ids = {"m1", "m2"}
        new = [
            _msg("m1", "Tim", "Hey", (2026, 4, 19, 10, 0)),
            _msg("m2", "AJ", "Hi", (2026, 4, 19, 10, 1)),
        ]

        result = deduplicate(new, existing_ids)
        assert len(result) == 0

    def test_partial_overlap(self):
        """Partial overlap → only new messages returned."""
        existing_ids = {"m1"}
        new = [
            _msg("m1", "Tim", "Old", (2026, 4, 19, 10, 0)),
            _msg("m2", "Tim", "New", (2026, 4, 19, 10, 5)),
        ]

        result = deduplicate(new, existing_ids)
        assert len(result) == 1
        assert result[0].id == "m2"

    def test_idempotent(self):
        """Running dedup twice on same input produces same output."""
        existing_ids = {"m1"}
        new = [
            _msg("m1", "Tim", "Old", (2026, 4, 19, 10, 0)),
            _msg("m2", "Tim", "New", (2026, 4, 19, 10, 5)),
        ]

        result1 = deduplicate(new, existing_ids)
        result2 = deduplicate(new, existing_ids)
        assert [m.id for m in result1] == [m.id for m in result2]

    def test_content_hash_dedup(self):
        """Messages without IDs in existing set use content hash fallback."""
        existing_hashes = set()
        msg = _msg("m1", "Tim", "Hello world", (2026, 4, 19, 10, 0))
        h = compute_content_hash(msg)
        existing_hashes.add(h)

        result = deduplicate([msg], set(), existing_hashes=existing_hashes)
        assert len(result) == 0

    def test_content_hash_stable(self):
        """Same message always produces same hash."""
        msg = _msg("m1", "Tim", "Hello world", (2026, 4, 19, 10, 0))
        h1 = compute_content_hash(msg)
        h2 = compute_content_hash(msg)
        assert h1 == h2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_dedup.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement dedup.py**

```python
# daemon/whatsapp_sync/dedup.py
"""Message deduplication — by ID or content hash."""

import hashlib
from typing import List, Optional, Set

from .bridge_reader import Message


def compute_content_hash(msg: Message) -> str:
    """
    Compute a stable hash for a message without relying on its ID.

    Uses: timestamp (minute-precision) + sender_name + first 100 chars of content.
    """
    ts_minute = msg.timestamp - (msg.timestamp % 60)
    sender = msg.sender_name or msg.sender_jid or ""
    content = (msg.content or "")[:100]
    raw = f"{ts_minute}:{sender}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deduplicate(
    new_messages: List[Message],
    existing_ids: Set[str],
    existing_hashes: Optional[Set[str]] = None,
) -> List[Message]:
    """
    Remove messages that already exist in the transcript.

    Dedup strategy:
    1. Primary: skip if message ID is in existing_ids.
    2. Fallback: skip if content hash is in existing_hashes.

    Args:
        new_messages: Messages from the bridge (may overlap with existing).
        existing_ids: Set of message IDs already in the transcript.
        existing_hashes: Optional set of content hashes from the transcript tail.

    Returns:
        List of messages that are genuinely new.
    """
    if existing_hashes is None:
        existing_hashes = set()

    result = []
    for msg in new_messages:
        if msg.id in existing_ids:
            continue
        if existing_hashes and compute_content_hash(msg) in existing_hashes:
            continue
        result.append(msg)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_dedup.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/dedup.py daemon/tests/test_dedup.py
git commit -m "feat: add dedup — message deduplication by ID and content hash

Primary dedup by WhatsApp message ID. Fallback to sha256(timestamp_minute
+ sender + content[:100]) for messages from non-bridge sources."
```

---

### Task 5: state — persistent state management

**Files:**
- Create: `daemon/whatsapp_sync/state.py`
- Create: `daemon/tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_state.py
"""Tests for state — persistent state management."""

import json

import pytest

from whatsapp_sync.state import SyncState


@pytest.mark.unit
class TestSyncState:

    def test_load_empty_state(self, tmp_state):
        """Loading non-existent file returns empty state."""
        state = SyncState.load(tmp_state)

        assert state.watermarks == {}
        assert state.voice_queue == []
        assert state.suspected_gaps == []

    def test_save_and_load_roundtrip(self, tmp_state):
        """State survives save/load cycle."""
        state = SyncState.load(tmp_state)
        state.watermarks["chat@s.whatsapp.net"] = 1713536400
        state.voice_queue.append({
            "message_id": "msg003",
            "chat_jid": "chat@s.whatsapp.net",
            "media_path": "/data/voice/msg003.ogg",
            "retries": 0,
        })

        state.save(tmp_state)

        loaded = SyncState.load(tmp_state)
        assert loaded.watermarks["chat@s.whatsapp.net"] == 1713536400
        assert len(loaded.voice_queue) == 1
        assert loaded.voice_queue[0]["message_id"] == "msg003"

    def test_atomic_save(self, tmp_state):
        """Save writes to .tmp then renames."""
        state = SyncState.load(tmp_state)
        state.watermarks["chat@s.whatsapp.net"] = 100

        state.save(tmp_state)

        # .tmp file should not remain
        assert not tmp_state.with_suffix(".json.tmp").exists()
        assert tmp_state.exists()

    def test_advance_watermark(self, tmp_state):
        """Watermark only advances forward, never backward."""
        state = SyncState.load(tmp_state)
        state.advance_watermark("chat@s.whatsapp.net", 200)
        assert state.watermarks["chat@s.whatsapp.net"] == 200

        # Attempt to go backward — should be ignored
        state.advance_watermark("chat@s.whatsapp.net", 100)
        assert state.watermarks["chat@s.whatsapp.net"] == 200

    def test_voice_queue_operations(self, tmp_state):
        """Enqueue, peek, and acknowledge voice items."""
        state = SyncState.load(tmp_state)

        state.enqueue_voice("msg003", "chat@s.whatsapp.net", "/data/voice/msg003.ogg")
        assert len(state.voice_queue) == 1

        # Peek returns items with retries < max
        items = state.peek_voice_queue(limit=5, max_retries=5)
        assert len(items) == 1

        # Acknowledge removes it
        state.acknowledge_voice("msg003")
        assert len(state.voice_queue) == 0

    def test_voice_queue_retry_increment(self, tmp_state):
        """Failed transcription increments retry count."""
        state = SyncState.load(tmp_state)
        state.enqueue_voice("msg003", "chat@s.whatsapp.net", "/path")

        state.increment_voice_retry("msg003")
        assert state.voice_queue[0]["retries"] == 1

    def test_voice_queue_max_retries_excluded(self, tmp_state):
        """Items at max retries are not returned by peek."""
        state = SyncState.load(tmp_state)
        state.enqueue_voice("msg003", "chat@s.whatsapp.net", "/path")

        for _ in range(5):
            state.increment_voice_retry("msg003")

        items = state.peek_voice_queue(limit=5, max_retries=5)
        assert len(items) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_state.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement state.py**

```python
# daemon/whatsapp_sync/state.py
"""Persistent sync state — watermarks, voice queue, gap flags."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SyncState:
    """Persistent state for the sync daemon."""

    watermarks: Dict[str, int] = field(default_factory=dict)
    voice_queue: List[Dict] = field(default_factory=list)
    suspected_gaps: List[Dict] = field(default_factory=list)
    contact_cache: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        """Load state from JSON file, or return empty state if missing."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                watermarks=data.get("watermarks", {}),
                voice_queue=data.get("voice_queue", []),
                suspected_gaps=data.get("suspected_gaps", []),
                contact_cache=data.get("contact_cache", {}),
            )
        except (json.JSONDecodeError, KeyError):
            return cls()

    def save(self, path: Path) -> None:
        """Atomically save state to JSON file."""
        tmp_path = path.with_suffix(".json.tmp")
        data = {
            "watermarks": self.watermarks,
            "voice_queue": self.voice_queue,
            "suspected_gaps": self.suspected_gaps,
            "contact_cache": self.contact_cache,
        }
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.rename(path)

    def advance_watermark(self, chat_jid: str, timestamp: int) -> None:
        """Advance watermark forward only — never backward."""
        current = self.watermarks.get(chat_jid, 0)
        if timestamp > current:
            self.watermarks[chat_jid] = timestamp

    def enqueue_voice(self, message_id: str, chat_jid: str, media_path: str) -> None:
        """Add a voice message to the transcription queue."""
        # Don't enqueue duplicates
        if any(item["message_id"] == message_id for item in self.voice_queue):
            return
        self.voice_queue.append({
            "message_id": message_id,
            "chat_jid": chat_jid,
            "media_path": media_path,
            "retries": 0,
        })

    def peek_voice_queue(self, limit: int = 5, max_retries: int = 5) -> List[Dict]:
        """Return up to `limit` items with retries below max."""
        return [
            item for item in self.voice_queue
            if item["retries"] < max_retries
        ][:limit]

    def acknowledge_voice(self, message_id: str) -> None:
        """Remove a successfully transcribed item from the queue."""
        self.voice_queue = [
            item for item in self.voice_queue
            if item["message_id"] != message_id
        ]

    def increment_voice_retry(self, message_id: str) -> None:
        """Increment retry count for a failed transcription."""
        for item in self.voice_queue:
            if item["message_id"] == message_id:
                item["retries"] += 1
                break
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_state.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/state.py daemon/tests/test_state.py
git commit -m "feat: add SyncState — persistent watermarks, voice queue, gaps

Atomic JSON save/load. Forward-only watermarks. Voice transcription
queue with retry counts and max-retry exclusion."
```

---

### Task 6: vault_writer — atomic transcript writes

**Files:**
- Create: `daemon/whatsapp_sync/vault_writer.py`
- Create: `daemon/tests/test_vault_writer.py`

This task covers the core safety guarantee: append-only, atomic, validated writes. This is the most critical module — if it's wrong, data is lost.

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_vault_writer.py
"""Tests for vault_writer — atomic transcript file operations."""

import pytest

from whatsapp_sync.vault_writer import VaultWriter


@pytest.mark.unit
class TestVaultWriter:

    def test_create_new_transcript(self, tmp_vault):
        """Creates transcript.md for a new chat."""
        writer = VaultWriter(tmp_vault / "People" / "Correspondence" / "Whatsapp")
        content = "---\ncssclasses:\n  - whatsapp-transcript\n---\n\n## 2026-04-19\n\n[14:30] Tim: Hey\n"

        writer.write_transcript("Tim Cocking", content)

        path = tmp_vault / "People" / "Correspondence" / "Whatsapp" / "Tim Cocking" / "transcript.md"
        assert path.exists()
        assert path.read_text() == content

    def test_append_to_existing_transcript(self, tmp_vault):
        """Appends new content to existing transcript.md."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        contact_dir = wa_dir / "Tim Cocking"
        contact_dir.mkdir(parents=True)
        transcript = contact_dir / "transcript.md"
        transcript.write_text("existing content\n")

        writer = VaultWriter(wa_dir)
        writer.append_transcript("Tim Cocking", "\n## 2026-04-19\n\n[14:30] Tim: New message\n")

        result = transcript.read_text()
        assert "existing content" in result
        assert "[14:30] Tim: New message" in result

    def test_append_preserves_existing_content(self, tmp_vault):
        """Atomic write validates existing content is preserved."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        contact_dir = wa_dir / "Tim Cocking"
        contact_dir.mkdir(parents=True)
        transcript = contact_dir / "transcript.md"
        original = "line 1\nline 2\nline 3\n"
        transcript.write_text(original)

        writer = VaultWriter(wa_dir)
        writer.append_transcript("Tim Cocking", "line 4\n")

        result = transcript.read_text()
        assert result.startswith(original)

    def test_write_index(self, tmp_vault):
        """Creates or overwrites index.md."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        writer = VaultWriter(wa_dir)

        writer.write_index("Tim Cocking", "---\ntype: note\n---\n")

        path = wa_dir / "Tim Cocking" / "index.md"
        assert path.exists()
        assert "type: note" in path.read_text()

    def test_creates_contact_directory(self, tmp_vault):
        """Auto-creates contact directory if it doesn't exist."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        writer = VaultWriter(wa_dir)

        writer.write_transcript("New Contact", "content\n")

        assert (wa_dir / "New Contact").is_dir()

    def test_tmp_file_cleaned_up(self, tmp_vault):
        """No .tmp file remains after successful write."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        writer = VaultWriter(wa_dir)

        writer.write_transcript("Tim Cocking", "content\n")

        tmp_file = wa_dir / "Tim Cocking" / "transcript.md.tmp"
        assert not tmp_file.exists()

    def test_get_existing_message_ids(self, tmp_vault):
        """Extracts message IDs from an existing transcript (if embedded)."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        writer = VaultWriter(wa_dir)

        # For now, returns empty — ID extraction from formatted text
        # uses content hash fallback (tested in dedup module)
        ids = writer.get_existing_message_ids("Tim Cocking")
        assert ids == set()

    def test_get_transcript_tail_hashes(self, tmp_vault):
        """Computes content hashes from the tail of an existing transcript."""
        wa_dir = tmp_vault / "People" / "Correspondence" / "Whatsapp"
        contact_dir = wa_dir / "Tim Cocking"
        contact_dir.mkdir(parents=True)
        transcript = contact_dir / "transcript.md"
        transcript.write_text(
            "## 2026-04-19\n\n"
            "[14:30] Tim Cocking: Hey mate\n"
            "[14:31] AJ Anderson: How's it going?\n"
        )

        writer = VaultWriter(wa_dir)
        hashes = writer.get_transcript_tail_hashes("Tim Cocking", tail_lines=50)

        assert len(hashes) > 0
        assert isinstance(hashes, set)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_vault_writer.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement vault_writer.py**

```python
# daemon/whatsapp_sync/vault_writer.py
"""Atomic, append-only file operations for the Obsidian vault."""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Set


class VaultWriter:
    """Writes transcript.md and index.md files with atomic safety."""

    def __init__(self, whatsapp_dir: Path):
        """
        Args:
            whatsapp_dir: Path to People/Correspondence/Whatsapp/ in the vault.
        """
        self.whatsapp_dir = Path(whatsapp_dir)

    def _contact_dir(self, contact_name: str) -> Path:
        d = self.whatsapp_dir / contact_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_transcript(self, contact_name: str, content: str) -> None:
        """Write a new transcript.md (for initial creation / full rewrite)."""
        contact_dir = self._contact_dir(contact_name)
        self._atomic_write(contact_dir / "transcript.md", content)

    def append_transcript(self, contact_name: str, new_content: str) -> None:
        """Append content to an existing transcript.md."""
        contact_dir = self._contact_dir(contact_name)
        transcript_path = contact_dir / "transcript.md"

        if not transcript_path.exists():
            self._atomic_write(transcript_path, new_content)
            return

        existing = transcript_path.read_text(encoding="utf-8")
        combined = existing + new_content

        # Validate: existing content is preserved
        if not combined.startswith(existing):
            raise RuntimeError(
                f"Append validation failed for {contact_name}: "
                f"existing content would be modified"
            )

        self._atomic_write(transcript_path, combined)

    def write_index(self, contact_name: str, content: str) -> None:
        """Write or overwrite index.md."""
        contact_dir = self._contact_dir(contact_name)
        self._atomic_write(contact_dir / "index.md", content)

    def get_existing_message_ids(self, contact_name: str) -> Set[str]:
        """
        Extract message IDs from an existing transcript.

        The spec format doesn't embed message IDs in the transcript text,
        so this returns an empty set. Dedup uses content hashes instead.
        """
        return set()

    def get_transcript_tail_hashes(
        self, contact_name: str, tail_lines: int = 50
    ) -> Set[str]:
        """
        Compute content hashes from the tail of an existing transcript.

        Used for dedup against incoming messages. Parses the last N lines
        of transcript.md and computes sha256(timestamp_minute + sender + content[:100]).
        """
        transcript_path = self.whatsapp_dir / contact_name / "transcript.md"
        if not transcript_path.exists():
            return set()

        lines = transcript_path.read_text(encoding="utf-8").splitlines()
        tail = lines[-tail_lines:] if len(lines) > tail_lines else lines

        hashes = set()
        # Match: [HH:MM] Sender: content
        pattern = re.compile(r"^\[(\d{2}:\d{2})\] ([^:]+): (.*)$")
        current_date = None

        # Scan backward for the date context
        for line in reversed(lines):
            if line.startswith("## "):
                current_date = line[3:].strip()
                break

        for line in tail:
            if line.startswith("## "):
                current_date = line[3:].strip()
                continue

            match = pattern.match(line)
            if match and current_date:
                time_str, sender, content = match.groups()
                try:
                    dt = datetime.strptime(
                        f"{current_date} {time_str}", "%Y-%m-%d %H:%M"
                    )
                    ts_minute = int(dt.timestamp()) - (int(dt.timestamp()) % 60)
                    raw = f"{ts_minute}:{sender}:{content[:100]}"
                    hashes.add(hashlib.sha256(raw.encode("utf-8")).hexdigest())
                except ValueError:
                    continue

        return hashes

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write to .tmp then rename for atomicity."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.rename(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_vault_writer.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/vault_writer.py daemon/tests/test_vault_writer.py
git commit -m "feat: add VaultWriter — atomic, append-only transcript writes

Creates contact directories, writes transcript.md and index.md atomically
via .tmp + rename. Validates existing content preserved on append.
Extracts content hashes from transcript tail for dedup."
```

---

### Task 7: health — Kuma push client

**Files:**
- Create: `daemon/whatsapp_sync/health.py`
- Create: `daemon/tests/test_health.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_health.py
"""Tests for health — Kuma push client."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from whatsapp_sync.health import KumaClient


@pytest.mark.unit
class TestKumaClient:

    def test_push_up(self):
        """Sends status=up with message and ping."""
        client = KumaClient(
            sync_loop_url="http://kuma:3001/api/push/abc",
            transcription_url="http://kuma:3001/api/push/def",
            gap_detector_url="http://kuma:3001/api/push/ghi",
        )

        with patch("whatsapp_sync.health.httpx") as mock_httpx:
            mock_httpx.get.return_value = MagicMock(status_code=200)
            client.push_sync_loop(status="up", msg="synced 3 chats", ping_ms=1200)

            mock_httpx.get.assert_called_once()
            call_args = mock_httpx.get.call_args
            assert "status=up" in str(call_args)

    def test_push_down(self):
        """Sends status=down."""
        client = KumaClient(
            sync_loop_url="http://kuma:3001/api/push/abc",
        )

        with patch("whatsapp_sync.health.httpx") as mock_httpx:
            mock_httpx.get.return_value = MagicMock(status_code=200)
            client.push_sync_loop(status="down", msg="SQLite unreachable")

            call_args = mock_httpx.get.call_args
            assert "status=down" in str(call_args)

    def test_push_failure_does_not_raise(self):
        """Network failure is logged, not raised."""
        client = KumaClient(
            sync_loop_url="http://kuma:3001/api/push/abc",
        )

        with patch("whatsapp_sync.health.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("connection refused")
            # Should not raise
            client.push_sync_loop(status="up", msg="test")

    def test_disabled_when_no_url(self):
        """No URL configured → push is a no-op."""
        client = KumaClient()

        with patch("whatsapp_sync.health.httpx") as mock_httpx:
            client.push_sync_loop(status="up", msg="test")
            mock_httpx.get.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_health.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement health.py**

```python
# daemon/whatsapp_sync/health.py
"""Kuma push monitor client — 4 independent health signals."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class KumaClient:
    """Pushes heartbeats to Uptime Kuma push monitors."""

    def __init__(
        self,
        sync_loop_url: str = "",
        transcription_url: str = "",
        gap_detector_url: str = "",
    ):
        self.sync_loop_url = sync_loop_url
        self.transcription_url = transcription_url
        self.gap_detector_url = gap_detector_url

    def _push(self, url: str, status: str, msg: str, ping_ms: int = 0) -> None:
        """Send a push to a Kuma monitor. Never raises."""
        if not url:
            return
        try:
            httpx.get(
                url,
                params={
                    "status": status,
                    "msg": msg[:200],
                    "ping": str(ping_ms),
                },
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"Kuma push failed ({url}): {e}")

    def push_sync_loop(self, status: str, msg: str, ping_ms: int = 0) -> None:
        """Push sync_loop monitor heartbeat."""
        self._push(self.sync_loop_url, status, msg, ping_ms)

    def push_transcription(self, status: str, msg: str, ping_ms: int = 0) -> None:
        """Push transcription monitor heartbeat."""
        self._push(self.transcription_url, status, msg, ping_ms)

    def push_gap_detector(self, status: str, msg: str, ping_ms: int = 0) -> None:
        """Push gap_detector monitor heartbeat."""
        self._push(self.gap_detector_url, status, msg, ping_ms)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_health.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/health.py daemon/tests/test_health.py
git commit -m "feat: add KumaClient — push heartbeats for 3 Python monitors

sync_loop, transcription, gap_detector. Follows Ryanair Fares pattern:
httpx.get with status/msg/ping params. Failures logged, never raised."
```

---

### Task 8: gap_detector — connection gap analysis

**Files:**
- Create: `daemon/whatsapp_sync/gap_detector.py`
- Create: `daemon/tests/test_gap_detector.py`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_gap_detector.py
"""Tests for gap_detector — connection gap analysis."""

import sqlite3
import time

import pytest

from whatsapp_sync.gap_detector import GapDetector, GapStatus


@pytest.mark.unit
class TestGapDetector:

    def _insert_connection_events(self, db_path, events):
        """Helper: insert connection_log events."""
        conn = sqlite3.connect(db_path)
        for event, ts, detail in events:
            conn.execute(
                "INSERT INTO connection_log (event, timestamp, detail) VALUES (?, ?, ?)",
                (event, ts, detail),
            )
        conn.commit()
        conn.close()

    def test_no_events_returns_unknown(self, tmp_db):
        """Empty connection log → UNKNOWN status."""
        detector = GapDetector(tmp_db)
        status = detector.check()
        assert status.level == "unknown"

    def test_recently_connected_is_ok(self, tmp_db):
        """Connected within threshold → OK."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 60, "normal"),
        ])

        detector = GapDetector(tmp_db)
        status = detector.check()
        assert status.level == "ok"

    def test_disconnected_3_days_is_warning(self, tmp_db):
        """Disconnected 3+ days → WARNING."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 86400 * 5, "initial"),
            ("disconnected", now - 86400 * 4, "lost connection"),
        ])

        detector = GapDetector(tmp_db, warning_days=3, alarm_days=7, critical_days=14)
        status = detector.check()
        assert status.level == "warning"

    def test_disconnected_8_days_is_alarm(self, tmp_db):
        """Disconnected 8 days → ALARM (Kuma DOWN)."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 86400 * 10, "initial"),
            ("disconnected", now - 86400 * 9, "lost connection"),
        ])

        detector = GapDetector(tmp_db, warning_days=3, alarm_days=7, critical_days=14)
        status = detector.check()
        assert status.level == "alarm"

    def test_disconnected_15_days_is_critical(self, tmp_db):
        """Disconnected 15 days → CRITICAL (reseed required)."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 86400 * 20, "initial"),
            ("disconnected", now - 86400 * 16, "lost connection"),
        ])

        detector = GapDetector(tmp_db, warning_days=3, alarm_days=7, critical_days=14)
        status = detector.check()
        assert status.level == "critical"

    def test_reconnected_resets_to_ok(self, tmp_db):
        """Disconnect then reconnect → OK."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 86400 * 10, "initial"),
            ("disconnected", now - 86400 * 5, "lost"),
            ("connected", now - 60, "reconnected"),
        ])

        detector = GapDetector(tmp_db)
        status = detector.check()
        assert status.level == "ok"

    def test_status_message(self, tmp_db):
        """Status includes human-readable message."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 60, "normal"),
        ])

        detector = GapDetector(tmp_db)
        status = detector.check()
        assert isinstance(status.message, str)
        assert len(status.message) > 0

    def test_kuma_status_mapping(self, tmp_db):
        """Level maps to Kuma status correctly."""
        now = int(time.time())
        self._insert_connection_events(tmp_db, [
            ("connected", now - 60, "normal"),
        ])

        detector = GapDetector(tmp_db)
        status = detector.check()
        assert status.kuma_status == "up"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_gap_detector.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement gap_detector.py**

```python
# daemon/whatsapp_sync/gap_detector.py
"""Analyzes bridge connection gaps to detect data loss risk."""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GapStatus:
    """Result of gap analysis."""

    level: str  # "ok", "warning", "alarm", "critical", "unknown"
    message: str
    disconnected_seconds: int = 0

    @property
    def kuma_status(self) -> str:
        """Map level to Kuma push status."""
        if self.level in ("alarm", "critical"):
            return "down"
        return "up"


class GapDetector:
    """Reads connection_log to detect dangerous gaps."""

    def __init__(
        self,
        db_path: Path,
        warning_days: int = 3,
        alarm_days: int = 7,
        critical_days: int = 14,
    ):
        self.db_path = Path(db_path)
        self.warning_seconds = warning_days * 86400
        self.alarm_seconds = alarm_days * 86400
        self.critical_seconds = critical_days * 86400

    def check(self) -> GapStatus:
        """Analyze connection log and return current gap status."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT event, timestamp FROM connection_log ORDER BY timestamp ASC"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return GapStatus(level="unknown", message="No connection events recorded")

        # Find the most recent event
        last_event = rows[-1]
        now = int(time.time())

        if last_event["event"] == "connected":
            seconds_since = now - last_event["timestamp"]
            return GapStatus(
                level="ok",
                message=f"Connected {seconds_since // 3600}h ago",
                disconnected_seconds=0,
            )

        # Last event is "disconnected" — compute gap duration
        disconnected_at = last_event["timestamp"]
        gap = now - disconnected_at

        if gap >= self.critical_seconds:
            days = gap // 86400
            return GapStatus(
                level="critical",
                message=f"CRITICAL: bridge down {days}d, history sync window expired, reseed REQUIRED",
                disconnected_seconds=gap,
            )
        elif gap >= self.alarm_seconds:
            days = gap // 86400
            return GapStatus(
                level="alarm",
                message=f"ALARM: bridge down {days}d, reseed recommended",
                disconnected_seconds=gap,
            )
        elif gap >= self.warning_seconds:
            days = gap // 86400
            return GapStatus(
                level="warning",
                message=f"WARNING: bridge down {days}d, reseed window closing",
                disconnected_seconds=gap,
            )
        else:
            hours = gap // 3600
            return GapStatus(
                level="ok",
                message=f"Bridge disconnected {hours}h ago (within threshold)",
                disconnected_seconds=gap,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_gap_detector.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/gap_detector.py daemon/tests/test_gap_detector.py
git commit -m "feat: add GapDetector — connection gap analysis

Reads connection_log from SQLite. Thresholds: 3d warning, 7d alarm (Kuma
DOWN), 14d critical (reseed required). Reconnection resets to OK."
```

---

### Task 9: config — YAML configuration

**Files:**
- Create: `daemon/whatsapp_sync/config.py`
- Create: `daemon/tests/test_config.py`
- Create: `config.yaml.example`

- [ ] **Step 1: Write the failing tests**

```python
# daemon/tests/test_config.py
"""Tests for config — YAML configuration loader."""

import pytest

from whatsapp_sync.config import SyncConfig


@pytest.mark.unit
class TestSyncConfig:

    def test_load_from_yaml(self, tmp_path):
        """Loads config from a YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
sqlite_path: /data/messages.db
voice_dir: /data/voice/
journal_path: /home/aj/Journal
output_path: People/Correspondence/Whatsapp
state_path: /home/aj/state.json
poll_interval_seconds: 120
voice_drain_per_cycle: 10
owner_name: AJ Anderson
git_author: "whatsapp_sync <whatsapp_sync@pi5>"

kuma:
  sync_loop: http://kuma:3001/api/push/abc
  transcription: http://kuma:3001/api/push/def
  gap_detector: http://kuma:3001/api/push/ghi

thresholds:
  gap_warning_days: 3
  gap_alarm_days: 7
  gap_critical_days: 14
  voice_max_retries: 5
""")

        config = SyncConfig.from_yaml(config_file)

        assert config.sqlite_path == "/data/messages.db"
        assert config.poll_interval_seconds == 120
        assert config.voice_drain_per_cycle == 10
        assert config.kuma_sync_loop_url == "http://kuma:3001/api/push/abc"
        assert config.gap_alarm_days == 7

    def test_defaults(self):
        """Default values are sensible."""
        config = SyncConfig()

        assert config.poll_interval_seconds == 60
        assert config.voice_drain_per_cycle == 5
        assert config.owner_name == "AJ Anderson"
        assert config.gap_warning_days == 3
        assert config.gap_alarm_days == 7
        assert config.gap_critical_days == 14
        assert config.voice_max_retries == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_config.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement config.py**

```python
# daemon/whatsapp_sync/config.py
"""YAML configuration for the sync daemon."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SyncConfig:
    """Configuration for the WhatsApp sync daemon."""

    # Paths
    sqlite_path: str = ""
    voice_dir: str = ""
    journal_path: str = ""
    output_path: str = "People/Correspondence/Whatsapp"
    state_path: str = ""

    # Timing
    poll_interval_seconds: int = 60
    voice_drain_per_cycle: int = 5
    overlap_seconds: int = 600  # 10 min overlap window

    # Identity
    owner_name: str = "AJ Anderson"
    git_author: str = "whatsapp_sync <whatsapp_sync@pi5>"

    # Kuma URLs
    kuma_sync_loop_url: str = ""
    kuma_transcription_url: str = ""
    kuma_gap_detector_url: str = ""

    # Thresholds
    gap_warning_days: int = 3
    gap_alarm_days: int = 7
    gap_critical_days: int = 14
    voice_max_retries: int = 5

    # ElevenLabs
    elevenlabs_api_key_env: str = "ELEVENLABS_API_KEY"

    @classmethod
    def from_yaml(cls, path: Path) -> "SyncConfig":
        """Load config from a YAML file."""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

        kuma = data.get("kuma", {})
        thresholds = data.get("thresholds", {})

        return cls(
            sqlite_path=data.get("sqlite_path", ""),
            voice_dir=data.get("voice_dir", ""),
            journal_path=data.get("journal_path", ""),
            output_path=data.get("output_path", "People/Correspondence/Whatsapp"),
            state_path=data.get("state_path", ""),
            poll_interval_seconds=data.get("poll_interval_seconds", 60),
            voice_drain_per_cycle=data.get("voice_drain_per_cycle", 5),
            overlap_seconds=data.get("overlap_seconds", 600),
            owner_name=data.get("owner_name", "AJ Anderson"),
            git_author=data.get("git_author", "whatsapp_sync <whatsapp_sync@pi5>"),
            kuma_sync_loop_url=kuma.get("sync_loop", ""),
            kuma_transcription_url=kuma.get("transcription", ""),
            kuma_gap_detector_url=kuma.get("gap_detector", ""),
            gap_warning_days=thresholds.get("gap_warning_days", 3),
            gap_alarm_days=thresholds.get("gap_alarm_days", 7),
            gap_critical_days=thresholds.get("gap_critical_days", 14),
            voice_max_retries=thresholds.get("voice_max_retries", 5),
            elevenlabs_api_key_env=data.get("elevenlabs_api_key_env", "ELEVENLABS_API_KEY"),
        )

    @property
    def whatsapp_dir(self) -> Path:
        """Full path to WhatsApp correspondence directory in the vault."""
        return Path(self.journal_path) / self.output_path
```

- [ ] **Step 4: Create config.yaml.example**

```yaml
# config.yaml.example — WhatsApp Sync Daemon configuration
sqlite_path: /home/ajanderson/whatsapp_sync/data/messages.db
voice_dir: /home/ajanderson/whatsapp_sync/data/voice/
journal_path: /home/ajanderson/Journal
output_path: People/Correspondence/Whatsapp
state_path: /home/ajanderson/whatsapp_sync/state.json
poll_interval_seconds: 60
voice_drain_per_cycle: 5
owner_name: AJ Anderson
git_author: "whatsapp_sync <whatsapp_sync@pi5>"

kuma:
  sync_loop: http://localhost:3001/api/push/REPLACE_ME
  transcription: http://localhost:3001/api/push/REPLACE_ME
  gap_detector: http://localhost:3001/api/push/REPLACE_ME

thresholds:
  gap_warning_days: 3
  gap_alarm_days: 7
  gap_critical_days: 14
  voice_max_retries: 5
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_config.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/config.py daemon/tests/test_config.py config.yaml.example
git commit -m "feat: add SyncConfig — YAML configuration loader

Loads all daemon config from a single YAML file. Sensible defaults for
intervals, thresholds, Kuma URLs. Example config included."
```

---

### Task 10: daemon — main sync loop

**Files:**
- Create: `daemon/whatsapp_sync/daemon.py`
- Create: `daemon/tests/test_daemon.py`

This is the orchestrator that ties everything together. One poll cycle = preflight + sync + voice drain + git commit + save state.

- [ ] **Step 1: Write the failing test — single cycle**

```python
# daemon/tests/test_daemon.py
"""Tests for daemon — main sync loop."""

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from whatsapp_sync.config import SyncConfig
from whatsapp_sync.daemon import SyncDaemon


@pytest.mark.unit
class TestSyncDaemon:

    def _make_config(self, tmp_path, db_path):
        """Create a SyncConfig pointing at temp paths."""
        vault = tmp_path / "Journal"
        wa_dir = vault / "People" / "Correspondence" / "Whatsapp"
        wa_dir.mkdir(parents=True)

        return SyncConfig(
            sqlite_path=str(db_path),
            voice_dir=str(tmp_path / "voice"),
            journal_path=str(vault),
            state_path=str(tmp_path / "state.json"),
            poll_interval_seconds=60,
            owner_name="AJ Anderson",
        )

    def test_single_cycle_creates_transcript(self, tmp_path, sample_messages_in_db):
        """One sync cycle creates transcript.md for a chat with new messages."""
        config = self._make_config(tmp_path, sample_messages_in_db)

        daemon = SyncDaemon(config)
        summary = daemon.run_cycle()

        transcript = (
            Path(config.journal_path) / config.output_path
            / "Tim Cocking" / "transcript.md"
        )
        assert transcript.exists()
        assert "## 2026-04-19" in transcript.read_text()
        assert summary["chats_synced"] >= 1

    def test_single_cycle_creates_index(self, tmp_path, sample_messages_in_db):
        """One sync cycle creates index.md alongside transcript."""
        config = self._make_config(tmp_path, sample_messages_in_db)

        daemon = SyncDaemon(config)
        daemon.run_cycle()

        index = (
            Path(config.journal_path) / config.output_path
            / "Tim Cocking" / "index.md"
        )
        assert index.exists()
        assert "type: note" in index.read_text()

    def test_second_cycle_is_idempotent(self, tmp_path, sample_messages_in_db):
        """Running twice without new messages produces no changes."""
        config = self._make_config(tmp_path, sample_messages_in_db)

        daemon = SyncDaemon(config)
        daemon.run_cycle()
        summary2 = daemon.run_cycle()

        assert summary2["chats_synced"] == 0

    def test_cycle_advances_watermark(self, tmp_path, sample_messages_in_db):
        """After sync, watermark is advanced in state."""
        config = self._make_config(tmp_path, sample_messages_in_db)

        daemon = SyncDaemon(config)
        daemon.run_cycle()

        from whatsapp_sync.state import SyncState
        state = SyncState.load(Path(config.state_path))
        assert "447956173473@s.whatsapp.net" in state.watermarks

    def test_voice_message_queued(self, tmp_path, sample_messages_in_db):
        """Voice messages are added to the transcription queue."""
        config = self._make_config(tmp_path, sample_messages_in_db)

        daemon = SyncDaemon(config)
        daemon.run_cycle()

        from whatsapp_sync.state import SyncState
        state = SyncState.load(Path(config.state_path))
        # msg003 is an audio message
        voice_ids = [item["message_id"] for item in state.voice_queue]
        assert "msg003" in voice_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_daemon.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement daemon.py**

```python
# daemon/whatsapp_sync/daemon.py
"""Main sync daemon — poll loop orchestrator."""

import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from .bridge_reader import BridgeReader
from .config import SyncConfig
from .dedup import deduplicate
from .formatter import format_transcript_file, format_index, format_messages
from .gap_detector import GapDetector
from .health import KumaClient
from .state import SyncState
from .vault_writer import VaultWriter

logger = logging.getLogger(__name__)


class SyncDaemon:
    """Orchestrates the sync loop: poll → format → write → commit."""

    def __init__(self, config: SyncConfig):
        self.config = config
        self.reader = BridgeReader(Path(config.sqlite_path))
        self.writer = VaultWriter(config.whatsapp_dir)
        self.gap_detector = GapDetector(
            Path(config.sqlite_path),
            warning_days=config.gap_warning_days,
            alarm_days=config.gap_alarm_days,
            critical_days=config.gap_critical_days,
        )
        self.kuma = KumaClient(
            sync_loop_url=config.kuma_sync_loop_url,
            transcription_url=config.kuma_transcription_url,
            gap_detector_url=config.kuma_gap_detector_url,
        )
        self._running = True

    def run_cycle(self) -> Dict:
        """
        Execute one sync cycle.

        Returns:
            Summary dict: chats_synced, chats_skipped, messages_added,
            voice_queued, errors.
        """
        start = time.time()
        state = SyncState.load(Path(self.config.state_path))

        summary = {
            "chats_synced": 0,
            "chats_skipped": 0,
            "messages_added": 0,
            "voice_queued": 0,
            "errors": [],
        }

        try:
            # 1. Preflight — gap detection
            gap_status = self.gap_detector.check()
            self.kuma.push_gap_detector(
                status=gap_status.kuma_status,
                msg=gap_status.message,
            )

            # 2. Find changed chats
            changed = self.reader.get_changed_chats(state.watermarks)

            if not changed:
                summary["chats_skipped"] = len(self.reader.get_chats())
                elapsed = int((time.time() - start) * 1000)
                self.kuma.push_sync_loop(
                    status="up",
                    msg=f"no changes, {summary['chats_skipped']} chats unchanged",
                    ping_ms=elapsed,
                )
                state.save(Path(self.config.state_path))
                return summary

            # 3. Sync each changed chat
            for chat in changed:
                try:
                    result = self._sync_chat(chat, state)
                    summary["chats_synced"] += 1
                    summary["messages_added"] += result["messages_added"]
                    summary["voice_queued"] += result["voice_queued"]
                except Exception as e:
                    logger.error(f"Failed to sync {chat['name']}: {e}")
                    summary["errors"].append(
                        {"chat": chat["name"], "error": str(e)}
                    )

            # 4. Save state
            state.save(Path(self.config.state_path))

            # 5. Kuma heartbeat
            elapsed = int((time.time() - start) * 1000)
            status = "up" if not summary["errors"] else "up"
            msg = (
                f"synced {summary['chats_synced']} chats, "
                f"{summary['messages_added']} msgs, "
                f"{summary['voice_queued']} voice queued"
            )
            if summary["errors"]:
                msg += f", {len(summary['errors'])} errors"
            self.kuma.push_sync_loop(status=status, msg=msg, ping_ms=elapsed)

        except Exception as e:
            logger.error(f"Sync cycle failed: {e}")
            summary["errors"].append({"chat": "_cycle", "error": str(e)})
            self.kuma.push_sync_loop(status="down", msg=str(e)[:200])

        return summary

    def _sync_chat(self, chat: Dict, state: SyncState) -> Dict:
        """Sync a single chat. Returns {messages_added, voice_queued}."""
        jid = chat["jid"]
        name = chat["name"] or jid
        is_group = chat["is_group"]
        watermark = state.watermarks.get(jid, 0)

        # Fetch messages with overlap
        messages = self.reader.get_messages(
            jid,
            after=watermark if watermark > 0 else None,
            overlap_seconds=self.config.overlap_seconds,
        )

        if not messages:
            return {"messages_added": 0, "voice_queued": 0}

        # Dedup
        existing_ids = self.writer.get_existing_message_ids(name)
        existing_hashes = self.writer.get_transcript_tail_hashes(name)
        new_messages = deduplicate(messages, existing_ids, existing_hashes)

        if not new_messages:
            # Advance watermark even if all dupes (messages were processed)
            state.advance_watermark(jid, messages[-1].timestamp)
            return {"messages_added": 0, "voice_queued": 0}

        # Check if this is a new chat (no existing transcript)
        transcript_path = self.config.whatsapp_dir / name / "transcript.md"
        is_new_chat = not transcript_path.exists()

        # Format
        if is_new_chat:
            # Full transcript for new chats
            content = format_transcript_file(
                new_messages,
                contact_name=name,
                chat_jid=jid,
                owner_name=self.config.owner_name,
            )
            self.writer.write_transcript(name, content)
        else:
            # Append for existing chats
            body = format_messages(
                new_messages,
                owner_name=self.config.owner_name,
            )
            self.writer.append_transcript(name, body)

        # Write/update index.md
        # For updates, we need all messages to compute accurate stats
        # Use the count from the existing transcript + new messages
        all_messages = messages  # close enough for stats
        chat_type = "group" if is_group else "direct"
        index_content = format_index(
            all_messages,
            contact_name=name,
            chat_jid=jid,
            chat_type=chat_type,
        )
        self.writer.write_index(name, index_content)

        # Queue voice messages for transcription
        voice_queued = 0
        for msg in new_messages:
            if msg.media_type == "audio" and msg.media_path:
                state.enqueue_voice(msg.id, jid, msg.media_path)
                voice_queued += 1

        # Advance watermark
        state.advance_watermark(jid, new_messages[-1].timestamp)

        return {"messages_added": len(new_messages), "voice_queued": voice_queued}

    def run_loop(self) -> None:
        """Run the poll loop indefinitely."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info(f"Starting sync loop (interval: {self.config.poll_interval_seconds}s)")

        while self._running:
            try:
                summary = self.run_cycle()
                logger.info(
                    f"Cycle complete: {summary['chats_synced']} synced, "
                    f"{summary['messages_added']} msgs"
                )
            except Exception as e:
                logger.error(f"Unexpected error in sync loop: {e}")

            if self._running:
                time.sleep(self.config.poll_interval_seconds)

        logger.info("Sync loop stopped")

    def _git_commit(self, message: str) -> None:
        """Commit changes to the journal repo."""
        journal = Path(self.config.journal_path)
        wa_path = self.config.output_path

        try:
            subprocess.run(
                ["git", "-C", str(journal), "add", wa_path],
                check=True, capture_output=True,
            )

            # Check if there are staged changes
            result = subprocess.run(
                ["git", "-C", str(journal), "diff", "--cached", "--quiet"],
                capture_output=True,
            )
            if result.returncode == 0:
                return  # Nothing staged

            subprocess.run(
                [
                    "git", "-C", str(journal), "commit",
                    f"--author={self.config.git_author}",
                    "-m", message,
                ],
                check=True, capture_output=True,
            )

            subprocess.run(
                ["git", "-C", str(journal), "push"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")

    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False


def main():
    """Entry point for the whatsapp-sync command."""
    import argparse

    parser = argparse.ArgumentParser(description="WhatsApp Sync Daemon")
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = SyncConfig.from_yaml(Path(args.config))
    daemon = SyncDaemon(config)

    if args.once:
        summary = daemon.run_cycle()
        print(summary)
    else:
        daemon.run_loop()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest tests/test_daemon.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/ajanderson/GitHub/projects/whatsapp_sync/daemon && poetry run pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add daemon/whatsapp_sync/daemon.py daemon/tests/test_daemon.py
git commit -m "feat: add SyncDaemon — main poll loop orchestrator

Ties all modules together: preflight gap check → find changed chats →
per-chat sync (fetch, dedup, format, atomic write) → voice queue →
git commit → Kuma heartbeat. Supports --once for single cycle."
```

---

## Phase 3: Go Bridge (skeleton)

### Task 11: Go bridge scaffold

**Files:**
- Create: `bridge/go.mod`
- Create: `bridge/main.go`
- Create: `bridge/db.go`
- Create: `bridge/health.go`
- Create: `bridge/kuma.go`

This task creates the Go bridge structure. Full whatsmeow integration requires a device for QR auth testing, so this task establishes the architecture with stubs that can be completed during Pi deployment.

- [ ] **Step 1: Initialize Go module**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync/bridge
go mod init github.com/ajanderson1/whatsapp-sync-bridge
go get go.mau.fi/whatsmeow@latest
go get github.com/mattn/go-sqlite3
```

- [ ] **Step 2: Create main.go**

```go
// bridge/main.go
package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	configPath := flag.String("config", "config.yaml", "Path to config file")
	flag.Parse()

	log.Printf("WhatsApp Bridge starting (config: %s)", *configPath)

	// TODO: Load config, init SQLite, connect whatsmeow, start health server

	// Wait for shutdown signal
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c

	log.Println("Shutting down...")
}
```

- [ ] **Step 3: Create db.go**

```go
// bridge/db.go
package main

import (
	"database/sql"
	"log"

	_ "github.com/mattn/go-sqlite3"
)

type DB struct {
	conn *sql.DB
}

func NewDB(path string) (*DB, error) {
	conn, err := sql.Open("sqlite3", path)
	if err != nil {
		return nil, err
	}

	// Create tables
	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS messages (
			id TEXT PRIMARY KEY,
			chat_jid TEXT NOT NULL,
			sender_jid TEXT NOT NULL,
			sender_name TEXT,
			content TEXT,
			timestamp INTEGER NOT NULL,
			is_from_me BOOLEAN NOT NULL,
			media_type TEXT,
			media_path TEXT,
			raw_proto BLOB
		);

		CREATE TABLE IF NOT EXISTS connection_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			event TEXT NOT NULL,
			timestamp INTEGER NOT NULL,
			detail TEXT
		);

		CREATE TABLE IF NOT EXISTS chats (
			jid TEXT PRIMARY KEY,
			name TEXT,
			is_group BOOLEAN NOT NULL,
			last_message_at INTEGER,
			participant_jids TEXT
		);
	`)
	if err != nil {
		return nil, err
	}

	log.Printf("Database initialized at %s", path)
	return &DB{conn: conn}, nil
}

func (db *DB) InsertMessage(id, chatJID, senderJID, senderName, content string,
	timestamp int64, isFromMe bool, mediaType, mediaPath string, rawProto []byte) error {

	_, err := db.conn.Exec(
		`INSERT OR IGNORE INTO messages
		(id, chat_jid, sender_jid, sender_name, content, timestamp, is_from_me, media_type, media_path, raw_proto)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		id, chatJID, senderJID, senderName, content, timestamp, isFromMe, mediaType, mediaPath, rawProto,
	)
	return err
}

func (db *DB) LogConnection(event string, timestamp int64, detail string) error {
	_, err := db.conn.Exec(
		"INSERT INTO connection_log (event, timestamp, detail) VALUES (?, ?, ?)",
		event, timestamp, detail,
	)
	return err
}

func (db *DB) UpsertChat(jid, name string, isGroup bool, lastMessageAt int64, participantJIDs string) error {
	_, err := db.conn.Exec(
		`INSERT INTO chats (jid, name, is_group, last_message_at, participant_jids)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT(jid) DO UPDATE SET
			name=excluded.name,
			last_message_at=MAX(last_message_at, excluded.last_message_at),
			participant_jids=excluded.participant_jids`,
		jid, name, isGroup, lastMessageAt, participantJIDs,
	)
	return err
}

func (db *DB) Close() error {
	return db.conn.Close()
}
```

- [ ] **Step 4: Create health.go**

```go
// bridge/health.go
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"time"
)

type HealthServer struct {
	connected       bool
	lastMessageAt   int64
	startedAt       time.Time
}

func NewHealthServer() *HealthServer {
	return &HealthServer{startedAt: time.Now()}
}

func (h *HealthServer) Start(addr string) {
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"connected":       h.connected,
			"last_message_at": h.lastMessageAt,
			"uptime_seconds":  int(time.Since(h.startedAt).Seconds()),
		})
	})

	go func() {
		log.Printf("Health server listening on %s", addr)
		if err := http.ListenAndServe(addr, nil); err != nil {
			log.Printf("Health server error: %v", err)
		}
	}()
}
```

- [ ] **Step 5: Create kuma.go**

```go
// bridge/kuma.go
package main

import (
	"fmt"
	"log"
	"net/http"
	"time"
)

type KumaClient struct {
	pushURL string
}

func NewKumaClient(pushURL string) *KumaClient {
	return &KumaClient{pushURL: pushURL}
}

func (k *KumaClient) Push(status, msg string, pingMs int) {
	if k.pushURL == "" {
		return
	}

	url := fmt.Sprintf("%s?status=%s&msg=%s&ping=%d", k.pushURL, status, msg, pingMs)
	client := &http.Client{Timeout: 5 * time.Second}

	resp, err := client.Get(url)
	if err != nil {
		log.Printf("Kuma push failed: %v", err)
		return
	}
	resp.Body.Close()
}

func (k *KumaClient) StartHeartbeat(interval time.Duration, healthServer *HealthServer) {
	go func() {
		for {
			status := "down"
			msg := "disconnected"
			if healthServer.connected {
				status = "up"
				msg = fmt.Sprintf("connected, last_msg=%d", healthServer.lastMessageAt)
			}
			k.Push(status, msg, 0)
			time.Sleep(interval)
		}
	}()
}
```

- [ ] **Step 6: Verify Go builds**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync/bridge
go build -o whatsapp-bridge .
```

Expected: Binary compiles successfully.

- [ ] **Step 7: Add bridge binary to .gitignore, commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
echo "bridge/whatsapp-bridge" >> .gitignore
git add bridge/ .gitignore
git commit -m "feat: add Go bridge scaffold — SQLite, health, Kuma

whatsmeow bridge structure with db.go (message/chat/connection_log tables),
health.go (/health JSON endpoint), kuma.go (push heartbeat). main.go
placeholder for whatsmeow integration."
```

---

## Phase 4: Systemd & Deployment Config

### Task 12: Systemd service files and deployment docs

**Files:**
- Create: `systemd/whatsapp-bridge.service`
- Create: `systemd/whatsapp-sync.service`
- Create: `.env.example`

- [ ] **Step 1: Create systemd unit files**

```ini
# systemd/whatsapp-bridge.service
[Unit]
Description=WhatsApp Bridge (whatsmeow)
After=network.target

[Service]
Type=simple
User=ajanderson
WorkingDirectory=/home/ajanderson/whatsapp_sync/bridge
ExecStart=/home/ajanderson/whatsapp_sync/bridge/whatsapp-bridge --config /home/ajanderson/whatsapp_sync/bridge/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# systemd/whatsapp-sync.service
[Unit]
Description=WhatsApp Sync Daemon
After=network.target whatsapp-bridge.service
Wants=whatsapp-bridge.service

[Service]
Type=simple
User=ajanderson
WorkingDirectory=/home/ajanderson/whatsapp_sync/daemon
ExecStart=/home/ajanderson/.cache/pypoetry/virtualenvs/whatsapp-sync-HASH-py3.13/bin/whatsapp-sync --config /home/ajanderson/whatsapp_sync/config.yaml
EnvironmentFile=/home/ajanderson/whatsapp_sync/.env
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create .env.example**

```bash
# .env.example — API keys for WhatsApp Sync Daemon
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

- [ ] **Step 3: Commit**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_sync
git add systemd/ .env.example
git commit -m "chore: add systemd service files and .env.example

Two systemd units: whatsapp-bridge (Go, RestartSec=10) and
whatsapp-sync (Python, After=bridge, RestartSec=30)."
```

---

## Deferred to Pi Deployment

The following tasks require the Pi 5 environment or a physical device and are deferred:

- **Go bridge whatsmeow integration** — Task 11 creates the scaffold; connecting to WhatsApp Web requires QR code scan on the Pi.
- **`transcriber.py`** — Extract ~200 lines from the exporter's `ElevenLabsTranscriber`. Wire into the voice queue drain loop in `daemon.py`. Requires `ELEVENLABS_API_KEY` for testing.
- **Voice queue drain in `daemon.py`** — The `run_cycle()` currently queues voice messages but doesn't drain. Add drain step between sync and git commit.
- **Git commit in `daemon.py`** — `_git_commit()` is implemented but not called from `run_cycle()`. Wire in after voice drain.
- **Kuma push monitor setup** — Create 4 push monitors on the Pi's Kuma instance (:3001).

---

## Post-Implementation Checklist

- [ ] `cd daemon && poetry run pytest -v` — all Python tests pass
- [ ] `cd daemon && poetry run pytest --cov=whatsapp_sync --cov-report=term-missing` — coverage >= 90%
- [ ] `cd bridge && go build -o whatsapp-bridge .` — Go compiles
- [ ] `poetry run whatsapp-sync --config config.yaml.example --once` — runs one cycle (will fail on missing DB, but validates CLI)
- [ ] Format compliance: daemon's `formatter.py` output matches exporter's `SpecFormatter` output for the same input messages
