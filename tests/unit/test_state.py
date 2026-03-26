"""
Tests for state management package.

Tests cover:
- Pydantic state models (ChatState, SessionState, ExportProgress)
- StateManager with event emission
- CheckpointManager with save/restore
- ExportQueue with priority ordering
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from whatsapp_chat_autoexport.state import (
    ChatStatus,
    ChatState,
    SessionStatus,
    SessionState,
    ExportProgress,
    PipelineProgress,
    StateManager,
    CheckpointManager,
    ExportQueue,
    QueueItem,
    QueuePriority,
)
from whatsapp_chat_autoexport.core.events import EventBus, EventType


# =============================================================================
# ChatState Model Tests
# =============================================================================


class TestChatState:
    """Tests for ChatState Pydantic model."""

    def test_create_default_chat_state(self):
        """Test creating ChatState with defaults."""
        chat = ChatState(name="Test Chat")

        assert chat.name == "Test Chat"
        assert chat.status == ChatStatus.PENDING
        assert chat.index == 0
        assert chat.current_step == 0
        assert chat.total_steps == 6
        assert chat.steps_completed == []
        assert chat.attempt_count == 0
        assert chat.max_attempts == 3

    def test_chat_state_start(self):
        """Test marking chat as started."""
        chat = ChatState(name="Test Chat")
        chat.start()

        assert chat.status == ChatStatus.IN_PROGRESS
        assert chat.started_at is not None
        assert chat.attempt_count == 1

    def test_chat_state_complete(self):
        """Test marking chat as completed."""
        chat = ChatState(name="Test Chat")
        chat.start()
        chat.complete()

        assert chat.status == ChatStatus.COMPLETED
        assert chat.completed_at is not None
        assert chat.duration_seconds > 0

    def test_chat_state_fail(self):
        """Test marking chat as failed."""
        chat = ChatState(name="Test Chat")
        chat.start()
        chat.fail("Element not found")

        assert chat.status == ChatStatus.FAILED
        assert chat.error_message == "Element not found"
        assert chat.completed_at is not None

    def test_chat_state_skip(self):
        """Test marking chat as skipped."""
        chat = ChatState(name="Test Chat")
        chat.skip("Community chat")

        assert chat.status == ChatStatus.SKIPPED
        assert chat.error_message == "Community chat"

    def test_chat_state_pause_resume(self):
        """Test pause and resume functionality."""
        chat = ChatState(name="Test Chat")
        chat.start()
        chat.pause()

        assert chat.status == ChatStatus.PAUSED

        chat.resume()
        assert chat.status == ChatStatus.IN_PROGRESS

    def test_chat_state_record_step(self):
        """Test recording completed steps."""
        chat = ChatState(name="Test Chat")

        chat.record_step("open_menu")
        assert "open_menu" in chat.steps_completed
        assert chat.current_step == 1

        chat.record_step("click_more")
        assert len(chat.steps_completed) == 2
        assert chat.current_step == 2

    def test_chat_state_is_complete(self):
        """Test is_complete property."""
        chat = ChatState(name="Test Chat")
        assert not chat.is_complete

        chat.complete()
        assert chat.is_complete

    def test_chat_state_is_failed(self):
        """Test is_failed property."""
        chat = ChatState(name="Test Chat")
        assert not chat.is_failed

        chat.fail("Error")
        assert chat.is_failed

    def test_chat_state_can_retry(self):
        """Test can_retry property."""
        chat = ChatState(name="Test Chat")
        chat.start()
        chat.fail("Error")

        assert chat.can_retry
        assert chat.attempt_count == 1

    def test_chat_state_max_retries_exceeded(self):
        """Test that can_retry returns False after max attempts."""
        chat = ChatState(name="Test Chat", max_attempts=2)

        # First attempt
        chat.start()
        chat.fail("Error 1")
        assert chat.can_retry

        # Second attempt
        chat.start()
        chat.fail("Error 2")
        assert not chat.can_retry

    def test_chat_state_serialization(self):
        """Test that ChatState can be serialized to JSON."""
        chat = ChatState(name="Test Chat")
        chat.start()
        chat.record_step("open_menu")

        # Serialize
        data = chat.model_dump(mode="json")

        # Deserialize
        restored = ChatState.model_validate(data)

        assert restored.name == chat.name
        assert restored.status == chat.status
        assert restored.steps_completed == chat.steps_completed


# =============================================================================
# SessionState Model Tests
# =============================================================================


class TestSessionState:
    """Tests for SessionState Pydantic model."""

    def test_create_default_session_state(self):
        """Test creating SessionState with defaults."""
        session = SessionState()

        assert session.status == SessionStatus.INITIALIZING
        assert session.total_chats == 0
        assert session.completed_chats == 0
        assert session.chats == {}

    def test_session_state_add_chat(self):
        """Test adding a chat to session."""
        session = SessionState()

        chat = session.add_chat("Test Chat", index=0)

        assert "Test Chat" in session.chats
        assert session.total_chats == 1
        assert chat.name == "Test Chat"

    def test_session_state_add_duplicate_chat(self):
        """Test adding duplicate chat returns existing."""
        session = SessionState()

        chat1 = session.add_chat("Test Chat")
        chat2 = session.add_chat("Test Chat")

        assert chat1 is chat2
        assert session.total_chats == 1

    def test_session_state_get_chat(self):
        """Test getting a chat by name."""
        session = SessionState()
        session.add_chat("Test Chat")

        chat = session.get_chat("Test Chat")
        assert chat is not None
        assert chat.name == "Test Chat"

        missing = session.get_chat("Missing")
        assert missing is None

    def test_session_state_current_chat(self):
        """Test current_chat property."""
        session = SessionState()
        chat1 = session.add_chat("Chat 1")
        chat2 = session.add_chat("Chat 2")

        assert session.current_chat is None

        chat1.start()
        assert session.current_chat == chat1

        chat1.complete()
        assert session.current_chat is None

    def test_session_state_update_counts(self):
        """Test update_counts method."""
        session = SessionState()

        chat1 = session.add_chat("Chat 1")
        chat2 = session.add_chat("Chat 2")
        chat3 = session.add_chat("Chat 3")

        chat1.complete()
        chat2.fail("Error")
        chat3.skip("Community")

        session.update_counts()

        assert session.completed_chats == 1
        assert session.failed_chats == 1
        assert session.skipped_chats == 1

    def test_session_state_progress_percent(self):
        """Test progress_percent property."""
        session = SessionState()

        assert session.progress_percent == 0.0

        session.add_chat("Chat 1").complete()
        session.add_chat("Chat 2")
        session.update_counts()

        assert session.progress_percent == 50.0

    def test_session_state_pending_chats(self):
        """Test pending_chats property."""
        session = SessionState()

        session.add_chat("Chat 1").complete()
        session.add_chat("Chat 2")
        session.add_chat("Chat 3")
        session.update_counts()

        assert session.pending_chats == 2

    def test_session_state_lifecycle(self):
        """Test session lifecycle methods."""
        session = SessionState()

        session.start()
        assert session.status == SessionStatus.EXPORTING
        assert session.started_at is not None

        session.pause()
        assert session.status == SessionStatus.PAUSED

        session.resume()
        assert session.status == SessionStatus.EXPORTING

        session.complete()
        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None

    def test_session_state_fail(self):
        """Test session fail method."""
        session = SessionState()
        session.fail("Connection lost")

        assert session.status == SessionStatus.FAILED
        assert session.error_message == "Connection lost"

    def test_session_state_serialization(self):
        """Test SessionState can be serialized and restored."""
        session = SessionState(include_media=False)
        session.add_chat("Chat 1").complete()
        session.add_chat("Chat 2")
        session.update_counts()

        # Serialize
        data = session.model_dump(mode="json")

        # Deserialize
        restored = SessionState.model_validate(data)

        assert restored.total_chats == 2
        assert restored.completed_chats == 1
        assert "Chat 1" in restored.chats


# =============================================================================
# ExportProgress Model Tests
# =============================================================================


class TestExportProgress:
    """Tests for ExportProgress model."""

    def test_create_default_progress(self):
        """Test creating ExportProgress with defaults."""
        progress = ExportProgress()

        assert progress.current_chat is None
        assert progress.chats_completed == 0
        assert progress.status == "idle"

    def test_progress_percent_complete(self):
        """Test percent_complete calculation."""
        progress = ExportProgress(
            chats_completed=3,
            chats_total=10,
            chats_failed=1,
            chats_skipped=1,
        )

        # 3 completed + 1 failed + 1 skipped = 5 processed out of 10
        assert progress.percent_complete == 50.0

    def test_progress_percent_with_zero_total(self):
        """Test percent_complete with zero total."""
        progress = ExportProgress(chats_total=0)
        assert progress.percent_complete == 0.0


# =============================================================================
# PipelineProgress Model Tests
# =============================================================================


class TestPipelineProgress:
    """Tests for PipelineProgress model."""

    def test_create_default_pipeline_progress(self):
        """Test creating PipelineProgress with defaults."""
        progress = PipelineProgress()

        assert progress.phase == ""
        assert progress.phase_index == 0
        assert progress.total_phases == 5

    def test_pipeline_percent_complete(self):
        """Test percent_complete calculation."""
        progress = PipelineProgress(
            phase_index=2,
            total_phases=4,
            items_processed=5,
            items_total=10,
        )

        # 2/4 phases = 50% + (5/10 items * 25% per phase) = 62.5%
        assert progress.percent_complete == 62.5


# =============================================================================
# StateManager Tests
# =============================================================================


class TestStateManager:
    """Tests for StateManager."""

    def test_create_state_manager(self):
        """Test creating StateManager."""
        manager = StateManager()

        assert not manager.has_session
        assert manager.session is None

    def test_create_session(self):
        """Test creating a session."""
        manager = StateManager()

        session = manager.create_session(include_media=False, limit=10)

        assert manager.has_session
        assert session.include_media is False
        assert session.limit == 10

    def test_get_session_creates_if_needed(self):
        """Test get_session creates session if none exists."""
        manager = StateManager()

        session = manager.get_session()

        assert manager.has_session
        assert session is not None

    def test_set_session_status(self):
        """Test setting session status."""
        manager = StateManager()
        manager.create_session()

        manager.set_session_status(SessionStatus.EXPORTING)

        assert manager.session.status == SessionStatus.EXPORTING
        assert manager.session.started_at is not None

    def test_add_chat(self):
        """Test adding a chat."""
        manager = StateManager()
        manager.create_session()

        chat = manager.add_chat("Test Chat", index=0)

        assert chat.name == "Test Chat"
        assert "Test Chat" in manager.session.chats

    def test_add_chats(self):
        """Test adding multiple chats."""
        manager = StateManager()
        manager.create_session()

        chats = manager.add_chats(["Chat 1", "Chat 2", "Chat 3"])

        assert len(chats) == 3
        assert manager.session.total_chats == 3

    def test_start_chat(self):
        """Test starting a chat."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")

        chat = manager.start_chat("Test Chat")

        assert chat.status == ChatStatus.IN_PROGRESS

    def test_complete_chat(self):
        """Test completing a chat."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")
        manager.start_chat("Test Chat")

        chat = manager.complete_chat("Test Chat")

        assert chat.status == ChatStatus.COMPLETED
        assert manager.session.completed_chats == 1

    def test_fail_chat(self):
        """Test failing a chat."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")
        manager.start_chat("Test Chat")

        chat = manager.fail_chat("Test Chat", "Element not found")

        assert chat.status == ChatStatus.FAILED
        assert chat.error_message == "Element not found"
        assert manager.session.failed_chats == 1

    def test_skip_chat(self):
        """Test skipping a chat."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")

        chat = manager.skip_chat("Test Chat", "Community chat")

        assert chat.status == ChatStatus.SKIPPED
        assert manager.session.skipped_chats == 1

    def test_record_step(self):
        """Test recording a step."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")
        manager.start_chat("Test Chat")

        manager.record_step("Test Chat", "open_menu")

        chat = manager.session.get_chat("Test Chat")
        assert "open_menu" in chat.steps_completed

    def test_get_progress(self):
        """Test getting progress snapshot."""
        manager = StateManager()
        manager.create_session()
        manager.add_chats(["Chat 1", "Chat 2"])
        manager.start_chat("Chat 1")

        progress = manager.get_progress()

        assert progress.current_chat == "Chat 1"
        assert progress.chats_total == 2
        assert progress.chats_completed == 0

    def test_get_pending_chats(self):
        """Test getting pending chats."""
        manager = StateManager()
        manager.create_session()
        manager.add_chats(["Chat 1", "Chat 2", "Chat 3"])
        manager.start_chat("Chat 1")
        manager.complete_chat("Chat 1")

        pending = manager.get_pending_chats()

        assert len(pending) == 2

    def test_get_next_chat(self):
        """Test getting next pending chat."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Chat 1", index=1)
        manager.add_chat("Chat 2", index=0)

        next_chat = manager.get_next_chat()

        # Should return Chat 2 (index 0) first
        assert next_chat.name == "Chat 2"

    def test_pause_resume(self):
        """Test pause and resume."""
        manager = StateManager()
        manager.create_session()
        manager.set_session_status(SessionStatus.EXPORTING)
        manager.add_chat("Test Chat")
        manager.start_chat("Test Chat")

        manager.pause()

        assert manager.session.status == SessionStatus.PAUSED

        manager.resume()

        assert manager.session.status == SessionStatus.EXPORTING

    def test_reset(self):
        """Test reset clears session."""
        manager = StateManager()
        manager.create_session()
        manager.add_chat("Test Chat")

        manager.reset()

        assert not manager.has_session

    def test_event_emission(self):
        """Test that state changes emit events."""
        event_bus = EventBus()
        manager = StateManager(event_bus=event_bus)

        events = []
        event_bus.subscribe(EventType.STATE_CHANGED, lambda e: events.append(e))

        manager.create_session()

        # Should have emitted state change event
        assert len(events) > 0


# =============================================================================
# CheckpointManager Tests
# =============================================================================


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_create_checkpoint_manager(self):
        """Test creating CheckpointManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(checkpoint_dir=Path(tmpdir))

            assert manager.checkpoint_dir == Path(tmpdir)
            assert not manager.has_checkpoint()

    def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(
                checkpoint_dir=Path(tmpdir),
                checkpoint_interval=1,  # Force save every chat
            )

            # Create session state
            session = SessionState(include_media=False)
            session.add_chat("Chat 1").complete()
            session.add_chat("Chat 2")
            session.update_counts()

            # Save checkpoint
            path = manager.save(session, force=True)

            assert path is not None
            assert path.exists()

            # Load checkpoint
            restored = manager.load_latest()

            assert restored is not None
            assert restored.total_chats == 2
            assert restored.completed_chats == 1

    def test_checkpoint_interval(self):
        """Test that checkpoint respects interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(
                checkpoint_dir=Path(tmpdir),
                checkpoint_interval=3,
            )

            session = SessionState()

            # First two saves should be skipped
            assert manager.save(session) is None
            assert manager.save(session) is None

            # Third save should succeed
            path = manager.save(session)
            assert path is not None

    def test_checkpoint_rotation(self):
        """Test that old checkpoints are rotated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(
                checkpoint_dir=Path(tmpdir),
                checkpoint_interval=1,
                max_checkpoints=2,
            )

            session = SessionState()

            # Create checkpoint files directly with different timestamps
            # to test rotation logic without timing issues
            for i in range(3):
                checkpoint_file = Path(tmpdir) / f"checkpoint_20240101_00000{i}.json"
                with open(checkpoint_file, "w") as f:
                    json.dump(session.model_dump(mode="json"), f, default=str)

            # Verify we have 3 files before rotation
            assert len(list(Path(tmpdir).glob("checkpoint_*.json"))) == 3

            # Trigger rotation by saving another checkpoint
            manager.save(session, force=True)

            # Should now have at most 2 checkpoints (new one + one old)
            checkpoints = manager.list_checkpoints()
            assert len(checkpoints) <= 2

    def test_load_specific_checkpoint(self):
        """Test loading a specific checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(checkpoint_dir=Path(tmpdir))

            session = SessionState()
            session.add_chat("Test Chat")

            path = manager.save(session, force=True)

            restored = manager.load(path)

            assert restored is not None
            assert "Test Chat" in restored.chats

    def test_load_nonexistent_checkpoint(self):
        """Test loading nonexistent checkpoint returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(checkpoint_dir=Path(tmpdir))

            result = manager.load(Path(tmpdir) / "nonexistent.json")

            assert result is None

    def test_clear_checkpoints(self):
        """Test clearing all checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(checkpoint_dir=Path(tmpdir))

            session = SessionState()
            manager.save(session, force=True)
            manager.save(session, force=True)

            assert manager.has_checkpoint()

            manager.clear()

            assert not manager.has_checkpoint()

    def test_checkpoint_info(self):
        """Test getting checkpoint info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(checkpoint_dir=Path(tmpdir))

            # No checkpoints
            info = manager.get_checkpoint_info()
            assert info["count"] == 0
            assert info["latest"] is None

            # With checkpoint
            session = SessionState()
            manager.save(session, force=True)

            info = manager.get_checkpoint_info()
            assert info["count"] == 1
            assert info["latest"] is not None


