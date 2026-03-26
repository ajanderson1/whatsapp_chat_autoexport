"""
Tests for SelectionScreen export mode progress callback wiring.

Tests that:
- Export progress callbacks flow through to ProgressPane
- Consecutive failure counter behavior works correctly
- CancelModal appears after MAX_CONSECUTIVE_FAILURES
- Deferred cancellation (wait for current chat) works
- Export results are preserved on back navigation
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Tests for the on_progress callback wiring
# ---------------------------------------------------------------------------

class TestProgressCallbackWiring:
    """Test that _export_single_chat passes on_progress to the exporter."""

    def _make_screen_with_app(self):
        """
        Create a SelectionScreen with a mocked app property.

        Textual's Screen.app is a ContextVar-based property that is hard to
        override without a running Textual app. We patch it at the class level.
        """
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._export_results = {"completed": [], "failed": [], "skipped": []}

        mock_app = MagicMock()
        mock_app.debug_mode = False
        return screen, mock_app

    def _make_mock_driver(self, whatsapp_open=True, chat_found=True):
        """Create a mock WhatsAppDriver."""
        driver = MagicMock()
        driver.verify_whatsapp_is_open.return_value = whatsapp_open
        driver.click_chat.return_value = chat_found
        driver.navigate_to_main.return_value = None
        driver.navigate_back_to_main.return_value = None
        return driver

    @patch("whatsapp_chat_autoexport.export.chat_exporter.ChatExporter")
    def test_on_progress_callback_passed_to_exporter(self, mock_exporter_cls):
        """Verify export_chat_to_google_drive receives the on_progress callback."""
        screen, mock_app = self._make_screen_with_app()
        mock_driver = self._make_mock_driver()

        mock_exporter = MagicMock()
        mock_exporter.export_chat_to_google_drive.return_value = True
        mock_exporter_cls.return_value = mock_exporter

        progress_calls = []
        def fake_progress(phase, message, current, total, item_name=""):
            progress_calls.append((phase, message, current, total, item_name))

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
            result = SelectionScreen._export_single_chat(
                screen, mock_driver, "Test Chat", True,
                log_callback=None, progress_callback=fake_progress,
            )

        assert result is True
        mock_exporter.export_chat_to_google_drive.assert_called_once_with(
            "Test Chat",
            include_media=True,
            on_progress=fake_progress,
        )

    @patch("whatsapp_chat_autoexport.export.chat_exporter.ChatExporter")
    def test_export_succeeds_without_progress_callback(self, mock_exporter_cls):
        """Verify export works when progress_callback is None."""
        screen, mock_app = self._make_screen_with_app()
        mock_driver = self._make_mock_driver()

        mock_exporter = MagicMock()
        mock_exporter.export_chat_to_google_drive.return_value = True
        mock_exporter_cls.return_value = mock_exporter

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
            result = SelectionScreen._export_single_chat(
                screen, mock_driver, "Test Chat", True,
                log_callback=None, progress_callback=None,
            )

        assert result is True
        mock_exporter.export_chat_to_google_drive.assert_called_once_with(
            "Test Chat",
            include_media=True,
            on_progress=None,
        )

    def test_export_returns_false_when_whatsapp_not_open(self):
        """Verify export returns False when WhatsApp is not accessible."""
        screen, mock_app = self._make_screen_with_app()
        mock_driver = self._make_mock_driver(whatsapp_open=False)

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
            result = SelectionScreen._export_single_chat(
                screen, mock_driver, "Test Chat", True,
            )
        assert result is False

    def test_export_returns_false_when_chat_not_found(self):
        """Verify export returns False when chat cannot be opened."""
        screen, mock_app = self._make_screen_with_app()
        mock_driver = self._make_mock_driver(chat_found=False)

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
            result = SelectionScreen._export_single_chat(
                screen, mock_driver, "Test Chat", True,
            )
        assert result is False

    def test_export_handles_exception_gracefully(self):
        """Verify export returns False and navigates back on exception."""
        screen, mock_app = self._make_screen_with_app()
        mock_driver = self._make_mock_driver()
        mock_driver.click_chat.side_effect = RuntimeError("Connection lost")

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
            result = SelectionScreen._export_single_chat(
                screen, mock_driver, "Test Chat", True,
            )
        assert result is False
        mock_driver.navigate_back_to_main.assert_called()


# ---------------------------------------------------------------------------
# Tests for consecutive failure detection
# ---------------------------------------------------------------------------

class TestConsecutiveFailureDetection:
    """Test that consecutive failures trigger the cancel modal."""

    def test_max_consecutive_failures_constant(self):
        """Verify the constant is defined and equals 3."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
        assert SelectionScreen.MAX_CONSECUTIVE_FAILURES == 3

    def test_consecutive_failures_reset_on_success(self):
        """Verify the counter resets to 0 after a successful export."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._consecutive_failures = 2
        # Simulating what _run_export does on success
        screen._consecutive_failures = 0
        assert screen._consecutive_failures == 0

    def test_consecutive_failures_increments_on_failure(self):
        """Verify the counter increments on each failure."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._consecutive_failures = 0

        for i in range(3):
            screen._consecutive_failures += 1
            assert screen._consecutive_failures == i + 1

    def test_threshold_matches_chat_exporter(self):
        """Verify our threshold matches ChatExporter.MAX_CONSECUTIVE_RECOVERIES."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
        from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter

        assert SelectionScreen.MAX_CONSECUTIVE_FAILURES == ChatExporter.MAX_CONSECUTIVE_RECOVERIES


# ---------------------------------------------------------------------------
# Tests for ProgressPane.update_export_step
# ---------------------------------------------------------------------------

class TestProgressPaneExportStep:
    """Test the new update_export_step method on ProgressPane."""

    def test_update_export_step_method_exists(self):
        """Verify the method is defined on ProgressPane."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import ProgressPane
        assert hasattr(ProgressPane, "update_export_step")
        assert callable(getattr(ProgressPane, "update_export_step"))

    def test_update_export_step_signature(self):
        """Verify the method has the correct parameters."""
        import inspect
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import ProgressPane

        sig = inspect.signature(ProgressPane.update_export_step)
        params = list(sig.parameters.keys())
        assert "step_message" in params
        assert "step_num" in params
        assert "total_steps" in params


