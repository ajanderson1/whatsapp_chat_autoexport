"""
Tests for SelectionScreen processing mode pipeline progress wiring.

Verifies that:
- The progress callback is passed to WhatsAppPipeline
- ProgressPane has the required update methods for pipeline progress
- Phase transitions are tracked correctly
- Per-item progress is forwarded to the ProgressPane
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock, call
from pathlib import Path


# ---------------------------------------------------------------------------
# ProgressPane unit tests (no Textual app needed)
# ---------------------------------------------------------------------------

class TestProgressPanePipelineMethods:
    """Test that ProgressPane has the required methods and phase mapping."""

    def _make_pane(self):
        """Create a ProgressPane instance with mocked mounting."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import (
            ProgressPane,
        )

        pane = ProgressPane(mode="processing")
        # Prevent actual widget queries (not mounted)
        pane._is_mounted = False
        return pane

    def test_has_update_pipeline_phase_method(self):
        """ProgressPane exposes update_pipeline_phase()."""
        pane = self._make_pane()
        assert callable(getattr(pane, "update_pipeline_phase", None))

    def test_has_update_pipeline_item_method(self):
        """ProgressPane exposes update_pipeline_item()."""
        pane = self._make_pane()
        assert callable(getattr(pane, "update_pipeline_item", None))

    def test_phase_display_map_covers_pipeline_phases(self):
        """PHASE_DISPLAY_MAP maps all pipeline phase keys to display names."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import (
            ProgressPane,
        )

        expected_keys = {"download", "extract", "transcribe", "build_output", "organize", "cleanup"}
        assert expected_keys.issubset(set(ProgressPane.PHASE_DISPLAY_MAP.keys()))

    def test_phase_display_map_values_in_processing_phases(self):
        """All PHASE_DISPLAY_MAP values are valid PROCESSING_PHASES entries."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import (
            ProgressPane,
        )

        for display_name in ProgressPane.PHASE_DISPLAY_MAP.values():
            assert display_name in ProgressPane.PROCESSING_PHASES, (
                f"{display_name!r} not in PROCESSING_PHASES"
            )

    def test_update_pipeline_phase_sets_current_phase(self):
        """update_pipeline_phase() sets current_phase to the display name."""
        pane = self._make_pane()
        pane.update_pipeline_phase("transcribe")
        assert pane.current_phase == "Transcribe"

    def test_update_pipeline_phase_sets_phase_number(self):
        """update_pipeline_phase() sets phase_number based on PROCESSING_PHASES index."""
        pane = self._make_pane()
        pane.update_pipeline_phase("extract")
        # "Extract" is at index 1 in PROCESSING_PHASES, so phase_number = 2 (1-indexed)
        assert pane.phase_number == 2

    def test_update_pipeline_phase_resets_item_progress(self):
        """update_pipeline_phase() clears per-item progress from previous phase."""
        pane = self._make_pane()
        # Simulate item progress from a previous phase
        pane.pipeline_item = "some_file.opus"
        pane.pipeline_item_current = 5
        pane.pipeline_item_total = 10

        pane.update_pipeline_phase("cleanup")

        assert pane.pipeline_item == ""
        assert pane.pipeline_item_current == 0
        assert pane.pipeline_item_total == 0

    def test_update_pipeline_phase_build_output_maps_to_build(self):
        """'build_output' maps to 'Build' display name."""
        pane = self._make_pane()
        pane.update_pipeline_phase("build_output")
        assert pane.current_phase == "Build"
        assert pane.phase_number == 4  # Build is index 3, so 1-indexed = 4

    def test_update_pipeline_phase_organize_maps_to_build(self):
        """'organize' maps to 'Build' display name (alias)."""
        pane = self._make_pane()
        pane.update_pipeline_phase("organize")
        assert pane.current_phase == "Build"

    def test_update_pipeline_item_sets_all_fields(self):
        """update_pipeline_item() sets item name, current, and total."""
        pane = self._make_pane()
        pane.update_pipeline_item("PTT-001.opus", 3, 10)

        assert pane.pipeline_item == "PTT-001.opus"
        assert pane.pipeline_item_current == 3
        assert pane.pipeline_item_total == 10

    def test_complete_phase_clears_item_progress(self):
        """complete_phase() resets per-item progress."""
        pane = self._make_pane()
        pane.pipeline_item = "file.opus"
        pane.pipeline_item_current = 5
        pane.pipeline_item_total = 10

        pane.complete_phase("Transcribe")

        assert pane.pipeline_item == ""
        assert pane.pipeline_item_current == 0
        assert pane.pipeline_item_total == 0

    def test_start_processing_resets_state(self):
        """start_processing() resets phase and mode."""
        pane = self._make_pane()
        pane.mode = "export"
        pane.phase_number = 3
        pane.current_phase = "Transcribe"

        pane.start_processing()

        assert pane.mode == "processing"
        assert pane.phase_number == 0
        assert pane.current_phase == ""


