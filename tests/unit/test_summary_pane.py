"""Tests for SummaryPane widget."""

import pytest
from textual.containers import Container

from whatsapp_chat_autoexport.tui.textual_panes.summary_pane import SummaryPane
from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import ProgressPane


class TestSummaryPaneStructure:
    """Test SummaryPane class structure and composition."""

    def test_summary_pane_is_container_subclass(self):
        """SummaryPane should be a Container subclass."""
        assert issubclass(SummaryPane, Container)

    def test_summary_pane_composes_with_progress_pane(self):
        """SummaryPane.compose() should reference a ProgressPane with id summary-progress."""
        import inspect

        source = inspect.getsource(SummaryPane.compose)
        assert "ProgressPane" in source
        assert "summary-progress" in source

    def test_start_processing_method_exists(self):
        """SummaryPane should have a start_processing method."""
        pane = SummaryPane()
        assert hasattr(pane, "start_processing")
        assert callable(pane.start_processing)

    def test_show_results_method_exists(self):
        """SummaryPane should have a show_results method."""
        pane = SummaryPane()
        assert hasattr(pane, "show_results")
        assert callable(pane.show_results)

    def test_compose_yields_bottom_bar_with_buttons(self):
        """SummaryPane.compose() should include Open Output and Done buttons."""
        import inspect

        source = inspect.getsource(SummaryPane.compose)
        assert "btn-open-output" in source
        assert "btn-done" in source
        assert "bottom-bar" in source
        assert "Open Output" in source
        assert "Done" in source

    def test_start_processing_stores_export_results(self):
        """start_processing should store export_results for later use."""
        pane = SummaryPane()
        # We can't fully call start_processing without a mounted app,
        # but we can verify the attribute is initialised properly.
        assert pane._export_results == {}

    def test_action_open_output_method_exists(self):
        """SummaryPane should have an action_open_output method."""
        pane = SummaryPane()
        assert hasattr(pane, "action_open_output")
        assert callable(pane.action_open_output)

    def test_on_button_pressed_method_exists(self):
        """SummaryPane should handle button pressed events."""
        pane = SummaryPane()
        assert hasattr(pane, "on_button_pressed")
        assert callable(pane.on_button_pressed)

    def test_on_worker_state_changed_method_exists(self):
        """SummaryPane should handle worker state changed events."""
        pane = SummaryPane()
        assert hasattr(pane, "on_worker_state_changed")
        assert callable(pane.on_worker_state_changed)

    def test_progress_pane_initialised_in_processing_mode(self):
        """The ProgressPane inside SummaryPane should be created in processing mode."""
        import inspect

        source = inspect.getsource(SummaryPane.compose)
        # Verify the ProgressPane is created with mode="processing"
        assert 'mode="processing"' in source


class TestSummaryPaneCancelButton:
    """Tests for SummaryPane cancel button (R8, R9)."""

    def test_cancelled_flag_defaults_false(self):
        """_cancelled flag should default to False."""
        pane = SummaryPane()
        assert pane._cancelled is False

    def test_cancel_button_in_compose(self):
        """SummaryPane.compose() should include a Cancel button."""
        import inspect

        source = inspect.getsource(SummaryPane.compose)
        assert "btn-cancel-processing" in source
        assert 'variant="error"' in source

    def test_cancel_processing_method_exists(self):
        """SummaryPane should have a _cancel_processing method."""
        pane = SummaryPane()
        assert hasattr(pane, "_cancel_processing")
        assert callable(pane._cancel_processing)

    def test_cancel_processing_noop_when_no_worker(self):
        """_cancel_processing should be a no-op when _processing_worker is None."""
        pane = SummaryPane()
        assert pane._processing_worker is None
        # Should not raise
        pane._cancel_processing()

    def test_show_results_accepts_cancelled_param(self):
        """show_results should accept a cancelled keyword argument."""
        import inspect

        sig = inspect.signature(SummaryPane.show_results)
        assert "cancelled" in sig.parameters
