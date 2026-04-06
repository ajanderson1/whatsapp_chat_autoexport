"""
SummaryPane -- processing progress and completion results.

Handles the post-export pipeline processing (download, extract, transcribe,
build, cleanup) and displays final results with action buttons.

Flow:
1. MainScreen calls start_processing(export_results) after export completes
2. Pipeline runs in a threaded worker, updating ProgressPane via call_from_thread
3. On completion, show_results() switches to completion display with buttons
4. User can open output folder or dismiss
"""

import asyncio
import subprocess
import sys
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Button, Static
from textual.worker import Worker, WorkerState

from ..textual_widgets.activity_log import ActivityLog
from ..textual_widgets.progress_pane import ProgressPane


class SummaryPane(Container):
    """
    Processing progress and completion results.

    Layout:
        Vertical:
          ProgressPane(id="summary-progress")
          Horizontal (bottom-bar, initially hidden):
            Button "Open Output" (id="btn-open-output")
            Button "Done" (id="btn-done")

    MainScreen orchestrates via method calls -- no custom messages needed.
    """

    BINDINGS = [
        Binding("o", "open_output", "Open Output", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._export_results: dict = {}
        self._processing_worker: Optional[Worker] = None

    def compose(self) -> ComposeResult:
        yield ProgressPane(
            mode="processing",
            id="summary-progress",
        )
        with Horizontal(classes="bottom-bar"):
            yield Button("Open Output", id="btn-open-output", variant="default")
            yield Button("Done", id="btn-done", variant="success")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_processing(self, export_results: dict) -> None:
        """
        Start the post-export processing pipeline.

        Args:
            export_results: Results dict from the export phase, with keys
                "completed", "failed", "skipped".
        """
        self._export_results = export_results

        progress = self.query_one("#summary-progress", ProgressPane)
        progress.start_processing()

        self._processing_worker = self.run_worker(
            self._run_processing(),
            name="processing_worker",
            thread=True,
        )

    def show_results(self, results: dict) -> None:
        """
        Display final results and reveal action buttons.

        Args:
            results: Summary dict with keys exported, failed, transcribed,
                output_path.
        """
        progress = self.query_one("#summary-progress", ProgressPane)
        progress.set_complete(results)

        # Reveal the bottom bar
        bottom_bar = self.query_one(".bottom-bar")
        bottom_bar.add_class("visible")

    # ------------------------------------------------------------------
    # Processing worker
    # ------------------------------------------------------------------

    async def _run_processing(self) -> dict:
        """
        Run the full processing pipeline.

        Returns:
            Dictionary with processing results.
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
        transcription_provider = getattr(self.app, "transcription_provider", "whisper")

        progress = self.query_one("#summary-progress", ProgressPane)
        phases = progress.PROCESSING_PHASES

        # If no output dir, simulate phases
        if not output_dir:
            for i, phase_name in enumerate(phases):
                self.app.call_from_thread(
                    self._update_processing_phase, phase_name, i + 1,
                )
                await asyncio.sleep(1.0)
                self.app.call_from_thread(
                    self._complete_processing_phase, phase_name,
                )
            return results

        try:
            from ...pipeline import WhatsAppPipeline, PipelineConfig
            from ...utils.logger import Logger

            def _tui_log_callback(message: str, level: str) -> None:
                try:
                    self.app.call_from_thread(
                        progress.log_activity, message, level
                    )
                except Exception:
                    pass

            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode, on_message=_tui_log_callback)

            exported_chats = (
                self._export_results.get("completed", [])
                if self._export_results
                else []
            )

            config = PipelineConfig(
                output_dir=output_dir,
                download_dir=output_dir / "downloads",
                skip_download=False,
                delete_from_drive=getattr(self.app, "delete_from_drive", False),
                transcribe_audio_video=transcribe,
                include_media=include_media,
                transcription_provider=transcription_provider,
                cleanup_temp=True,
                limit=getattr(self.app, "limit", None),
                chat_names=exported_chats if exported_chats else None,
            )

            _last_phase = [None]

            def _pipeline_progress_callback(
                phase: str,
                message: str,
                current: int,
                total: int,
                item_name: str = "",
            ) -> None:
                try:
                    if phase != _last_phase[0]:
                        if _last_phase[0] is not None:
                            prev_display = progress.PHASE_DISPLAY_MAP.get(
                                _last_phase[0], _last_phase[0].title()
                            )
                            self.app.call_from_thread(
                                self._complete_processing_phase, prev_display
                            )
                        _last_phase[0] = phase
                        self.app.call_from_thread(
                            self._update_pipeline_phase, phase
                        )

                    if item_name or total > 0:
                        self.app.call_from_thread(
                            self._update_pipeline_item,
                            item_name or message,
                            current,
                            total,
                        )

                    if message:
                        self.app.call_from_thread(
                            progress.log_activity, message, "info"
                        )
                except Exception:
                    pass

            pipeline = WhatsAppPipeline(
                config, logger=logger, on_progress=_pipeline_progress_callback
            )

            self.app.call_from_thread(self._update_processing_phase, "Download", 1)
            pipeline_results = await asyncio.to_thread(
                pipeline.run, output_dir / "downloads"
            )

            if _last_phase[0] is not None:
                last_display = progress.PHASE_DISPLAY_MAP.get(
                    _last_phase[0], _last_phase[0].title()
                )
                self.app.call_from_thread(
                    self._complete_processing_phase, last_display
                )

            results["downloaded"] = (
                1 if "download" in pipeline_results.get("phases_completed", []) else 0
            )
            results["extracted"] = (
                1 if "extract" in pipeline_results.get("phases_completed", []) else 0
            )
            results["transcribed"] = (
                1 if "transcribe" in pipeline_results.get("phases_completed", []) else 0
            )
            results["output_files"] = len(
                pipeline_results.get("outputs_created", [])
            )
            results["errors"] = pipeline_results.get("errors", [])

            for phase_name in ["Download", "Extract", "Transcribe", "Build", "Cleanup"]:
                self.app.call_from_thread(self._complete_processing_phase, phase_name)

        except Exception as e:
            results["errors"].append(str(e))
            self.app.call_from_thread(self._log_processing_error, str(e))

        return results

    # ------------------------------------------------------------------
    # Progress helpers (called on main thread via call_from_thread)
    # ------------------------------------------------------------------

    def _update_processing_phase(
        self, phase_name_or_key: str, phase_num: int = 0
    ) -> None:
        progress = self.query_one("#summary-progress", ProgressPane)
        if phase_num > 0:
            progress.update_processing_progress(
                phase=phase_name_or_key, phase_num=phase_num
            )
            progress.log_activity(f"Starting: {phase_name_or_key}", "info")
        else:
            progress.update_pipeline_phase(phase_name_or_key)

    def _update_pipeline_phase(self, phase_key: str) -> None:
        progress = self.query_one("#summary-progress", ProgressPane)
        progress.update_pipeline_phase(phase_key)

    def _update_pipeline_item(
        self, item_name: str, current: int, total: int
    ) -> None:
        progress = self.query_one("#summary-progress", ProgressPane)
        progress.update_pipeline_item(item_name, current, total)

    def _complete_processing_phase(self, phase_name: str) -> None:
        progress = self.query_one("#summary-progress", ProgressPane)
        progress.complete_phase(phase_name)

    def _log_processing_error(self, error: str) -> None:
        progress = self.query_one("#summary-progress", ProgressPane)
        progress.log_activity(f"Error: {error}", "error")

    # ------------------------------------------------------------------
    # Worker state handling
    # ------------------------------------------------------------------

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes for the processing worker."""
        worker = event.worker

        if worker.state == WorkerState.CANCELLED:
            return

        if (
            worker.name == "processing_worker"
            and worker.state in (WorkerState.SUCCESS, WorkerState.ERROR)
        ):
            processing_results = worker.result if worker.result else {}
            self._handle_processing_complete(processing_results)

    def _handle_processing_complete(self, processing_results: dict) -> None:
        """Finalize the completion state after processing."""
        summary = {
            "exported": len(self._export_results.get("completed", [])),
            "failed": len(self._export_results.get("failed", [])),
            "transcribed": processing_results.get("transcribed", 0),
            "output_path": (
                str(self.app.output_dir) if self.app.output_dir else ""
            ),
        }
        self.show_results(summary)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_output(self) -> None:
        """Open the output folder in the system file manager."""
        if self.app.output_dir:
            if sys.platform == "darwin":
                subprocess.run(
                    ["open", str(self.app.output_dir)], close_fds=True
                )
            elif sys.platform == "linux":
                subprocess.run(
                    ["xdg-open", str(self.app.output_dir)], close_fds=True
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-open-output":
            self.action_open_output()
        elif event.button.id == "btn-done":
            self.app.exit()
