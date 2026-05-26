"""
Export screen for displaying export progress.

This is the third screen in the pipeline:
1. Show overall progress
2. Show per-chat export steps
3. Show queue with status
4. Show activity log
5. Support pause/resume
"""

import asyncio
from typing import List, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from whatsapp_chat_autoexport.tui.textual_widgets.pipeline_header import PipelineHeader
from whatsapp_chat_autoexport.tui.textual_widgets.progress_display import ProgressDisplay
from whatsapp_chat_autoexport.tui.textual_widgets.queue_widget import QueueWidget
from whatsapp_chat_autoexport.tui.textual_widgets.activity_log import ActivityLog
from whatsapp_chat_autoexport.tui.textual_app import PipelineStage
from whatsapp_chat_autoexport.state.models import ChatStatus, ChatState


class ExportScreen(Screen):
    """
    Export screen showing real-time export progress.

    Layout:
    - Top: Progress display with steps
    - Middle: Queue and Activity log side by side
    - Bottom: Control bar with pause/resume
    """

    BINDINGS = [
        Binding("p", "toggle_pause", "Pause/Resume", show=True),
        Binding("s", "skip_current", "Skip", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        """Initialize the export screen."""
        super().__init__(**kwargs)
        self._paused = False
        self._current_chat: Optional[str] = None
        self._export_worker: Optional[Worker] = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield PipelineHeader()
        with Container(classes="top-section"):
            yield ProgressDisplay(title="EXPORT PROGRESS", id="progress-display")
        with Container(classes="middle-section"):
            with Vertical(classes="queue-section"):
                yield QueueWidget(title="EXPORT QUEUE", id="queue-widget")
            with Vertical(classes="activity-section"):
                yield ActivityLog(title="ACTIVITY", id="activity-log")
        with Horizontal(classes="control-bar"):
            yield Static("[dim]P Pause | S Skip | Q Quit[/dim]", id="control-hints")
            yield Button("Pause", id="btn-pause", variant="warning")

    async def on_mount(self) -> None:
        """Start export when mounted."""
        # Set the pipeline header stage
        header = self.query_one(PipelineHeader)
        header.set_stage(PipelineStage.PROCESS)

        # Initialize displays
        selected_chats = self.app.selected_chats
        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.start(len(selected_chats))

        activity = self.query_one(ActivityLog)
        activity.log_info(f"Starting export of {len(selected_chats)} chats")

        # Initialize queue with ChatState objects
        queue = self.query_one("#queue-widget", QueueWidget)
        chat_states = [
            ChatState(name=name, status=ChatStatus.PENDING)
            for name in selected_chats
        ]
        queue.update_queue(chat_states)

        # Start export in background
        self._export_worker = self.run_worker(
            self._run_export(selected_chats),
            name="export_worker",
            thread=True,
        )

    async def _run_export(self, chats: List[str]) -> dict:
        """
        Run the export process for all selected chats.

        Args:
            chats: List of chat names to export

        Returns:
            Dictionary with results summary
        """
        results = {
            "completed": [],
            "failed": [],
            "skipped": [],
        }

        driver = self.app.driver
        include_media = self.app.include_media

        for i, chat_name in enumerate(chats):
            # Check for pause
            while self._paused:
                await asyncio.sleep(0.5)

            # Update progress
            self.app.call_from_thread(self._start_chat_export, chat_name)

            try:
                if driver:
                    # Real export using the driver's methods
                    success = await asyncio.to_thread(
                        self._export_single_chat,
                        driver,
                        chat_name,
                        include_media,
                    )

                    if success:
                        results["completed"].append(chat_name)
                        self.app.call_from_thread(self._complete_chat_export, chat_name)
                    else:
                        results["failed"].append(chat_name)
                        self.app.call_from_thread(
                            self._fail_chat_export,
                            chat_name,
                            "Export failed",
                        )
                else:
                    # Dry run - simulate export
                    for step_idx in range(7):
                        if self._paused:
                            while self._paused:
                                await asyncio.sleep(0.5)

                        self.app.call_from_thread(self._update_step, chat_name, step_idx)
                        await asyncio.sleep(0.3)  # Simulate work

                    results["completed"].append(chat_name)
                    self.app.call_from_thread(self._complete_chat_export, chat_name)

            except Exception as e:
                results["failed"].append(chat_name)
                self.app.call_from_thread(self._fail_chat_export, chat_name, str(e))

        return results

    def _export_single_chat(self, driver, chat_name: str, include_media: bool) -> bool:
        """
        Export a single chat to Google Drive.

        Args:
            driver: WhatsApp driver instance
            chat_name: Name of chat to export
            include_media: Whether to include media

        Returns:
            True if successful, False otherwise
        """
        from whatsapp_chat_autoexport.utils.logger import Logger
        from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter
        import time

        # Create logger
        debug_mode = getattr(self.app, "debug_mode", False)
        logger = Logger(debug=debug_mode)

        # Create exporter with required logger
        exporter = ChatExporter(driver, logger)

        try:
            # Verify WhatsApp is accessible
            if not driver.verify_whatsapp_is_open():
                logger.error(f"WhatsApp not accessible - cannot export '{chat_name}'")
                return False

            # Navigate to main screen
            driver.navigate_to_main()
            time.sleep(0.3)

            # Click into the chat
            if not driver.click_chat(chat_name):
                logger.warning(f"Could not open chat '{chat_name}'")
                return False

            # Export the chat to Google Drive
            success = exporter.export_chat_to_google_drive(chat_name, include_media=include_media)

            # Navigate back to main screen
            driver.navigate_back_to_main()

            return success

        except Exception as e:
            logger.error(f"Error exporting '{chat_name}': {e}")
            try:
                driver.navigate_back_to_main()
            except Exception:
                pass
            return False

    def _start_chat_export(self, chat_name: str) -> None:
        """Update UI when starting a chat export."""
        self._current_chat = chat_name

        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.start_item(chat_name)

        queue = self.query_one("#queue-widget", QueueWidget)
        queue.update_chat(chat_name, status=ChatStatus.IN_PROGRESS)

        activity = self.query_one(ActivityLog)
        activity.log_chat_start(chat_name)

    def _update_step(self, chat_name: str, step_idx: int) -> None:
        """Update UI with current step."""
        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.advance_step(step_idx)

        queue = self.query_one("#queue-widget", QueueWidget)
        queue.update_chat(chat_name, step=progress._steps[step_idx] if step_idx < len(progress._steps) else "")

        activity = self.query_one(ActivityLog)
        if step_idx < len(progress._steps):
            activity.log_step(chat_name, progress._steps[step_idx])

    def _complete_chat_export(self, chat_name: str) -> None:
        """Update UI when a chat export completes."""
        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.complete_item()

        queue = self.query_one("#queue-widget", QueueWidget)
        queue.update_chat(chat_name, status=ChatStatus.COMPLETED)

        activity = self.query_one(ActivityLog)
        activity.log_chat_complete(chat_name)

        self._current_chat = None

    def _fail_chat_export(self, chat_name: str, error: str) -> None:
        """Update UI when a chat export fails."""
        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.fail_item()

        queue = self.query_one("#queue-widget", QueueWidget)
        queue.update_chat(chat_name, status=ChatStatus.FAILED, error=error)

        activity = self.query_one(ActivityLog)
        activity.log_chat_failed(chat_name, error)

        self._current_chat = None

    def _skip_chat_export(self, chat_name: str, reason: str) -> None:
        """Update UI when a chat is skipped."""
        progress = self.query_one("#progress-display", ProgressDisplay)
        progress.skip_item()

        queue = self.query_one("#queue-widget", QueueWidget)
        queue.update_chat(chat_name, status=ChatStatus.SKIPPED, error=reason)

        activity = self.query_one(ActivityLog)
        activity.log_chat_skipped(chat_name, reason)

        self._current_chat = None

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        worker = event.worker
        is_finished = worker.state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)

        if worker.name == "export_worker" and is_finished:
            results = worker.result
            self._handle_export_complete(results)

    def _handle_export_complete(self, results: dict) -> None:
        """Handle export completion."""
        activity = self.query_one(ActivityLog)

        completed = len(results.get("completed", []))
        failed = len(results.get("failed", []))
        skipped = len(results.get("skipped", []))

        activity.log_info("=" * 40)
        activity.log_info("Export Complete")
        activity.log_success(f"Completed: {completed}")
        if failed:
            activity.log_error(f"Failed: {failed}")
        if skipped:
            activity.log_warning(f"Skipped: {skipped}")

        # Update button to continue (keep same ID, just change appearance)
        pause_btn = self.query_one("#btn-pause", Button)
        pause_btn.label = "Continue"
        pause_btn.variant = "success"
        # Note: Cannot change widget ID after creation in Textual

        # Transition to processing after a short delay
        if self.app.transcribe_audio or self.app.output_dir:
            self.set_timer(2.0, self._transition_to_processing)
        else:
            activity.log_info("Export workflow complete!")

    def _transition_to_processing(self) -> None:
        """Transition to processing screen."""
        self.app.call_later(self.app.transition_to_processing)

    def action_toggle_pause(self) -> None:
        """Toggle pause state."""
        self._paused = not self._paused

        progress = self.query_one("#progress-display", ProgressDisplay)
        activity = self.query_one(ActivityLog)
        pause_btn = self.query_one("#btn-pause", Button)

        if self._paused:
            progress.pause()
            activity.log_warning("Export paused")
            pause_btn.label = "Resume"
            pause_btn.variant = "success"
        else:
            progress.resume()
            activity.log_info("Export resumed")
            pause_btn.label = "Pause"
            pause_btn.variant = "warning"

    def action_skip_current(self) -> None:
        """Skip the current chat."""
        if self._current_chat:
            activity = self.query_one(ActivityLog)
            activity.log_warning(f"Skipping: {self._current_chat}")
            # Note: Actual skip logic would need to be implemented in the exporter

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-pause":
            self.action_toggle_pause()
        elif event.button.id == "btn-continue":
            self._transition_to_processing()