# ---------------------------------------------------------------------------
# Phase transition tracking tests
# ---------------------------------------------------------------------------

class TestPhaseTransitionTracking:
    """Test that phase transitions happen correctly during progress callbacks."""

    def test_sequential_phase_transitions(self):
        """Phases progress in order: download -> extract -> transcribe -> build -> cleanup."""
        pane = self._make_pane()

        phases_in_order = ["download", "extract", "transcribe", "build_output", "cleanup"]
        expected_numbers = [1, 2, 3, 4, 5]

        for phase_key, expected_num in zip(phases_in_order, expected_numbers):
            pane.update_pipeline_phase(phase_key)
            assert pane.phase_number == expected_num, (
                f"Phase {phase_key!r} should be number {expected_num}, got {pane.phase_number}"
            )

    def _make_pane(self):
        """Create a ProgressPane instance with mocked mounting."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import (
            ProgressPane,
        )

        pane = ProgressPane(mode="processing")
        pane._is_mounted = False
        return pane


# ---------------------------------------------------------------------------
# Pipeline progress callback wiring tests (mock-based)
# ---------------------------------------------------------------------------

class TestPipelineProgressCallbackWiring:
    """Test that _run_processing wires the on_progress callback to WhatsAppPipeline."""

    def test_pipeline_receives_on_progress_callback(self):
        """WhatsAppPipeline stores the on_progress callback passed at init."""
        from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

        cb = MagicMock()
        config = PipelineConfig(
            skip_download=True,
            dry_run=True,
            output_dir=Path("/tmp/test"),
        )
        pipeline = WhatsAppPipeline(config=config, on_progress=cb)

        assert pipeline.on_progress is cb

    def test_pipeline_init_accepts_on_progress_kwarg(self):
        """WhatsAppPipeline.__init__ accepts on_progress parameter."""
        from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

        config = PipelineConfig(
            skip_download=True,
            dry_run=True,
            output_dir=Path("/tmp/test"),
        )

        # Should not raise
        pipeline = WhatsAppPipeline(config=config, on_progress=lambda *a, **kw: None)
        assert pipeline.on_progress is not None

    def test_pipeline_fire_progress_forwards_to_callback(self):
        """Pipeline._fire_progress invokes the callback with all arguments."""
        from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, message, current, total, item_name))

        config = PipelineConfig(
            skip_download=True,
            dry_run=True,
            output_dir=Path("/tmp/test"),
        )
        pipeline = WhatsAppPipeline(config=config, on_progress=recorder)

        pipeline._fire_progress("transcribe", "Transcribing file", 2, 10, "PTT-001.opus")

        assert len(events) == 1
        assert events[0] == ("transcribe", "Transcribing file", 2, 10, "PTT-001.opus")


# ---------------------------------------------------------------------------
# SelectionScreen helper method tests
# ---------------------------------------------------------------------------

class TestSelectionScreenProcessingHelpers:
    """Test the helper methods on SelectionScreen used by the progress callback."""

    def _make_screen_with_mocked_pane(self):
        """Create a SelectionScreen with a mocked ProgressPane query."""
        from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import (
            SelectionScreen,
        )

        screen = SelectionScreen.__new__(SelectionScreen)
        mock_pane = MagicMock()
        mock_pane.PHASE_DISPLAY_MAP = {
            "download": "Download",
            "extract": "Extract",
            "transcribe": "Transcribe",
            "build_output": "Build",
            "organize": "Build",
            "cleanup": "Cleanup",
        }
        mock_pane.PROCESSING_PHASES = ["Download", "Extract", "Transcribe", "Build", "Cleanup"]

        # Mock query_one to return our mock pane
        screen.query_one = MagicMock(return_value=mock_pane)

        return screen, mock_pane

    def test_update_pipeline_phase_delegates_to_pane(self):
        """_update_pipeline_phase calls pane.update_pipeline_phase()."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._update_pipeline_phase("transcribe")
        mock_pane.update_pipeline_phase.assert_called_once_with("transcribe")

    def test_update_pipeline_item_delegates_to_pane(self):
        """_update_pipeline_item calls pane.update_pipeline_item()."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._update_pipeline_item("PTT-001.opus", 3, 10)
        mock_pane.update_pipeline_item.assert_called_once_with("PTT-001.opus", 3, 10)

    def test_complete_processing_phase_delegates_to_pane(self):
        """_complete_processing_phase calls pane.complete_phase()."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._complete_processing_phase("Download")
        mock_pane.complete_phase.assert_called_once_with("Download")

    def test_log_processing_error_delegates_to_pane(self):
        """_log_processing_error calls pane.log_activity with error level."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._log_processing_error("Something broke")
        mock_pane.log_activity.assert_called_once_with("Error: Something broke", "error")

    def test_update_processing_phase_with_explicit_number(self):
        """_update_processing_phase with phase_num > 0 uses legacy path."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._update_processing_phase("Download", 1)
        mock_pane.update_processing_progress.assert_called_once_with(
            phase="Download", phase_num=1
        )
        mock_pane.log_activity.assert_called_once_with("Starting: Download", "info")

    def test_update_processing_phase_without_number_uses_pipeline_key(self):
        """_update_processing_phase with phase_num=0 uses update_pipeline_phase."""
        screen, mock_pane = self._make_screen_with_mocked_pane()
        screen._update_processing_phase("extract")
        mock_pane.update_pipeline_phase.assert_called_once_with("extract")