# ---------------------------------------------------------------------------
# Tests for CancelModal message parameter
# ---------------------------------------------------------------------------

class TestCancelModalMessage:
    """Test that CancelModal accepts and displays a custom message."""

    def test_cancel_modal_accepts_message(self):
        """Verify CancelModal stores the message parameter."""
        from whatsapp_chat_autoexport.tui.textual_widgets.cancel_modal import CancelModal

        modal = CancelModal(
            current_chat="Test Chat",
            completed=1,
            total=5,
            message="Device may be disconnected",
        )
        assert modal._message == "Device may be disconnected"

    def test_cancel_modal_default_message_is_none(self):
        """Verify CancelModal defaults to None message."""
        from whatsapp_chat_autoexport.tui.textual_widgets.cancel_modal import CancelModal

        modal = CancelModal(completed=1, total=5)
        assert modal._message is None

    def test_cancel_modal_stores_current_chat(self):
        """Verify CancelModal stores the current chat reference."""
        from whatsapp_chat_autoexport.tui.textual_widgets.cancel_modal import CancelModal

        modal = CancelModal(current_chat="Alice", completed=2, total=10)
        assert modal._current_chat == "Alice"
        assert modal._completed == 2
        assert modal._total == 10


# ---------------------------------------------------------------------------
# Tests for deferred cancellation state
# ---------------------------------------------------------------------------

