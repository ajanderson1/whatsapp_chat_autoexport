"""
Unified selection and export screen.

This screen handles the entire workflow after device connection:
1. Select Mode: Display discovered chats with checkboxes, allow selection
2. Export Mode: Export selected chats while showing status in chat list
3. Processing Mode: Run post-processing phases (download, extract, transcribe, etc.)
4. Complete Mode: Show summary and completion status

The key design principle is that the chat list stays visible throughout,
with chats being checked off as they complete, providing a unified experience.
"""

import asyncio
from typing import List, Optional, Literal

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, ListView
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.reactive import reactive
from textual.worker import Worker, WorkerState

from ..textual_widgets.pipeline_header import PipelineHeader
from ..textual_widgets.chat_list import ChatListWidget, ChatDisplayStatus
from ..textual_widgets.settings_panel import SettingsPanel, DEFAULT_OUTPUT_DIR
from ..textual_widgets.progress_pane import ProgressPane
from ..textual_widgets.cancel_modal import CancelModal
from ..textual_app import PipelineStage


# Type alias for screen modes
ScreenMode = Literal["select", "export", "processing", "complete"]


class SelectionScreen(Screen):
    """
    Unified selection and export screen.

    Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │ Pipeline Header                                             │
    ├─────────────────────────────────────────────────────────────┤
    │  Chat List            │  Settings Panel                     │
    │  [✓] Jason Cormack    │  [X] Include media                  │
    │  [●] Tim Cocking      │  [X] Transcribe audio               │
    │  [ ] Helicopter...    │  [ ] Delete from Drive              │
    │  ...                  │                                     │
    ├─────────────────────────────────────────────────────────────┤
    │  Progress Pane (shown during export/processing)             │
    │  Exporting: Tim Cocking | Step: Select Drive (5/7)          │
    │  ████████████░░░░░░░░░░░░  40%                              │
    │  Activity: ✓ Jason exported | → Opening menu...             │
    ├─────────────────────────────────────────────────────────────┤
    │  Bottom Bar: [selection count] [Back] [Start Export]        │
    └─────────────────────────────────────────────────────────────┘
    """

    BINDINGS = [
        Binding("enter", "confirm_selection", "Start Export", show=True),
        Binding("escape", "go_back_or_cancel", "Back/Cancel", show=True),
        Binding("p", "toggle_pause", "Pause", show=False),
        Binding("o", "open_folder", "Open Folder", show=False),
    ]

    # Screen mode state
    _mode: reactive[ScreenMode] = reactive("select")

    # Export state
    _paused: reactive[bool] = reactive(False)
    _current_chat: Optional[str] = None
    _export_worker: Optional[Worker] = None
    _processing_worker: Optional[Worker] = None
    _export_results: dict = {}
    _consecutive_failures: int = 0
    _cancel_after_current: bool = False

    def __init__(self, **kwargs) -> None:
        """Initialize the selection screen."""
        super().__init__(**kwargs)
        self._export_results = {
            "completed": [],
            "failed": [],
            "skipped": [],
        }
        self._consecutive_failures = 0
        self._cancel_after_current = False

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield PipelineHeader()
        with Container(classes="main-content"):
            with Vertical(classes="left-panel"):
                yield ChatListWidget(
                    chats=self.app.discovered_chats,
                    title="CHAT INVENTORY",
                    id="chat-list",
                )
            with Vertical(classes="right-panel"):
                yield SettingsPanel(
                    include_media=self.app.include_media,
                    transcribe_audio=self.app.transcribe_audio,
                    delete_from_drive=self.app.delete_from_drive,
                    output_folder=str(self.app.output_dir) if self.app.output_dir else DEFAULT_OUTPUT_DIR,
                    transcription_provider=getattr(self.app, "transcription_provider", "whisper"),
                    id="settings-panel",
                )
        # Progress pane - initially hidden
        yield ProgressPane(
            id="progress-pane",
            total_chats=len(self.app.discovered_chats),
        )
        with Horizontal(classes="bottom-bar"):
            yield Static(
                f"[dim]Selected: {len(self.app.discovered_chats)} chats[/dim]",
                id="selection-count",
            )
            yield Button("Back", id="btn-back", variant="default")
            yield Button("Start Export", id="btn-start", variant="success")

    async def on_mount(self) -> None:
        """Set up the screen when mounted."""
        # Set the pipeline header stage
        header = self.query_one(PipelineHeader)
        header.set_stage(PipelineStage.PROCESS)

        # Update selection count
        self._update_selection_count()

        # Hide progress pane initially
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.display = False

        # Focus the chat list ListView for keyboard navigation
        chat_listview = self.query_one("#chat-listview", ListView)
        chat_listview.focus()

    # =========================================================================
    # Mode management
    # =========================================================================

    def watch__mode(self, new_mode: ScreenMode) -> None:
        """React to mode changes."""
        self._update_ui_for_mode(new_mode)

    def _update_ui_for_mode(self, mode: ScreenMode) -> None:
        """Update UI elements based on current mode."""
        chat_list = self.query_one("#chat-list", ChatListWidget)
        settings = self.query_one("#settings-panel", SettingsPanel)
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        back_btn = self.query_one("#btn-back", Button)
        start_btn = self.query_one("#btn-start", Button)
        count_label = self.query_one("#selection-count", Static)
        header = self.query_one(PipelineHeader)

        if mode == "select":
            # Selection mode - normal state
            chat_list.set_locked(False)
            chat_list.set_display_mode("select")
            settings.set_locked(False)
            progress_pane.display = False
            back_btn.display = True
            back_btn.label = "Back"
            start_btn.display = True
            start_btn.label = "Start Export"
            start_btn.variant = "success"
            start_btn.disabled = len(chat_list.get_selected()) == 0
            header.set_stage(PipelineStage.PROCESS)

        elif mode == "export":
            # Export mode - locked, showing progress
            chat_list.set_locked(True)
            chat_list.set_display_mode("status")
            settings.set_locked(True)
            progress_pane.display = True
            back_btn.display = True
            back_btn.label = "Cancel"
            start_btn.display = True
            start_btn.label = "Pause" if not self._paused else "Resume"
            start_btn.variant = "warning"
            start_btn.disabled = False
            count_label.update("[yellow]Exporting...[/yellow]")
            header.set_stage(PipelineStage.PROCESS)

        elif mode == "processing":
            # Processing mode - post-export processing
            chat_list.set_locked(True)
            chat_list.set_display_mode("status")
            settings.set_locked(True)
            progress_pane.display = True
            back_btn.display = True
            back_btn.label = "Cancel"
            start_btn.display = False
            count_label.update("[yellow]Processing...[/yellow]")
            header.set_stage(PipelineStage.PROCESS)

        elif mode == "complete":
            # Complete mode - show summary
            chat_list.set_locked(True)
            chat_list.set_display_mode("status")
            settings.set_locked(True)
            progress_pane.display = True
            back_btn.display = False
            start_btn.display = True
            start_btn.label = "Done"
            start_btn.variant = "success"
            start_btn.disabled = False
            self._update_completion_summary()

    def _update_completion_summary(self) -> None:
        """Update the selection count label with completion summary."""
        count_label = self.query_one("#selection-count", Static)
        completed = len(self._export_results.get("completed", []))
        failed = len(self._export_results.get("failed", []))

        if failed > 0:
            count_label.update(f"[green]✓ {completed} exported[/green] | [red]✗ {failed} failed[/red]")
        else:
            count_label.update(f"[green]✓ {completed} chats exported successfully![/green]")

    # =========================================================================
    # Selection mode handlers
    # =========================================================================

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle Enter on ListView - forward to confirm action in select mode."""
        if self._mode == "select":
            event.stop()
            self.action_confirm_selection()

    def on_chat_list_widget_selection_changed(
        self,
        event: ChatListWidget.SelectionChanged,
    ) -> None:
        """Handle chat selection changes."""
        if self._mode == "select":
            self._update_selection_count()

    def _update_selection_count(self) -> None:
        """Update the selection count display."""
        chat_list = self.query_one("#chat-list", ChatListWidget)
        selected = chat_list.get_selected()
        count_label = self.query_one("#selection-count", Static)

        if len(selected) == 0:
            count_label.update("[yellow]No chats selected[/yellow]")
        elif len(selected) == len(self.app.discovered_chats):
            count_label.update(f"[green]All {len(selected)} chats selected[/green]")
        else:
            count_label.update(f"[cyan]{len(selected)} of {len(self.app.discovered_chats)} chats selected[/cyan]")

        # Enable/disable start button
        start_btn = self.query_one("#btn-start", Button)
        start_btn.disabled = len(selected) == 0

    def on_settings_panel_settings_changed(
        self,
        event: SettingsPanel.SettingsChanged,
    ) -> None:
        """Handle settings changes."""
        if self._mode == "select":
            from pathlib import Path

            # Update app settings
            self.app.include_media = event.include_media
            self.app.transcribe_audio = event.transcribe_audio
            self.app.delete_from_drive = event.delete_from_drive

            # Update new settings
            if event.output_folder:
                self.app.output_dir = Path(event.output_folder)
            if event.transcription_provider:
                self.app.transcription_provider = event.transcription_provider

    # =========================================================================
    # Actions
    # =========================================================================

    def action_confirm_selection(self) -> None:
        """Confirm selection and start export (or handle based on mode)."""
        if self._mode == "select":
            self._start_export()
        elif self._mode == "complete":
            self._exit_app()

    # Track whether the cancel modal is currently showing
    _cancel_modal_open: bool = False

    def action_go_back_or_cancel(self) -> None:
        """Go back or cancel based on current mode."""
        if self._mode == "select":
            self.query_one("#chat-listview").focus()
        elif self._mode in ("export", "processing"):
            self._show_cancel_modal()
        elif self._mode == "complete":
            self._return_to_selection()

    def action_toggle_pause(self) -> None:
        """Toggle pause state during export."""
        if self._mode == "export":
            self._paused = not self._paused
            progress_pane = self.query_one("#progress-pane", ProgressPane)

            if self._paused:
                progress_pane.pause()
            else:
                progress_pane.resume()

            # Update button label
            start_btn = self.query_one("#btn-start", Button)
            start_btn.label = "Resume" if self._paused else "Pause"

    def action_open_folder(self) -> None:
        """Open output folder (in complete mode)."""
        if self._mode == "complete" and self.app.output_dir:
            import subprocess
            import sys
            if sys.platform == "darwin":
                subprocess.run(["open", str(self.app.output_dir)], close_fds=True)
            elif sys.platform == "linux":
                subprocess.run(["xdg-open", str(self.app.output_dir)], close_fds=True)

    def _go_back(self) -> None:
        """Go back to discovery screen."""
        # Cleanup driver if connected
        if self.app.driver:
            try:
                self.app.driver.quit()
            except Exception:
                pass
            self.app._whatsapp_driver = None

        # Use switch_screen since we got here via switch_screen (not push_screen)
        from .discovery_screen import DiscoveryScreen
        self.app.switch_screen(DiscoveryScreen())

    _active_cancel_modal: Optional[CancelModal] = None

    def _show_cancel_modal(self, message: Optional[str] = None) -> None:
        """
        Show the cancel confirmation modal.

        Args:
            message: Optional override message (e.g., for consecutive failure warning)
        """
        if self._cancel_modal_open:
            return  # Prevent multiple modals

        self._cancel_modal_open = True

        completed = len(self._export_results.get("completed", []))
        total = len(getattr(self.app, "_selected_chats", []) or [])

        modal = CancelModal(
            current_chat=self._current_chat,
            completed=completed,
            total=total,
            message=message,
        )
        self._active_cancel_modal = modal
        self.app.push_screen(modal, self._handle_cancel_choice)

    _exit_after_cancel: bool = False

    def _handle_cancel_choice(self, choice: str) -> None:
        """Handle the user's cancel modal choice."""
        # Capture checkbox state before clearing modal reference
        wait_for_current = False
        if self._active_cancel_modal:
            try:
                wait_for_current = self._active_cancel_modal.wait_for_current
            except Exception:
                pass
        self._active_cancel_modal = None
        self._cancel_modal_open = False

        if choice == "btn-return":
            if self._current_chat and wait_for_current:
                self._cancel_after_current = True
                self._exit_after_cancel = False
                progress_pane = self.query_one("#progress-pane", ProgressPane)
                progress_pane.log_activity(
                    "Will return to selection after current chat completes", "warning"
                )
            else:
                self._return_to_selection()
        elif choice == "btn-exit":
            if self._current_chat and wait_for_current:
                self._cancel_after_current = True
                self._exit_after_cancel = True
                progress_pane = self.query_one("#progress-pane", ProgressPane)
                progress_pane.log_activity(
                    "Will exit after current chat completes", "warning"
                )
            else:
                self._cancel_operation()
                self.app.exit()
        # "btn-continue" - do nothing, export continues

    def _return_to_selection(self) -> None:
        """Cancel export and return to chat selection mode."""
        # Cancel workers
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None
        if self._processing_worker:
            self._processing_worker.cancel()
            self._processing_worker = None

        # Log the return
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.log_activity("Returned to selection", "info")

        # Reset export state for next run, but preserve results
        # so user can see what was completed
        self._current_chat = None
        self._paused = False
        self._consecutive_failures = 0
        self._cancel_after_current = False
        self._exit_after_cancel = False
        # Note: _export_results is intentionally NOT cleared here
        # so that completed chats are visible in the chat list

        # Reset mode to select (triggers _update_ui_for_mode)
        self._mode = "select"

        # Reset chat list for re-selection
        chat_list = self.query_one("#chat-list", ChatListWidget)
        chat_list.reset_for_reselection()

        # Update selection count
        self._update_selection_count()

    def _cancel_operation(self) -> None:
        """Cancel current export or processing operation."""
        # Cancel workers
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None
        if self._processing_worker:
            self._processing_worker.cancel()
            self._processing_worker = None

        # Show cancellation
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.log_activity("Operation cancelled", "warning")

        # Set to complete mode
        self._mode = "complete"
        self._update_completion_summary()

    def _exit_app(self) -> None:
        """Exit the application."""
        self.app.exit()

    # =========================================================================
    # Export logic
    # =========================================================================

    def _start_export(self) -> None:
        """Start the export process."""
        chat_list = self.query_one("#chat-list", ChatListWidget)
        settings_panel = self.query_one("#settings-panel", SettingsPanel)
        selected = chat_list.get_selected()

        if not selected:
            self.notify("Please select at least one chat", severity="warning")
            return

        # Check if transcription is enabled but no valid provider
        if self.app.transcribe_audio and not settings_panel.has_valid_transcription_provider():
            self.notify(
                "Transcription enabled but no valid API key configured. "
                "Please configure an API key or disable transcription.",
                severity="warning",
            )
            return

        # Apply limit if set
        if self.app.limit and len(selected) > self.app.limit:
            selected = selected[:self.app.limit]
            self.notify(f"Limited to {self.app.limit} chats", severity="information")

        # Store selected chats in app
        self.app._selected_chats = selected

        # Initialize chat statuses from selection
        chat_list.init_statuses_from_selection()

        # Switch to export mode
        self._mode = "export"

        # Initialize progress pane
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.start_export(len(selected))

        # Start export worker
        self._export_worker = self.run_worker(
            self._run_export(selected),
            name="export_worker",
            thread=True,
        )

    # Max consecutive failures before showing disconnect warning
    MAX_CONSECUTIVE_FAILURES = 3

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

        # Get progress pane for activity logging (must be done on main thread)
        progress_pane = self.query_one("#progress-pane", ProgressPane)

        # Create callback to forward log messages to TUI in real-time
        def _export_log_callback(message: str, level: str) -> None:
            try:
                self.app.call_from_thread(
                    progress_pane.log_activity, message, level
                )
            except Exception:
                pass

        # Create callback to forward export step progress to TUI
        def _export_progress_callback(
            phase: str,
            message: str,
            current: int,
            total: int,
            item_name: str = "",
        ) -> None:
            """Forward export step progress to ProgressPane."""
            try:
                self.app.call_from_thread(
                    progress_pane.update_export_step,
                    message,
                    current + 1,  # Convert 0-indexed to 1-indexed for display
                    total,
                )
            except Exception:
                pass

        # Reset consecutive failure counter
        self._consecutive_failures = 0

        for i, chat_name in enumerate(chats):
            # Check for pause
            while self._paused:
                await asyncio.sleep(0.5)

            # Check if cancellation was requested after previous chat
            if self._cancel_after_current:
                # Add remaining chats as skipped
                for remaining in chats[i:]:
                    results["skipped"].append(remaining)
                    self.app.call_from_thread(
                        self._skip_chat_export,
                        remaining,
                        "Cancelled by user",
                    )
                break

            # Update UI - start this chat
            self.app.call_from_thread(self._start_chat_export, chat_name)

            try:
                if driver:
                    # Real export using the driver's methods
                    success = await asyncio.to_thread(
                        self._export_single_chat,
                        driver,
                        chat_name,
                        include_media,
                        _export_log_callback,
                        _export_progress_callback,
                    )

                    if success:
                        results["completed"].append(chat_name)
                        self._consecutive_failures = 0
                        self.app.call_from_thread(self._complete_chat_export, chat_name)
                    else:
                        results["failed"].append(chat_name)
                        self._consecutive_failures += 1
                        self.app.call_from_thread(
                            self._fail_chat_export,
                            chat_name,
                            "Export failed",
                        )

                        # Check for consecutive failure threshold
                        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                            self.app.call_from_thread(
                                self._show_consecutive_failure_warning,
                            )
                            # Wait for user to respond to modal
                            while self._cancel_modal_open:
                                await asyncio.sleep(0.3)
                            # If user chose to cancel, break
                            if self._cancel_after_current:
                                for remaining in chats[i + 1:]:
                                    results["skipped"].append(remaining)
                                    self.app.call_from_thread(
                                        self._skip_chat_export,
                                        remaining,
                                        "Cancelled after consecutive failures",
                                    )
                                break
                else:
                    # Dry run - simulate export
                    for step_idx in range(7):
                        if self._paused:
                            while self._paused:
                                await asyncio.sleep(0.5)

                        self.app.call_from_thread(self._update_step, chat_name, step_idx)
                        await asyncio.sleep(0.3)  # Simulate work

                    results["completed"].append(chat_name)
                    self._consecutive_failures = 0
                    self.app.call_from_thread(self._complete_chat_export, chat_name)

            except Exception as e:
                results["failed"].append(chat_name)
                self._consecutive_failures += 1
                self.app.call_from_thread(self._fail_chat_export, chat_name, str(e))

                # Check for consecutive failure threshold
                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self.app.call_from_thread(
                        self._show_consecutive_failure_warning,
                    )
                    while self._cancel_modal_open:
                        await asyncio.sleep(0.3)
                    if self._cancel_after_current:
                        for remaining in chats[i + 1:]:
                            results["skipped"].append(remaining)
                            self.app.call_from_thread(
                                self._skip_chat_export,
                                remaining,
                                "Cancelled after consecutive failures",
                            )
                        break

        return results

    def _export_single_chat(
        self,
        driver,
        chat_name: str,
        include_media: bool,
        log_callback=None,
        progress_callback=None,
    ) -> bool:
        """
        Export a single chat to Google Drive.

        Args:
            driver: WhatsApp driver instance
            chat_name: Name of chat to export
            include_media: Whether to include media
            log_callback: Optional callback for logging messages to TUI
            progress_callback: Optional callback for step-level progress updates.
                Signature: (phase, message, current, total, item_name="")

        Returns:
            True if successful, False otherwise
        """
        from ...utils.logger import Logger
        from ...export.chat_exporter import ChatExporter
        import time

        # Create logger with TUI callback for real-time activity reporting
        debug_mode = getattr(self.app, "debug_mode", False)
        logger = Logger(debug=debug_mode, on_message=log_callback)

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

            # Export the chat to Google Drive, passing progress callback
            success = exporter.export_chat_to_google_drive(
                chat_name,
                include_media=include_media,
                on_progress=progress_callback,
            )

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

        # Update chat list status
        chat_list = self.query_one("#chat-list", ChatListWidget)
        chat_list.update_chat_status(chat_name, ChatDisplayStatus.IN_PROGRESS)

        # Update progress pane
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.update_export_progress(chat=chat_name, step="Opening chat", step_num=1)
        progress_pane.log_activity(f"Starting: {chat_name}", "info")

    def _update_step(self, chat_name: str, step_idx: int) -> None:
        """Update UI with current step."""
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        steps = progress_pane.EXPORT_STEPS
        if step_idx < len(steps):
            progress_pane.update_export_progress(
                step=steps[step_idx],
                step_num=step_idx + 1,
            )

    def _complete_chat_export(self, chat_name: str) -> None:
        """Update UI when a chat export completes."""
        # Update chat list status
        chat_list = self.query_one("#chat-list", ChatListWidget)
        chat_list.update_chat_status(chat_name, ChatDisplayStatus.COMPLETED)

        # Update progress pane
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.complete_chat(chat_name)

        self._current_chat = None

    def _fail_chat_export(self, chat_name: str, error: str) -> None:
        """Update UI when a chat export fails."""
        # Update chat list status
        chat_list = self.query_one("#chat-list", ChatListWidget)
        chat_list.update_chat_status(chat_name, ChatDisplayStatus.FAILED)

        # Update progress pane
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.fail_chat(chat_name, error)

        self._current_chat = None

    def _skip_chat_export(self, chat_name: str, reason: str) -> None:
        """Update UI when a chat export is skipped."""
        chat_list = self.query_one("#chat-list", ChatListWidget)
        chat_list.update_chat_status(chat_name, ChatDisplayStatus.SKIPPED)

        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.log_activity(f"[dim]Skipped: {chat_name} ({reason})[/dim]", "info")

    def _show_consecutive_failure_warning(self) -> None:
        """Show cancel modal with consecutive failure warning."""
        self._show_cancel_modal(
            message=(
                f"{self._consecutive_failures} consecutive exports have failed. "
                "The device may be disconnected or WhatsApp may have become unresponsive."
            ),
        )

    # =========================================================================
    # Processing logic
    # =========================================================================

    def _start_processing(self) -> None:
        """Start post-export processing."""
        self._mode = "processing"

        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.start_processing()

        self._processing_worker = self.run_worker(
            self._run_processing(),
            name="processing_worker",
            thread=True,
        )

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
        transcription_provider = getattr(self.app, "transcription_provider", "whisper")

        progress_pane = self.query_one("#progress-pane", ProgressPane)
        phases = progress_pane.PROCESSING_PHASES

        # If no output dir, just simulate
        if not output_dir:
            for i, phase_name in enumerate(phases):
                self.app.call_from_thread(
                    self._update_processing_phase,
                    phase_name,
                    i + 1,
                )
                await asyncio.sleep(1.0)  # Simulate work
                self.app.call_from_thread(
                    self._complete_processing_phase,
                    phase_name,
                )

            return results

        try:
            from ...pipeline import WhatsAppPipeline, PipelineConfig
            from ...utils.logger import Logger

            # Create a logger with a TUI callback that forwards messages
            # to the ProgressPane activity log
            def _tui_log_callback(message: str, level: str) -> None:
                try:
                    self.app.call_from_thread(
                        progress_pane.log_activity, message, level
                    )
                except Exception:
                    pass

            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode, on_message=_tui_log_callback)

            # Get the list of successfully exported chat names to filter downloads
            exported_chats = self._export_results.get("completed", []) if self._export_results else []

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

            # Build a progress callback that updates the TUI from the
            # worker thread via call_from_thread
            _last_phase = [None]  # mutable container for closure

            def _pipeline_progress_callback(
                phase: str,
                message: str,
                current: int,
                total: int,
                item_name: str = "",
            ) -> None:
                """Forward pipeline progress events to the ProgressPane."""
                try:
                    # Detect phase transitions
                    if phase != _last_phase[0]:
                        # Complete the previous phase in the UI
                        if _last_phase[0] is not None:
                            prev_display = progress_pane.PHASE_DISPLAY_MAP.get(
                                _last_phase[0], _last_phase[0].title()
                            )
                            self.app.call_from_thread(
                                self._complete_processing_phase, prev_display
                            )
                        _last_phase[0] = phase
                        self.app.call_from_thread(
                            self._update_pipeline_phase, phase
                        )

                    # Update per-item progress
                    if item_name or total > 0:
                        self.app.call_from_thread(
                            self._update_pipeline_item,
                            item_name or message,
                            current,
                            total,
                        )

                    # Log meaningful messages to the activity feed
                    if message:
                        self.app.call_from_thread(
                            progress_pane.log_activity, message, "info"
                        )
                except Exception:
                    pass  # Never let UI errors crash the pipeline

            pipeline = WhatsAppPipeline(
                config, logger=logger, on_progress=_pipeline_progress_callback
            )

            # Kick off the first phase in the UI
            self.app.call_from_thread(self._update_processing_phase, "Download", 1)
            pipeline_results = await asyncio.to_thread(pipeline.run, output_dir / "downloads")

            # Complete the last active phase in the UI
            if _last_phase[0] is not None:
                last_display = progress_pane.PHASE_DISPLAY_MAP.get(
                    _last_phase[0], _last_phase[0].title()
                )
                self.app.call_from_thread(
                    self._complete_processing_phase, last_display
                )

            # Map pipeline results back
            results["downloaded"] = 1 if "download" in pipeline_results.get("phases_completed", []) else 0
            results["extracted"] = 1 if "extract" in pipeline_results.get("phases_completed", []) else 0
            results["transcribed"] = 1 if "transcribe" in pipeline_results.get("phases_completed", []) else 0
            results["output_files"] = len(pipeline_results.get("outputs_created", []))
            results["errors"] = pipeline_results.get("errors", [])

            # Ensure all phases show as complete in the UI
            for phase_name in ["Download", "Extract", "Transcribe", "Build", "Cleanup"]:
                self.app.call_from_thread(self._complete_processing_phase, phase_name)

        except Exception as e:
            results["errors"].append(str(e))
            self.app.call_from_thread(self._log_processing_error, str(e))

        return results

    def _update_processing_phase(self, phase_name_or_key: str, phase_num: int = 0) -> None:
        """
        Update UI for current processing phase.

        Args:
            phase_name_or_key: Display name (e.g. "Download") or pipeline key
                (e.g. "download", "build_output").
            phase_num: Optional explicit phase number (1-indexed). When 0,
                the ProgressPane derives it from the phase key.
        """
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        if phase_num > 0:
            # Legacy path — display name + explicit number
            progress_pane.update_processing_progress(phase=phase_name_or_key, phase_num=phase_num)
            progress_pane.log_activity(f"Starting: {phase_name_or_key}", "info")
        else:
            # New path — pipeline phase key, let ProgressPane resolve it
            progress_pane.update_pipeline_phase(phase_name_or_key)

    def _update_pipeline_phase(self, phase_key: str) -> None:
        """
        Update the ProgressPane to reflect a new pipeline phase.

        Called from the progress callback via call_from_thread.

        Args:
            phase_key: Pipeline phase key (e.g. "download", "transcribe")
        """
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.update_pipeline_phase(phase_key)

    def _update_pipeline_item(self, item_name: str, current: int, total: int) -> None:
        """
        Update per-item progress within the current pipeline phase.

        Called from the progress callback via call_from_thread.

        Args:
            item_name: Name of the current item being processed
            current: Current item index (0-based from pipeline, display as-is)
            total: Total items in this phase
        """
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.update_pipeline_item(item_name, current, total)

    def _complete_processing_phase(self, phase_name: str) -> None:
        """Mark a processing phase as complete."""
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.complete_phase(phase_name)

    def _log_processing_error(self, error: str) -> None:
        """Log a processing error."""
        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.log_activity(f"Error: {error}", "error")

    # =========================================================================
    # Worker state handling
    # =========================================================================

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        worker = event.worker

        # Skip cancelled workers - cancellation is handled by _return_to_selection
        if worker.state == WorkerState.CANCELLED:
            return

        is_finished = worker.state in (WorkerState.SUCCESS, WorkerState.ERROR)

        if worker.name == "export_worker" and is_finished:
            results = worker.result if worker.result else {}
            self._handle_export_complete(results)
        elif worker.name == "processing_worker" and is_finished:
            results = worker.result if worker.result else {}
            self._handle_processing_complete(results)

    def _handle_export_complete(self, results: dict) -> None:
        """Handle export completion."""
        self._export_results = results

        completed = len(results.get("completed", []))
        failed = len(results.get("failed", []))
        skipped = len(results.get("skipped", []))

        progress_pane = self.query_one("#progress-pane", ProgressPane)

        summary_parts = [f"{completed} OK"]
        if failed:
            summary_parts.append(f"{failed} failed")
        if skipped:
            summary_parts.append(f"{skipped} skipped")
        progress_pane.log_activity(f"Export complete: {', '.join(summary_parts)}", "info")

        # Handle deferred cancellation
        if self._cancel_after_current:
            self._cancel_after_current = False
            if self._exit_after_cancel:
                self._exit_after_cancel = False
                self._cancel_operation()
                self.app.exit()
            else:
                self._return_to_selection()
            return

        # Check if we should run processing
        if self.app.transcribe_audio or self.app.output_dir:
            # Transition to processing after a short delay
            self.set_timer(1.0, self._start_processing)
        else:
            # No processing needed, go to complete
            self._finalize_completion(results, {})

    def _handle_processing_complete(self, results: dict) -> None:
        """Handle processing completion."""
        self._finalize_completion(self._export_results, results)

    def _finalize_completion(self, export_results: dict, processing_results: dict) -> None:
        """Finalize the completion state."""
        self._mode = "complete"

        # Build summary
        summary = {
            "exported": len(export_results.get("completed", [])),
            "failed": len(export_results.get("failed", [])),
            "transcribed": processing_results.get("transcribed", 0),
            "output_path": str(self.app.output_dir) if self.app.output_dir else "",
        }

        progress_pane = self.query_one("#progress-pane", ProgressPane)
        progress_pane.set_complete(summary)

    # =========================================================================
    # Button handlers
    # =========================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.action_go_back_or_cancel()
        elif event.button.id == "btn-start":
            if self._mode == "select":
                self.action_confirm_selection()
            elif self._mode == "export":
                self.action_toggle_pause()
            elif self._mode == "complete":
                self._exit_app()