# ---------------------------------------------------------------------------
# Progress callback closure behavior tests
# ---------------------------------------------------------------------------

class TestProgressCallbackBehavior:
    """Test the callback closure logic that would be built in _run_processing."""

    def test_callback_tracks_phase_transitions(self):
        """
        Simulates the callback closure behavior: phase changes should trigger
        _update_pipeline_phase calls and complete the previous phase.
        """
        # Track calls that would happen through call_from_thread
        update_phase_calls = []
        complete_phase_calls = []
        update_item_calls = []
        log_calls = []

        phase_display_map = {
            "download": "Download",
            "extract": "Extract",
            "transcribe": "Transcribe",
            "build_output": "Build",
            "cleanup": "Cleanup",
        }

        # Simulate the closure from _run_processing
        _last_phase = [None]

        def simulate_callback(phase, message, current, total, item_name=""):
            if phase != _last_phase[0]:
                if _last_phase[0] is not None:
                    prev_display = phase_display_map.get(
                        _last_phase[0], _last_phase[0].title()
                    )
                    complete_phase_calls.append(prev_display)
                _last_phase[0] = phase
                update_phase_calls.append(phase)

            if item_name or total > 0:
                update_item_calls.append((item_name or message, current, total))

            if message:
                log_calls.append(message)

        # Simulate pipeline firing progress events
        simulate_callback("download", "Starting download", 0, 1)
        simulate_callback("download", "Download complete", 1, 1)
        simulate_callback("extract", "Extracting archives", 0, 3)
        simulate_callback("extract", "Extracting", 1, 3, "archive1.zip")
        simulate_callback("extract", "Extracting", 2, 3, "archive2.zip")
        simulate_callback("extract", "Extracting", 3, 3, "archive3.zip")
        simulate_callback("transcribe", "Starting transcription", 0, 5)
        simulate_callback("transcribe", "Transcribing", 1, 5, "PTT-001.opus")
        simulate_callback("transcribe", "Transcribing", 2, 5, "PTT-002.opus")

        # Verify phase transitions
        assert update_phase_calls == ["download", "extract", "transcribe"]

        # Verify previous phases were completed
        assert complete_phase_calls == ["Download", "Extract"]

        # Verify item updates (all calls where item_name or total > 0)
        assert len(update_item_calls) == 9
        # archive2.zip is the 5th item update (index 4)
        assert update_item_calls[4] == ("archive2.zip", 2, 3)
        # PTT-002.opus is the last item update (index 8)
        assert update_item_calls[8] == ("PTT-002.opus", 2, 5)

    def test_callback_handles_unknown_phase_gracefully(self):
        """Callback does not crash on unknown phase keys."""
        from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import (
            ProgressPane,
        )

        pane = ProgressPane(mode="processing")
        pane._is_mounted = False

        # Unknown phase should not raise, should use title-cased key
        pane.update_pipeline_phase("unknown_phase")
        assert pane.current_phase == "Unknown_Phase"
        # phase_number stays at current since lookup fails
        assert pane.phase_number == 0


# ---------------------------------------------------------------------------
# Error handling in progress callback
# ---------------------------------------------------------------------------

class TestProgressCallbackErrorHandling:
    """Test that errors in the progress callback do not crash the pipeline."""

    def test_pipeline_fire_progress_swallows_callback_errors(self):
        """_fire_progress catches exceptions from the callback."""
        from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

        def bad_callback(*args, **kwargs):
            raise RuntimeError("UI thread died")

        config = PipelineConfig(
            skip_download=True,
            dry_run=True,
            output_dir=Path("/tmp/test"),
        )
        pipeline = WhatsAppPipeline(config=config, on_progress=bad_callback)

        # Should not raise
        pipeline._fire_progress("transcribe", "test", 1, 5, "file.opus")
