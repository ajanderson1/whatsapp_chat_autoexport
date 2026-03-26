"""
Processing screen for post-export operations.

This is the fourth screen in the pipeline:
1. Download from Google Drive
2. Extract archives
3. Transcribe audio/video
4. Build final output
5. Cleanup
"""

import asyncio
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, ProgressBar
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from whatsapp_chat_autoexport.tui.textual_widgets.pipeline_header import PipelineHeader
from whatsapp_chat_autoexport.tui.textual_widgets.activity_log import ActivityLog
from whatsapp_chat_autoexport.tui.textual_app import PipelineStage


class ProcessingScreen(Screen):
    """
    Processing screen for post-export operations.

    Shows progress through:
    - Download from Google Drive
    - Archive extraction
    - Audio/video transcription
    - Final output organization
    - Cleanup
    """

    PROCESSING_PHASES = [
        ("download", "Downloading from Google Drive"),
        ("extract", "Extracting archives"),
        ("transcribe", "Transcribing audio/video"),
        ("output", "Building final output"),
        ("cleanup", "Cleaning up temporary files"),
    ]

    def __init__(self, **kwargs) -> None:
        """Initialize the processing screen."""
        super().__init__(**kwargs)
        self._current_phase = 0
        self._processing_worker: Optional[Worker] = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield PipelineHeader()
        with Container(classes="progress-section"):
            yield Static("[bold]POST-EXPORT PROCESSING[/bold]", classes="section-title")
            yield Static("", id="current-phase")
            yield ProgressBar(id="phase-progress", total=100, show_eta=False)
            yield Static("", id="phase-steps")
        with Container(classes="log-section"):
            yield ActivityLog(title="PROCESSING LOG", id="activity-log")
        with Horizontal(classes="control-bar"):
            yield Static("[dim]Processing...[/dim]", id="status-text")
            yield Button("Cancel", id="btn-cancel", variant="error", disabled=True)

    async def on_mount(self) -> None:
        """Start processing when mounted."""
        # Set the pipeline header stage
        header = self.query_one(PipelineHeader)
        header.set_stage(PipelineStage.PROCESS)

        activity = self.query_one(ActivityLog)
        activity.log_info("Starting post-export processing...")

        # Update phase display
        self._update_phase_display()

        # Start processing
        self._processing_worker = self.run_worker(
            self._run_processing(),
            name="processing_worker",
            thread=True,
        )

    def _update_phase_display(self) -> None:
        """Update the phase display."""
        phase_label = self.query_one("#current-phase", Static)
        steps_label = self.query_one("#phase-steps", Static)

        # Build phase steps display
        lines = []
        for i, (phase_id, phase_name) in enumerate(self.PROCESSING_PHASES):
            if i < self._current_phase:
                lines.append(f"  [green]✓[/green] {phase_name}")
            elif i == self._current_phase:
                lines.append(f"  [yellow bold]●[/yellow bold] [yellow]{phase_name}[/yellow]")
            else:
                lines.append(f"  [dim]○ {phase_name}[/dim]")

        steps_label.update("\n".join(lines))

        # Update current phase label
        if self._current_phase < len(self.PROCESSING_PHASES):
            _, phase_name = self.PROCESSING_PHASES[self._current_phase]
            phase_label.update(f"Current: [cyan]{phase_name}[/cyan]")
        else:
            phase_label.update("[green]Processing complete![/green]")

        # Update progress bar
        progress = self.query_one("#phase-progress", ProgressBar)
        percentage = (self._current_phase / len(self.PROCESSING_PHASES)) * 100
        progress.update(progress=percentage)

    async def _run_processing(self) -> dict:
        """
        Run the full processing pipeline.

        Returns:
            Dictionary with processing results
        """
        results = {
            "downloaded": 0,
            "extracted": 0,
            "transcribed": 0,
            "output_files": 0,
            "errors": [],
        }

        output_dir = self.app.output_dir
        transcribe = self.app.transcribe_audio
        include_media = self.app.include_media

        # If no output dir, just simulate
        if not output_dir:
            for i in range(len(self.PROCESSING_PHASES)):
                self._current_phase = i
                self.app.call_from_thread(self._update_phase_display)
                self.app.call_from_thread(
                    self._log_phase_start,
                    self.PROCESSING_PHASES[i][1],
                )
                await asyncio.sleep(1.0)  # Simulate work
                self.app.call_from_thread(
                    self._log_phase_complete,
                    self.PROCESSING_PHASES[i][1],
                )

            self._current_phase = len(self.PROCESSING_PHASES)
            self.app.call_from_thread(self._update_phase_display)
            return results

        try:
            # Phase 1: Download from Google Drive
            self._current_phase = 0
            self.app.call_from_thread(self._update_phase_display)
            self.app.call_from_thread(self._log_phase_start, "Downloading from Google Drive")

            # Use pipeline for actual processing
            from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

            config = PipelineConfig(
                output_dir=Path(output_dir),
                transcribe_audio_video=transcribe,
                include_media=include_media,
                skip_download=False,
                limit=getattr(self.app, "limit", None),
            )

            pipeline = WhatsAppPipeline(config)

            # Run the full pipeline (handles all phases internally)
            pipeline_result = await asyncio.to_thread(pipeline.run)

            # Update phase display based on completed phases
            phases_completed = pipeline_result.get("phases_completed", [])

            # Phase 1: Download
            if "download" in phases_completed:
                results["downloaded"] = 1
            self.app.call_from_thread(
                self._log_phase_complete,
                f"Download phase {'complete' if 'download' in phases_completed else 'skipped'}",
            )

            # Phase 2: Extract
            self._current_phase = 1
            self.app.call_from_thread(self._update_phase_display)
            if "extract" in phases_completed:
                results["extracted"] = 1
            self.app.call_from_thread(
                self._log_phase_complete,
                f"Extract phase {'complete' if 'extract' in phases_completed else 'skipped'}",
            )

            # Phase 3: Transcribe
            self._current_phase = 2
            self.app.call_from_thread(self._update_phase_display)
            if "transcribe" in phases_completed:
                results["transcribed"] = 1
                self.app.call_from_thread(self._log_phase_complete, "Transcription complete")
            else:
                self.app.call_from_thread(self._log_info, "Transcription skipped")

            # Phase 4: Build output
            self._current_phase = 3
            self.app.call_from_thread(self._update_phase_display)
            results["output_files"] = len(pipeline_result.get("outputs_created", []))
            self.app.call_from_thread(
                self._log_phase_complete,
                f"Created {results['output_files']} output files",
            )

            # Phase 5: Cleanup
            self._current_phase = 4
            self.app.call_from_thread(self._update_phase_display)
            self.app.call_from_thread(self._log_phase_complete, "Cleanup complete")

        except Exception as e:
            results["errors"].append(str(e))
            self.app.call_from_thread(self._log_error, f"Processing error: {e}")

        # Mark complete
        self._current_phase = len(self.PROCESSING_PHASES)
        self.app.call_from_thread(self._update_phase_display)

        return results

    def _log_phase_start(self, phase_name: str) -> None:
        """Log phase start."""
        activity = self.query_one(ActivityLog)
        activity.log_info(f"Starting: {phase_name}")

    def _log_phase_complete(self, message: str) -> None:
        """Log phase completion."""
        activity = self.query_one(ActivityLog)
        activity.log_success(message)

    def _log_info(self, message: str) -> None:
        """Log info message."""
        activity = self.query_one(ActivityLog)
        activity.log(message)

    def _log_error(self, message: str) -> None:
        """Log error message."""
        activity = self.query_one(ActivityLog)
        activity.log_error(message)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        worker = event.worker
        is_finished = worker.state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)

        if worker.name == "processing_worker" and is_finished:
            results = worker.result
            self._handle_processing_complete(results)

    def _handle_processing_complete(self, results: dict) -> None:
        """Handle processing completion."""
        activity = self.query_one(ActivityLog)
        status = self.query_one("#status-text", Static)

        activity.log_info("=" * 40)
        activity.log_info("Processing Complete!")

        if results.get("downloaded"):
            activity.log(f"  Downloaded: {results['downloaded']}")
        if results.get("extracted"):
            activity.log(f"  Extracted: {results['extracted']}")
        if results.get("transcribed"):
            activity.log(f"  Transcribed: {results['transcribed']}")
        if results.get("output_files"):
            activity.log(f"  Output files: {results['output_files']}")

        errors = results.get("errors", [])
        if errors:
            activity.log_error(f"Errors: {len(errors)}")
            for error in errors[:5]:  # Show first 5 errors
                activity.log_error(f"  - {error}")

        if self.app.output_dir:
            activity.log_success(f"Output saved to: {self.app.output_dir}")

        status.update("[green]Processing complete! Press Q to quit.[/green]")

        # Update cancel button to done (keep same ID, just change appearance)
        cancel_btn = self.query_one("#btn-cancel", Button)
        cancel_btn.label = "Done"
        cancel_btn.variant = "success"
        cancel_btn.disabled = False
        # Note: Cannot change widget ID after creation in Textual

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-cancel":
            # If label is "Done", exit; otherwise cancel (not fully implemented)
            if event.button.label == "Done":
                self.app.exit()
            else:
                pass  # Cancel processing