# =============================================================================
# ExportQueue Tests
# =============================================================================


class TestExportQueue:
    """Tests for ExportQueue."""

    def test_create_empty_queue(self):
        """Test creating empty queue."""
        queue = ExportQueue()

        assert len(queue) == 0
        assert queue.is_empty()

    def test_add_item(self):
        """Test adding item to queue."""
        queue = ExportQueue()

        item = queue.add("Test Chat")

        assert len(queue) == 1
        assert item.chat_name == "Test Chat"
        assert "Test Chat" in queue

    def test_add_duplicate_returns_existing(self):
        """Test adding duplicate returns existing item."""
        queue = ExportQueue()

        item1 = queue.add("Test Chat")
        item2 = queue.add("Test Chat")

        assert item1 is item2
        assert len(queue) == 1

    def test_add_many(self):
        """Test adding multiple items."""
        queue = ExportQueue()

        items = queue.add_many(["Chat 1", "Chat 2", "Chat 3"])

        assert len(items) == 3
        assert len(queue) == 3

    def test_pop_returns_by_priority(self):
        """Test pop returns items by priority."""
        queue = ExportQueue()

        queue.add("Low Chat", priority=QueuePriority.LOW)
        queue.add("High Chat", priority=QueuePriority.HIGH)
        queue.add("Normal Chat", priority=QueuePriority.NORMAL)

        # Should return high priority first
        item = queue.pop()
        assert item.chat_name == "High Chat"

        # Then normal
        item = queue.pop()
        assert item.chat_name == "Normal Chat"

        # Then low
        item = queue.pop()
        assert item.chat_name == "Low Chat"

    def test_pop_empty_returns_none(self):
        """Test pop on empty queue returns None."""
        queue = ExportQueue()

        assert queue.pop() is None

    def test_peek(self):
        """Test peeking at next item."""
        queue = ExportQueue()

        queue.add("Test Chat")

        item = queue.peek()
        assert item is not None
        assert item.chat_name == "Test Chat"

        # Item should still be in queue
        assert len(queue) == 1

    def test_get_by_name(self):
        """Test getting item by name."""
        queue = ExportQueue()

        queue.add("Test Chat")

        item = queue.get("Test Chat")
        assert item is not None
        assert item.chat_name == "Test Chat"

        missing = queue.get("Missing")
        assert missing is None

    def test_remove(self):
        """Test removing item."""
        queue = ExportQueue()

        queue.add("Test Chat")

        item = queue.remove("Test Chat")

        assert item is not None
        assert len(queue) == 0
        assert "Test Chat" not in queue

    def test_reprioritize(self):
        """Test changing item priority."""
        queue = ExportQueue()

        queue.add("Test Chat", priority=QueuePriority.LOW)

        item = queue.reprioritize("Test Chat", QueuePriority.HIGH)

        assert item is not None
        assert item.priority == QueuePriority.HIGH.value

    def test_clear(self):
        """Test clearing queue."""
        queue = ExportQueue()

        queue.add_many(["Chat 1", "Chat 2", "Chat 3"])

        queue.clear()

        assert queue.is_empty()

    def test_items_returns_sorted(self):
        """Test items returns sorted list."""
        queue = ExportQueue()

        queue.add("Chat 1", priority=QueuePriority.LOW)
        queue.add("Chat 2", priority=QueuePriority.HIGH)
        queue.add("Chat 3", priority=QueuePriority.NORMAL)

        items = queue.items()

        assert items[0].chat_name == "Chat 2"  # HIGH
        assert items[1].chat_name == "Chat 3"  # NORMAL
        assert items[2].chat_name == "Chat 1"  # LOW

    def test_filter(self):
        """Test filtering items."""
        queue = ExportQueue()

        queue.add("Chat 1", priority=QueuePriority.HIGH)
        queue.add("Chat 2", priority=QueuePriority.LOW)
        queue.add("Chat 3", priority=QueuePriority.HIGH)

        high_priority = queue.filter(
            lambda item: item.priority == QueuePriority.HIGH.value
        )

        assert len(high_priority) == 2

    def test_stats(self):
        """Test queue statistics."""
        queue = ExportQueue()

        queue.add("Chat 1", priority=QueuePriority.HIGH)
        queue.add("Chat 2", priority=QueuePriority.NORMAL)
        queue.add("Chat 3", priority=QueuePriority.NORMAL)
        queue.add("Chat 4", priority=QueuePriority.LOW)

        stats = queue.stats()

        assert stats["total"] == 4
        assert stats["by_priority"]["HIGH"] == 1
        assert stats["by_priority"]["NORMAL"] == 2
        assert stats["by_priority"]["LOW"] == 1

    def test_queue_item_metadata(self):
        """Test queue item with metadata."""
        queue = ExportQueue()

        item = queue.add("Test Chat", include_media=True, device_id="abc123")

        assert item.metadata["include_media"] is True
        assert item.metadata["device_id"] == "abc123"

    def test_thread_safety(self):
        """Test that queue operations are thread-safe."""
        import threading

        queue = ExportQueue()
        errors = []

        def add_items(start, count):
            try:
                for i in range(count):
                    queue.add(f"Chat {start + i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_items, args=(0, 50)),
            threading.Thread(target=add_items, args=(50, 50)),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(queue) == 100


# =============================================================================
# Integration Tests
# =============================================================================


class TestStateIntegration:
    """Integration tests for state management."""

    def test_full_export_workflow(self):
        """Test complete export workflow with state tracking."""
        manager = StateManager()

        # Create session
        session = manager.create_session(include_media=True, limit=5)

        # Add chats
        manager.add_chats(["Chat 1", "Chat 2", "Chat 3"])
        manager.set_session_status(SessionStatus.EXPORTING)

        # Export first chat
        manager.start_chat("Chat 1")
        manager.record_step("Chat 1", "open_menu")
        manager.record_step("Chat 1", "click_more")
        manager.complete_chat("Chat 1")

        # Fail second chat
        manager.start_chat("Chat 2")
        manager.fail_chat("Chat 2", "Element not found")

        # Skip third chat
        manager.skip_chat("Chat 3", "Community chat")

        # Check progress
        progress = manager.get_progress()

        assert progress.chats_completed == 1
        assert progress.chats_failed == 1
        assert progress.chats_skipped == 1
        assert progress.percent_complete == 100.0

    def test_checkpoint_resume_workflow(self):
        """Test checkpoint and resume workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First session
            checkpoint = CheckpointManager(checkpoint_dir=Path(tmpdir))
            manager = StateManager()

            session = manager.create_session()
            manager.add_chats(["Chat 1", "Chat 2", "Chat 3"])
            manager.start_chat("Chat 1")
            manager.complete_chat("Chat 1")

            # Save checkpoint
            checkpoint.save(manager.session, force=True)

            # Simulate crash and restart
            del manager

            # Restore from checkpoint
            restored_session = checkpoint.load_latest()

            new_manager = StateManager()
            new_manager._session = restored_session

            # Continue from where we left off
            assert new_manager.session.completed_chats == 1

            pending = new_manager.get_pending_chats()
            assert len(pending) == 2

    def test_queue_with_state_manager(self):
        """Test using queue with state manager."""
        manager = StateManager()
        queue = ExportQueue()

        # Create session and queue
        manager.create_session()

        # Add to queue with priorities
        queue.add("Important Chat", priority=QueuePriority.HIGH)
        queue.add("Regular Chat", priority=QueuePriority.NORMAL)
        queue.add("Later Chat", priority=QueuePriority.LOW)

        # Process from queue
        while not queue.is_empty():
            item = queue.pop()
            chat = manager.add_chat(item.chat_name, index=item.index)
            manager.start_chat(item.chat_name)
            manager.complete_chat(item.chat_name)

        assert manager.session.completed_chats == 3
