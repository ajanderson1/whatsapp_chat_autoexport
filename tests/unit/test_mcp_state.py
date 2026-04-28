"""
Test suite for MCPState — incremental sync state management.

Tests serialisation round-trips, atomic writes, graceful corruption
handling, watermark management, contact cache, and voice retry queue.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.mcp.state import MCPState, VoiceRetryItem, STATE_VERSION


# =========================================================================
# Construction and defaults
# =========================================================================


@pytest.mark.unit
class TestMCPStateDefaults:
    """Test default construction of MCPState."""

    def test_default_construction(self):
        """Fresh state has sensible defaults."""
        state = MCPState()
        assert state.version == STATE_VERSION
        assert state.watermarks == {}
        assert state.contact_cache == {}
        assert state.voice_retry_queue == []
        assert state.last_sync is None


# =========================================================================
# Watermarks
# =========================================================================


@pytest.mark.unit
class TestWatermarks:
    """Tests for per-chat watermark management."""

    def test_set_and_get_watermark(self):
        """Watermark round-trips correctly."""
        state = MCPState()
        ts = datetime(2026, 3, 25, 10, 30, 0)
        state.set_watermark("alice@s.whatsapp.net", ts)
        assert state.get_watermark("alice@s.whatsapp.net") == ts

    def test_get_nonexistent_watermark(self):
        """Returns None for a chat with no watermark."""
        state = MCPState()
        assert state.get_watermark("nonexistent@s.whatsapp.net") is None

    def test_overwrite_watermark(self):
        """Setting a watermark again overwrites the old value."""
        state = MCPState()
        ts1 = datetime(2026, 3, 25, 10, 0, 0)
        ts2 = datetime(2026, 3, 25, 11, 0, 0)
        state.set_watermark("alice@s.whatsapp.net", ts1)
        state.set_watermark("alice@s.whatsapp.net", ts2)
        assert state.get_watermark("alice@s.whatsapp.net") == ts2

    def test_corrupt_watermark_returns_none(self):
        """Corrupt watermark value returns None with warning."""
        state = MCPState(watermarks={"alice@s.whatsapp.net": "not-a-date"})
        assert state.get_watermark("alice@s.whatsapp.net") is None


# =========================================================================
# Contact cache
# =========================================================================


@pytest.mark.unit
class TestContactCache:
    """Tests for the contact name cache."""

    def test_set_and_get(self):
        """Contact name round-trips."""
        state = MCPState()
        state.set_contact_name("447837370336", "Alice")
        assert state.get_contact_name("447837370336") == "Alice"

    def test_get_missing(self):
        """Returns None for uncached sender."""
        state = MCPState()
        assert state.get_contact_name("unknown") is None


# =========================================================================
# Voice retry queue
# =========================================================================


@pytest.mark.unit
class TestVoiceRetryQueue:
    """Tests for the voice transcription retry queue."""

    def test_add_and_pop(self):
        """Items can be added and popped."""
        state = MCPState()
        ts = datetime(2026, 3, 25, 10, 0, 0)
        state.add_voice_retry("msg001", "alice@jid", ts)
        assert len(state.voice_retry_queue) == 1

        retries = state.pop_voice_retries()
        assert len(retries) == 1
        assert retries[0].message_id == "msg001"
        assert retries[0].attempts == 1

    def test_no_duplicates(self):
        """Adding the same message twice is idempotent."""
        state = MCPState()
        ts = datetime(2026, 3, 25, 10, 0, 0)
        state.add_voice_retry("msg001", "alice@jid", ts)
        state.add_voice_retry("msg001", "alice@jid", ts)
        assert len(state.voice_retry_queue) == 1

    def test_max_attempts_exceeded(self):
        """Items exceeding max_attempts are dropped."""
        state = MCPState()
        state.voice_retry_queue.append(
            VoiceRetryItem(
                message_id="msg001",
                chat_jid="alice@jid",
                timestamp="2026-03-25T10:00:00",
                attempts=3,
            )
        )
        retries = state.pop_voice_retries(max_attempts=3)
        assert len(retries) == 0
        assert len(state.voice_retry_queue) == 0


# =========================================================================
# Serialisation round-trip
# =========================================================================


@pytest.mark.unit
class TestSerialisation:
    """Tests for to_dict / from_dict round-trips."""

    def test_round_trip(self):
        """State survives a to_dict → from_dict cycle."""
        state = MCPState()
        state.set_watermark("alice@jid", datetime(2026, 3, 25, 10, 0, 0))
        state.set_contact_name("447837370336", "Alice")
        state.add_voice_retry("msg001", "alice@jid", datetime(2026, 3, 25, 10, 0, 0))
        state.last_sync = "2026-03-25T12:00:00"

        data = state.to_dict()
        restored = MCPState.from_dict(data)

        assert restored.version == state.version
        assert restored.watermarks == state.watermarks
        assert restored.contact_cache == state.contact_cache
        assert len(restored.voice_retry_queue) == 1
        assert restored.voice_retry_queue[0].message_id == "msg001"
        assert restored.last_sync == state.last_sync

    def test_from_dict_missing_keys(self):
        """Handles partial/older JSON gracefully."""
        data = {"version": 1, "watermarks": {"jid": "2026-03-25T10:00:00"}}
        state = MCPState.from_dict(data)
        assert state.watermarks == {"jid": "2026-03-25T10:00:00"}
        assert state.contact_cache == {}
        assert state.voice_retry_queue == []


# =========================================================================
# File persistence
# =========================================================================


@pytest.mark.unit
class TestFilePersistence:
    """Tests for save() and load() file I/O."""

    def test_save_and_load(self, tmp_path):
        """State round-trips through file I/O."""
        path = tmp_path / "state.json"

        state = MCPState()
        state.set_watermark("alice@jid", datetime(2026, 3, 25, 10, 0, 0))
        state.set_contact_name("447837370336", "Alice")
        state.save(path)

        loaded = MCPState.load(path)
        assert loaded.get_watermark("alice@jid") == datetime(2026, 3, 25, 10, 0, 0)
        assert loaded.get_contact_name("447837370336") == "Alice"
        assert loaded.last_sync is not None  # set by save()

    def test_load_nonexistent_returns_fresh(self, tmp_path):
        """Loading from a nonexistent file returns fresh state."""
        path = tmp_path / "nonexistent" / "state.json"
        state = MCPState.load(path)
        assert state.watermarks == {}
        assert state.version == STATE_VERSION

    def test_load_corrupt_json_returns_fresh(self, tmp_path):
        """Corrupt JSON is handled gracefully."""
        path = tmp_path / "state.json"
        path.write_text("this is not json{{{")

        state = MCPState.load(path)
        assert state.watermarks == {}

    def test_load_wrong_type_returns_fresh(self, tmp_path):
        """Non-dict JSON is handled gracefully."""
        path = tmp_path / "state.json"
        path.write_text('"just a string"')

        state = MCPState.load(path)
        assert state.watermarks == {}

    def test_load_array_json_returns_fresh(self, tmp_path):
        """Array JSON at top level is handled gracefully."""
        path = tmp_path / "state.json"
        path.write_text("[1, 2, 3]")

        state = MCPState.load(path)
        assert state.watermarks == {}

    def test_creates_parent_directories(self, tmp_path):
        """save() creates parent directories if needed."""
        path = tmp_path / "deep" / "nested" / "state.json"
        state = MCPState()
        state.save(path)
        assert path.exists()

    def test_atomic_write_no_tmp_left(self, tmp_path):
        """After a successful save, no .tmp file remains."""
        path = tmp_path / "state.json"
        state = MCPState()
        state.save(path)

        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_save_produces_valid_json(self, tmp_path):
        """The saved file contains valid, pretty-printed JSON."""
        path = tmp_path / "state.json"
        state = MCPState()
        state.set_watermark("jid", datetime(2026, 1, 1))
        state.save(path)

        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        assert data["version"] == STATE_VERSION

    def test_overwrite_existing(self, tmp_path):
        """Saving over an existing file replaces it."""
        path = tmp_path / "state.json"

        state1 = MCPState()
        state1.set_watermark("jid1", datetime(2026, 1, 1))
        state1.save(path)

        state2 = MCPState()
        state2.set_watermark("jid2", datetime(2026, 2, 2))
        state2.save(path)

        loaded = MCPState.load(path)
        assert loaded.get_watermark("jid2") is not None
        # jid1 should NOT be present (fresh state overwrites)
        assert loaded.get_watermark("jid1") is None

    def test_future_version_loads_with_warning(self, tmp_path):
        """A state file with a higher version loads but warns."""
        path = tmp_path / "state.json"
        data = {"version": 999, "watermarks": {"jid": "2026-03-25T10:00:00"}}
        path.write_text(json.dumps(data))

        state = MCPState.load(path)
        assert state.version == 999
        assert state.get_watermark("jid") == datetime(2026, 3, 25, 10, 0, 0)