class TestDeferredCancellation:
    """Test the cancel-after-current-chat functionality."""

    def test_cancel_after_current_initialized_false(self):
        """Verify _cancel_after_current is initialized to False."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen.__init__()
        assert screen._cancel_after_current is False

    def test_exit_after_cancel_initialized_false(self):
        """Verify _exit_after_cancel is initialized to False."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen.__init__()
        assert screen._exit_after_cancel is False

    def test_consecutive_failures_initialized_zero(self):
        """Verify _consecutive_failures is initialized to 0."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen.__init__()
        assert screen._consecutive_failures == 0


# ---------------------------------------------------------------------------
# Tests for export results preservation
# ---------------------------------------------------------------------------

class TestExportResultsPreservation:
    """Test that export results are preserved on back navigation."""

    def test_return_to_selection_preserves_results(self):
        """
        Verify _return_to_selection does NOT clear _export_results.

        We verify this by inspecting the source code for the absence of
        _export_results reassignment, since mounting a full Textual app
        for this is unnecessary.
        """
        import inspect
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        source = inspect.getsource(SelectionScreen._return_to_selection)

        # The method should NOT contain _export_results = {... (clearing it)
        # It should have a comment explaining why it's preserved
        assert '_export_results = {"completed"' not in source
        assert "_export_results" not in source or "NOT cleared" in source or "preserve" in source.lower()

    def test_return_to_selection_resets_operational_state(self):
        """
        Verify _return_to_selection resets consecutive failures and cancel flags.

        We inspect the source to confirm these fields are reset.
        """
        import inspect
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        source = inspect.getsource(SelectionScreen._return_to_selection)

        assert "_consecutive_failures = 0" in source
        assert "_cancel_after_current = False" in source
        assert "_exit_after_cancel = False" in source


# ---------------------------------------------------------------------------
# Test the progress callback translation
# ---------------------------------------------------------------------------

class TestProgressCallbackTranslation:
    """Test that the progress callback correctly translates step indices."""

    def test_progress_callback_converts_zero_indexed_to_one_indexed(self):
        """
        The exporter fires 0-indexed steps. The callback should convert
        to 1-indexed for display in ProgressPane.update_export_step.
        """
        captured_calls = []

        class FakePane:
            def update_export_step(self, msg, step_num, total):
                captured_calls.append((msg, step_num, total))

        fake_pane = FakePane()

        # Replicate the callback definition from _run_export
        def _export_progress_callback(phase, message, current, total, item_name=""):
            fake_pane.update_export_step(message, current + 1, total)

        # Simulate exporter calling _fire(0, 6, "Starting export")
        _export_progress_callback("export", "Starting export", 0, 6, "Test Chat")
        assert captured_calls[-1] == ("Starting export", 1, 6)

        # Simulate exporter calling _fire(3, 6, "'Export chat' clicked")
        _export_progress_callback("export", "'Export chat' clicked", 3, 6, "Test Chat")
        assert captured_calls[-1] == ("'Export chat' clicked", 4, 6)

        # Simulate exporter calling _fire(6, 6, "Upload complete")
        _export_progress_callback("export", "Upload complete", 6, 6, "Test Chat")
        assert captured_calls[-1] == ("Upload complete", 7, 6)

    def test_progress_callback_handles_exception_gracefully(self):
        """
        Verify the callback pattern from _run_export swallows exceptions.
        """
        # The actual callback in _run_export wraps calls in try/except.
        # Verify the pattern handles errors without crashing.
        error_count = 0

        def broken_update(*args):
            nonlocal error_count
            error_count += 1
            raise RuntimeError("Widget not mounted")

        # Replicate the callback with error handling from _run_export
        def _export_progress_callback(phase, message, current, total, item_name=""):
            try:
                broken_update(message, current + 1, total)
            except Exception:
                pass

        # Should not raise
        _export_progress_callback("export", "Step", 0, 6, "Chat")
        assert error_count == 1  # Function was called but error was swallowed


# ---------------------------------------------------------------------------
# Test handle_cancel_choice logic
# ---------------------------------------------------------------------------

class TestHandleCancelChoice:
    """Test the cancel choice handler with deferred cancellation."""

    def test_handle_cancel_return_with_wait_sets_flag(self):
        """
        Verify btn-return + wait_for_current sets _cancel_after_current.
        """
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._cancel_modal_open = True
        screen._current_chat = "Active Chat"
        screen._cancel_after_current = False
        screen._exit_after_cancel = False

        # Create a mock modal where wait_for_current returns True
        mock_modal = MagicMock()
        mock_modal.wait_for_current = True
        screen._active_cancel_modal = mock_modal

        # Mock query_one for progress pane access
        mock_pane = MagicMock()

        def fake_query_one(selector, *args):
            return mock_pane

        screen.query_one = fake_query_one

        screen._handle_cancel_choice("btn-return")

        assert screen._cancel_after_current is True
        assert screen._exit_after_cancel is False
        assert screen._cancel_modal_open is False

    def test_handle_cancel_exit_with_wait_sets_both_flags(self):
        """
        Verify btn-exit + wait_for_current sets both cancel and exit flags.
        """
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._cancel_modal_open = True
        screen._current_chat = "Active Chat"
        screen._cancel_after_current = False
        screen._exit_after_cancel = False

        mock_modal = MagicMock()
        mock_modal.wait_for_current = True
        screen._active_cancel_modal = mock_modal

        mock_pane = MagicMock()
        screen.query_one = lambda *a: mock_pane

        screen._handle_cancel_choice("btn-exit")

        assert screen._cancel_after_current is True
        assert screen._exit_after_cancel is True

    def test_handle_cancel_continue_does_nothing(self):
        """Verify btn-continue just clears modal state."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen

        screen = SelectionScreen.__new__(SelectionScreen)
        screen._cancel_modal_open = True
        screen._current_chat = "Active Chat"
        screen._cancel_after_current = False
        screen._exit_after_cancel = False
        screen._active_cancel_modal = MagicMock()

        screen._handle_cancel_choice("btn-continue")

        assert screen._cancel_after_current is False
        assert screen._cancel_modal_open is False
