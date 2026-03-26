"""
Tests for core abstractions package.
"""

import pytest
from datetime import datetime

from whatsapp_chat_autoexport.core import (
    # Errors
    ErrorCategory,
    ErrorSeverity,
    ExportError,
    RecoveryHint,
    DeviceConnectionError,
    AppStateError,
    ElementNotFoundError,
    ExportWorkflowError,
    TranscriptionError,
    PipelineError,
    # Result type
    Result,
    Ok,
    Err,
    # Events
    Event,
    EventType,
    EventBus,
    StateChangeEvent,
    ExportProgressEvent,
    PipelineProgressEvent,
    ErrorEvent,
)
from whatsapp_chat_autoexport.core.result import (
    is_ok,
    is_err,
    unwrap,
    unwrap_or,
    collect_results,
    try_except,
    from_optional,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_all_categories_defined(self):
        """Verify key error categories exist."""
        assert ErrorCategory.CONNECTION
        assert ErrorCategory.APP_STATE
        assert ErrorCategory.ELEMENT_NOT_FOUND
        assert ErrorCategory.MENU_NAVIGATION
        assert ErrorCategory.TRANSCRIPTION_API
        assert ErrorCategory.TIMEOUT


class TestRecoveryHint:
    """Tests for RecoveryHint dataclass."""

    def test_retry_factory(self):
        """Test retry hint creation."""
        hint = RecoveryHint.retry(max_retries=5, delay=2.0)
        assert hint.action == "retry"
        assert hint.max_retries == 5
        assert hint.retry_delay_seconds == 2.0
        assert hint.auto_recoverable is True

    def test_skip_factory(self):
        """Test skip hint creation."""
        hint = RecoveryHint.skip("Skip this item")
        assert hint.action == "skip"
        assert hint.auto_recoverable is True

    def test_reconnect_factory(self):
        """Test reconnect hint creation."""
        hint = RecoveryHint.reconnect()
        assert hint.action == "reconnect"
        assert hint.max_retries == 3
        assert hint.retry_delay_seconds == 5.0

    def test_user_action_factory(self):
        """Test user action hint creation."""
        hint = RecoveryHint.user_action("Unlock your phone")
        assert hint.action == "user_action"
        assert hint.requires_user_action is True
        assert hint.user_instruction == "Unlock your phone"

    def test_abort_factory(self):
        """Test abort hint creation."""
        hint = RecoveryHint.abort("Cannot continue")
        assert hint.action == "abort"
        assert hint.auto_recoverable is False


class TestExportError:
    """Tests for ExportError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = ExportError(
            category=ErrorCategory.CONNECTION,
            message="Connection failed",
        )
        assert error.category == ErrorCategory.CONNECTION
        assert error.message == "Connection failed"
        assert error.severity == ErrorSeverity.ERROR
        assert isinstance(error.timestamp, datetime)

    def test_error_with_context(self):
        """Test error with context chaining."""
        error = ExportError(
            category=ErrorCategory.ELEMENT_NOT_FOUND,
            message="Button not found",
        ).with_context(element="upload_button", screen="drive_selection")

        assert error.context["element"] == "upload_button"
        assert error.context["screen"] == "drive_selection"

    def test_error_with_hint(self):
        """Test error with recovery hints."""
        error = ExportError(
            category=ErrorCategory.TIMEOUT,
            message="Operation timed out",
        ).with_hint(RecoveryHint.retry(3))

        assert len(error.recovery_hints) == 1
        assert error.can_auto_recover() is True

    def test_error_string_representation(self):
        """Test error string formatting."""
        error = ExportError(
            category=ErrorCategory.CONNECTION,
            message="Device disconnected",
            context={"device_id": "192.168.1.100:5555"},
        )
        error_str = str(error)
        assert "[CONNECTION]" in error_str
        assert "Device disconnected" in error_str

    def test_get_auto_recovery_hint(self):
        """Test getting first auto-recoverable hint."""
        error = ExportError(
            category=ErrorCategory.TIMEOUT,
            message="Timeout",
        )
        error.with_hint(RecoveryHint.abort())
        error.with_hint(RecoveryHint.retry(2))

        hint = error.get_auto_recovery_hint()
        assert hint is not None
        assert hint.action == "retry"


class TestSpecificErrors:
    """Tests for specific error types."""

    def test_device_connection_error(self):
        """Test DeviceConnectionError creation."""
        error = DeviceConnectionError(
            message="Failed to connect via USB",
            device_id="abc123",
        )
        assert error.category == ErrorCategory.CONNECTION
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.context["device_id"] == "abc123"
        assert len(error.recovery_hints) >= 1

    def test_app_state_error(self):
        """Test AppStateError creation."""
        error = AppStateError(
            message="WhatsApp not in chat list",
            expected_state="chat_list",
            actual_state="settings",
        )
        assert error.category == ErrorCategory.APP_STATE
        assert error.context["expected"] == "chat_list"
        assert error.context["actual"] == "settings"

    def test_element_not_found_error(self):
        """Test ElementNotFoundError creation."""
        error = ElementNotFoundError(
            message="Export button not found",
            element_name="export_button",
            strategies_tried=["id", "text", "content_desc"],
        )
        assert error.category == ErrorCategory.ELEMENT_NOT_FOUND
        assert error.context["element"] == "export_button"
        assert "id" in error.context["strategies"]

    def test_transcription_error(self):
        """Test TranscriptionError creation."""
        error = TranscriptionError(
            message="API rate limit exceeded",
            file_path="/path/to/audio.opus",
            provider="whisper",
        )
        assert error.category == ErrorCategory.TRANSCRIPTION_API
        assert error.severity == ErrorSeverity.WARNING


class TestResult:
    """Tests for Result type."""

    def test_ok_creation(self):
        """Test Ok result creation."""
        result = Ok(42)
        assert result.is_ok()
        assert not result.is_err()
        assert result.value == 42

    def test_err_creation(self):
        """Test Err result creation."""
        result = Err("something went wrong")
        assert not result.is_ok()
        assert result.is_err()
        assert result.error == "something went wrong"

    def test_ok_unwrap(self):
        """Test unwrapping Ok."""
        result = Ok("hello")
        assert result.unwrap() == "hello"

    def test_err_unwrap_raises(self):
        """Test unwrapping Err raises ValueError."""
        result = Err("error")
        with pytest.raises(ValueError):
            result.unwrap()

    def test_unwrap_or(self):
        """Test unwrap_or with default."""
        ok_result = Ok(10)
        err_result = Err("error")

        assert ok_result.unwrap_or(0) == 10
        assert err_result.unwrap_or(0) == 0

    def test_unwrap_or_else(self):
        """Test unwrap_or_else with callable."""
        ok_result = Ok(10)
        err_result = Err("error")

        assert ok_result.unwrap_or_else(lambda: 0) == 10
        assert err_result.unwrap_or_else(lambda e: len(e)) == 5

    def test_map_ok(self):
        """Test mapping Ok value."""
        result = Ok(5)
        mapped = result.map(lambda x: x * 2)
        assert mapped.value == 10

    def test_map_err(self):
        """Test map on Err returns unchanged."""
        result = Err("error")
        mapped = result.map(lambda x: x * 2)
        assert mapped.error == "error"

    def test_map_err_transforms(self):
        """Test map_err transforms error."""
        result = Err("error")
        mapped = result.map_err(lambda e: e.upper())
        assert mapped.error == "ERROR"

    def test_and_then_ok(self):
        """Test chaining Ok results."""
        result = Ok(5)
        chained = result.and_then(lambda x: Ok(x * 2))
        assert chained.value == 10

    def test_and_then_err(self):
        """Test chaining on Err returns Err."""
        result = Err("error")
        chained = result.and_then(lambda x: Ok(x * 2))
        assert chained.error == "error"


class TestResultUtilities:
    """Tests for Result utility functions."""

    def test_is_ok_function(self):
        """Test is_ok helper function."""
        assert is_ok(Ok(1)) is True
        assert is_ok(Err("e")) is False

    def test_is_err_function(self):
        """Test is_err helper function."""
        assert is_err(Err("e")) is True
        assert is_err(Ok(1)) is False

    def test_collect_results_all_ok(self):
        """Test collecting all Ok results."""
        results = [Ok(1), Ok(2), Ok(3)]
        collected = collect_results(results)
        assert is_ok(collected)
        assert collected.value == [1, 2, 3]

    def test_collect_results_with_err(self):
        """Test collecting results with Err returns first Err."""
        results = [Ok(1), Err("failed"), Ok(3)]
        collected = collect_results(results)
        assert is_err(collected)
        assert collected.error == "failed"

    def test_try_except_success(self):
        """Test try_except with successful function."""
        result = try_except(lambda: 42)
        assert is_ok(result)
        assert result.value == 42

    def test_try_except_failure(self):
        """Test try_except with failing function."""
        result = try_except(lambda: int("not a number"))
        assert is_err(result)
        assert isinstance(result.error, ValueError)

    def test_from_optional_with_value(self):
        """Test from_optional with value."""
        result = from_optional("hello", "not found")
        assert is_ok(result)
        assert result.value == "hello"

    def test_from_optional_none(self):
        """Test from_optional with None."""
        result = from_optional(None, "not found")
        assert is_err(result)
        assert result.error == "not found"


class TestEvents:
    """Tests for event system."""

    def test_basic_event(self):
        """Test basic event creation."""
        event = Event(type=EventType.EXPORT_STARTED, data={"chat": "John"})
        assert event.type == EventType.EXPORT_STARTED
        assert event.data["chat"] == "John"
        assert isinstance(event.timestamp, datetime)

    def test_state_change_event(self):
        """Test StateChangeEvent creation."""
        event = StateChangeEvent(old_state="idle", new_state="exporting")
        assert event.type == EventType.STATE_CHANGED
        assert event.data["old_state"] == "idle"
        assert event.data["new_state"] == "exporting"

    def test_export_progress_event(self):
        """Test ExportProgressEvent creation."""
        event = ExportProgressEvent(
            chat_name="John",
            step_name="open_menu",
            step_index=1,
            total_steps=6,
        )
        assert event.type == EventType.PROGRESS_UPDATED
        assert event.data["chat_name"] == "John"
        assert event.data["step_index"] == 1

    def test_pipeline_progress_event(self):
        """Test PipelineProgressEvent creation."""
        event = PipelineProgressEvent(
            phase="transcribe",
            current=5,
            total=10,
            item_name="audio.opus",
        )
        assert event.data["phase"] == "transcribe"
        assert event.data["current"] == 5

    def test_error_event(self):
        """Test ErrorEvent creation."""
        event = ErrorEvent(
            error_message="Connection lost",
            error_category="CONNECTION",
            recoverable=True,
            recovery_action="reconnect",
        )
        assert event.type == EventType.ERROR_OCCURRED
        assert event.data["recoverable"] is True


class TestEventBus:
    """Tests for EventBus."""

    def test_subscribe_and_emit(self):
        """Test basic subscription and emission."""
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(EventType.EXPORT_STARTED, handler)
        bus.emit(Event(type=EventType.EXPORT_STARTED, data={"chat": "John"}))

        assert len(received) == 1
        assert received[0].data["chat"] == "John"

    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        unsubscribe = bus.subscribe(EventType.EXPORT_STARTED, handler)

        # Emit first event
        bus.emit(Event(type=EventType.EXPORT_STARTED))
        assert len(received) == 1

        # Unsubscribe and emit second event
        unsubscribe()
        bus.emit(Event(type=EventType.EXPORT_STARTED))
        assert len(received) == 1  # Still 1, not 2

    def test_multiple_handlers(self):
        """Test multiple handlers for same event."""
        bus = EventBus()
        handler1_calls = []
        handler2_calls = []

        bus.subscribe(EventType.EXPORT_STARTED, lambda e: handler1_calls.append(e))
        bus.subscribe(EventType.EXPORT_STARTED, lambda e: handler2_calls.append(e))

        bus.emit(Event(type=EventType.EXPORT_STARTED))

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    def test_emit_simple(self):
        """Test emit_simple helper."""
        bus = EventBus()
        received = []

        bus.subscribe(EventType.PROGRESS_UPDATED, lambda e: received.append(e))
        bus.emit_simple(EventType.PROGRESS_UPDATED, source="test", progress=50)

        assert len(received) == 1
        assert received[0].data["progress"] == 50
        assert received[0].source == "test"

    def test_event_history(self):
        """Test event history retrieval."""
        bus = EventBus()

        bus.emit(Event(type=EventType.EXPORT_STARTED, data={"id": 1}))
        bus.emit(Event(type=EventType.EXPORT_COMPLETED, data={"id": 1}))
        bus.emit(Event(type=EventType.EXPORT_STARTED, data={"id": 2}))

        # Get all history
        history = bus.get_history()
        assert len(history) == 3

        # Get filtered history
        started_events = bus.get_history(EventType.EXPORT_STARTED)
        assert len(started_events) == 2

    def test_subscribe_all(self):
        """Test subscribing to all events."""
        bus = EventBus()
        received = []

        bus.subscribe_all(lambda e: received.append(e))

        bus.emit(Event(type=EventType.EXPORT_STARTED))
        bus.emit(Event(type=EventType.EXPORT_COMPLETED))
        bus.emit(Event(type=EventType.ERROR_OCCURRED))

        assert len(received) == 3

    def test_handler_error_isolated(self):
        """Test that handler errors don't break other handlers."""
        bus = EventBus()
        received = []

        def failing_handler(event):
            raise RuntimeError("Handler failed")

        def working_handler(event):
            received.append(event)

        bus.subscribe(EventType.EXPORT_STARTED, failing_handler)
        bus.subscribe(EventType.EXPORT_STARTED, working_handler)

        # Should not raise, and working_handler should still be called
        bus.emit(Event(type=EventType.EXPORT_STARTED))
        assert len(received) == 1
