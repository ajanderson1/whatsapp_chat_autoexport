"""
ExportPane -- per-chat export progress pane.

Displays a ChatListWidget in status mode alongside a ProgressPane,
with pause/resume and cancel controls. Runs the export worker and
emits ExportComplete or CancelledReturnToSelection when done.

Flow:
1. MainScreen calls start_export(chats) after user confirms selection
2. ChatListWidget shows pending/in-progress/completed/failed per chat
3. ProgressPane shows step-level and overall progress
4. Pause/Resume toggles the _paused flag checked by the worker loop
5. Cancel opens CancelModal; callback emits appropriate message
6. On completion (or cancellation) emits ExportComplete
"""

import asyncio
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, Button
from textual.worker import Worker, WorkerState

from ..textual_widgets.activity_log import ActivityLog
from ..textual_widgets.chat_list import ChatListWidget, ChatDisplayStatus
from ..textual_widgets.progress_pane import ProgressPane
from ..textual_widgets.cancel_modal import CancelModal


class ExportPane(Container):
    """
    Export progress pane showing per-chat status and overall progress.

    Responsibilities:
    - Display ChatListWidget in status mode with export statuses
    - Display ProgressPane with step-level and overall export progress
    - Run the export worker (thread=True) and manage pause/cancel
    - Emit ExportComplete when export finishes or is cancelled
    - Emit CancelledReturnToSelection when user cancels and returns
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class ExportComplete(Message):
        """Emitted when export finishes (success, partial, or all failed)."""

        def __init__(self, results: dict, cancelled: bool = False) -> None:
            super().__init__()
            self.results = results
            self.cancelled = cancelled

    class CancelledReturnToSelection(Message):
        """Emitted when user cancels and chooses to return to selection."""
        pass

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    MAX_CONSECUTIVE_FAILURES = 3

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._export_results: dict = {
            "completed": [],
            "failed": [],
            "skipped": [],
        }
        self._consecutive_failures: int = 0
        self._cancel_after_current: bool = False
        self._paused: bool = False
        self._current_chat: Optional[str] = None
        self._export_worker: Optional[Worker] = None
        self._cancel_modal_open: bool = False
        self._active_cancel_modal: Optional[CancelModal] = None
        self._exit_after_cancel: bool = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(classes="main-content"):
            with Vertical(classes="left-panel"):
                yield ChatListWidget(
                    chats=[],
                    title="EXPORT STATUS",
                    display_mode="status",
                    locked=True,
                    id="chat-status-list",
                )
            with Vertical(classes="right-panel"):
                yield ProgressPane(id="export-progress-pane", mode="export")

        with Horizontal(classes="bottom-bar"):
            yield Static(
                "[dim]Ready to export[/dim]",
                id="export-status",
            )
            yield Button("Pause", id="btn-pause", variant="warning")
            yield Button("Cancel", id="btn-cancel", variant="error")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_export(self, chats: List[str]) -> None:
        """
        Populate the chat list and start the export worker.

        Args:
            chats: List of chat names to export
        """
        # Reset state
        self._export_results = {
            "completed": [],
            "failed": [],
            "skipped": [],
        }
        self._consecutive_failures = 0
        self._cancel_after_current = False
        self._paused = False
        self._current_chat = None
        self._exit_after_cancel = False

        # Populate ChatListWidget
        chat_list = self.query_one("#chat-status-list", ChatListWidget)
        chat_list.set_chats(chats, select_all=True)
        chat_list.set_display_mode("status")
        chat_list.set_locked(True)
        chat_list.init_statuses_from_selection()

        # Initialize ProgressPane
        progress = self.query_one("#export-progress-pane", ProgressPane)
        progress.start_export(len(chats))

        # Update status bar
        try:
            status = self.query_one("#export-status", Static)
            status.update(f"[yellow]Exporting 0 of {len(chats)}[/yellow]")
        except Exception:
            pass

        # Enable buttons
        try:
            self.query_one("#btn-pause", Button).label = "Pause"
            self.query_one("#btn-pause", Button).disabled = False
            self.query_one("#btn-cancel", Button).disabled = False
        except Exception:
            pass

        # Start worker
        self._export_worker = self.run_worker(
            self._run_export(chats),
            name="export_worker",
            thread=True,
        )

    def reset(self) -> None:
        """Clear all export state for re-export after cancel."""
        # Cancel any running worker
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None

        self._export_results = {
            "completed": [],
            "failed": [],
            "skipped": [],
        }
        self._consecutive_failures = 0
        self._cancel_after_current = False
        self._paused = False
        self._current_chat = None
        self._exit_after_cancel = False
        self._cancel_modal_open = False
        self._active_cancel_modal = None

        # Reset UI elements
        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.set_chats([], select_all=False)
        except Exception:
            pass

        try:
            status = self.query_one("#export-status", Static)
            status.update("[dim]Ready to export[/dim]")
        except Exception:
            pass

        try:
            self.query_one("#btn-pause", Button).label = "Pause"
            self.query_one("#btn-pause", Button).disabled = False
            self.query_one("#btn-cancel", Button).disabled = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-pause":
            self._toggle_pause()
        elif event.button.id == "btn-cancel":
            self._show_cancel_modal()

    def _toggle_pause(self) -> None:
        """Toggle pause state."""
        self._paused = not self._paused
        progress = self.query_one("#export-progress-pane", ProgressPane)

        if self._paused:
            progress.pause()
            try:
                self.query_one("#btn-pause", Button).label = "Resume"
            except Exception:
                pass
        else:
            progress.resume()
            try:
                self.query_one("#btn-pause", Button).label = "Pause"
            except Exception:
                pass

    def _show_cancel_modal(self, message: Optional[str] = None) -> None:
        """Show the cancel confirmation modal."""
        if self._cancel_modal_open:
            return

        self._cancel_modal_open = True

        completed = len(self._export_results.get("completed", []))
        total = len(self._export_results.get("completed", [])) + \
                len(self._export_results.get("failed", [])) + \
                len(self._export_results.get("skipped", []))
        # Estimate total from chat list
        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            total = len(chat_list._chats)
        except Exception:
            pass

        modal = CancelModal(
            current_chat=self._current_chat,
            completed=completed,
            total=total,
            message=message,
        )
        self._active_cancel_modal = modal
        self.app.push_screen(modal, self._handle_cancel_choice)

    def _handle_cancel_choice(self, choice: str) -> None:
        """Handle the user's cancel modal choice."""
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
                progress = self.query_one("#export-progress-pane", ProgressPane)
                progress.log_activity(
                    "Will return to selection after current chat completes",
                    "warning",
                )
            else:
                self._cancel_and_return()
        elif choice == "btn-exit":
            if self._current_chat and wait_for_current:
                self._cancel_after_current = True
                self._exit_after_cancel = True
                progress = self.query_one("#export-progress-pane", ProgressPane)
                progress.log_activity(
                    "Will exit after current chat completes",
                    "warning",
                )
            else:
                self._cancel_operation()
                self.app.exit()
        # "btn-continue" - do nothing, export continues

    def _cancel_and_return(self) -> None:
        """Cancel export and emit CancelledReturnToSelection."""
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None

        self._log("Export cancelled, returning to selection")
        self.post_message(self.CancelledReturnToSelection())

    def _cancel_operation(self) -> None:
        """Cancel current export operation."""
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None

        self._log("Export cancelled")

    # ------------------------------------------------------------------
    # Export worker
    # ------------------------------------------------------------------

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

        driver = getattr(self.app, "driver", None)
        include_media = getattr(self.app, "include_media", True)

        progress = self.query_one("#export-progress-pane", ProgressPane)

        def _export_log_callback(message: str, level: str) -> None:
            try:
                self.app.call_from_thread(
                    progress.log_activity, message, level
                )
            except Exception:
                pass

        def _export_progress_callback(
            phase: str,
            message: str,
            current: int,
            total: int,
            item_name: str = "",
        ) -> None:
            try:
                self.app.call_from_thread(
                    progress.update_export_step,
                    message,
                    current + 1,
                    total,
                )
            except Exception:
                pass

        self._consecutive_failures = 0

        # Reset WhatsApp to the top of the chat list before exporting
        # (discovery may have scrolled to the bottom)
        if driver:
            try:
                await asyncio.to_thread(driver.restart_app_to_top)
            except Exception:
                pass

        for i, chat_name in enumerate(chats):
            # Check for pause
            while self._paused:
                await asyncio.sleep(0.5)

            # Check for cancellation
            if self._cancel_after_current:
                for remaining in chats[i:]:
                    results["skipped"].append(remaining)
                    self.app.call_from_thread(
                        self._skip_chat_export, remaining, "Cancelled by user"
                    )
                break

            # Update UI - start this chat
            self.app.call_from_thread(self._start_chat_export, chat_name)

            try:
                if driver:
                    outcome = await asyncio.to_thread(
                        self._export_single_chat,
                        driver,
                        chat_name,
                        include_media,
                        _export_log_callback,
                        _export_progress_callback,
                    )

                    # Normalise legacy bool returns to ExportOutcome so the
                    # tri-state branches below can be written uniformly.
                    from ...export.chat_exporter import (
                        ExportOutcome,
                        ExportOutcomeKind,
                    )
                    if outcome is True:
                        outcome = ExportOutcome(kind=ExportOutcomeKind.SUCCESS)
                    elif outcome is False:
                        outcome = ExportOutcome(
                            kind=ExportOutcomeKind.FAILED,
                            reason="Unknown failure",
                        )

                    if outcome.kind == ExportOutcomeKind.SUCCESS:
                        results["completed"].append(chat_name)
                        self._consecutive_failures = 0
                        self.app.call_from_thread(
                            self._complete_chat_export, chat_name
                        )
                    elif outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY:
                        # Community chats must NOT count toward the consecutive
                        # failure limit - they are an expected skip, not a
                        # transient UI failure.
                        results["skipped"].append(chat_name)
                        self.app.call_from_thread(
                            self._skip_chat_export,
                            chat_name,
                            outcome.reason or "Community chat - export unsupported",
                        )
                    else:  # FAILED
                        results["failed"].append(chat_name)
                        self._consecutive_failures += 1
                        self.app.call_from_thread(
                            self._fail_chat_export,
                            chat_name,
                            outcome.reason or "Export failed",
                        )

                        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                            self.app.call_from_thread(
                                self._show_consecutive_failure_warning
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
                else:
                    # Dry run - simulate export
                    for step_idx in range(7):
                        if self._paused:
                            while self._paused:
                                await asyncio.sleep(0.5)
                        self.app.call_from_thread(
                            self._update_step, chat_name, step_idx
                        )
                        await asyncio.sleep(0.3)

                    results["completed"].append(chat_name)
                    self._consecutive_failures = 0
                    self.app.call_from_thread(
                        self._complete_chat_export, chat_name
                    )

            except Exception as e:
                results["failed"].append(chat_name)
                self._consecutive_failures += 1
                self.app.call_from_thread(
                    self._fail_chat_export, chat_name, str(e)
                )

                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self.app.call_from_thread(
                        self._show_consecutive_failure_warning
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
            log_callback: Optional callback for logging
            progress_callback: Optional callback for step progress

        Returns:
            True if successful, False otherwise
        """
        from ...export.chat_exporter import (
            ChatExporter,
            ExportOutcome,
            ExportOutcomeKind,
        )

        debug_mode = getattr(self.app, "debug_mode", False)

        try:
            from ...utils.logger import Logger
            logger = Logger(debug=debug_mode, on_message=log_callback)
        except ImportError:
            logger = None

        exporter = ChatExporter(driver, logger)

        try:
            # Settle wait absorbs the Drive-share-return window before verify.
            # Timeout here is not fatal - we fall through to verify so existing
            # failure handling still triggers for genuine non-WhatsApp states.
            if not driver.wait_for_whatsapp_foreground(timeout=8.0):
                if log_callback:
                    log_callback(
                        "Foreground settle timed out; running full verify",
                        "debug",
                    )

            if not driver.verify_whatsapp_is_open():
                if log_callback:
                    log_callback("WhatsApp verification failed", "error")
                return ExportOutcome(
                    kind=ExportOutcomeKind.FAILED,
                    reason="WhatsApp verification failed",
                )

            # Navigate to main screen and open the chat
            driver.navigate_to_main()
            from time import sleep
            sleep(0.3)

            if not driver.click_chat(chat_name):
                if log_callback:
                    log_callback(f"Could not open chat '{chat_name}'", "error")
                return ExportOutcome(
                    kind=ExportOutcomeKind.FAILED,
                    reason=f"Could not open chat '{chat_name}'",
                )

            outcome = exporter.export_chat_to_google_drive(
                chat_name,
                include_media=include_media,
                on_progress=progress_callback,
            )
            return outcome
        except Exception as e:
            if log_callback:
                log_callback(f"Export error: {e}", "error")
            return ExportOutcome(kind=ExportOutcomeKind.FAILED, reason=str(e))

    # ------------------------------------------------------------------
    # UI update helpers (called from worker thread via call_from_thread)
    # ------------------------------------------------------------------

    def _start_chat_export(self, chat_name: str) -> None:
        """Mark a chat as in-progress."""
        self._current_chat = chat_name

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(chat_name, ChatDisplayStatus.IN_PROGRESS)
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.update_export_progress(chat=chat_name)
        except Exception:
            pass

        completed = len(self._export_results.get("completed", []))
        total_chats = 0
        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            total_chats = len(chat_list._chats)
        except Exception:
            pass

        try:
            status = self.query_one("#export-status", Static)
            status.update(
                f"[yellow]Exporting {completed + 1} of {total_chats}[/yellow]"
            )
        except Exception:
            pass

        self._log(f"Starting export: {chat_name}")

    def _complete_chat_export(self, chat_name: str) -> None:
        """Mark a chat as completed."""
        self._current_chat = None
        self._export_results["completed"].append(chat_name)

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(chat_name, ChatDisplayStatus.COMPLETED)
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.complete_chat(chat_name)
        except Exception:
            pass

    def _fail_chat_export(self, chat_name: str, error: str) -> None:
        """Mark a chat as failed."""
        self._current_chat = None
        self._export_results["failed"].append(chat_name)

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(chat_name, ChatDisplayStatus.FAILED)
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.fail_chat(chat_name, error)
        except Exception:
            pass

    def _skip_chat_export(self, chat_name: str, reason: str) -> None:
        """Mark a chat as skipped."""
        self._export_results["skipped"].append(chat_name)

        try:
            chat_list = self.query_one("#chat-status-list", ChatListWidget)
            chat_list.update_chat_status(chat_name, ChatDisplayStatus.SKIPPED)
        except Exception:
            pass

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.log_activity(f"Skipped: {chat_name} ({reason})", "warning")
        except Exception:
            pass

    def _update_step(self, chat_name: str, step_idx: int) -> None:
        """Update step progress during dry-run export."""
        steps = ProgressPane.EXPORT_STEPS
        step_name = steps[step_idx] if step_idx < len(steps) else f"Step {step_idx}"

        try:
            progress = self.query_one("#export-progress-pane", ProgressPane)
            progress.update_export_step(step_name, step_idx + 1, len(steps))
        except Exception:
            pass

    def _show_consecutive_failure_warning(self) -> None:
        """Show cancel modal with a consecutive failure warning."""
        self._show_cancel_modal(
            message=f"{self._consecutive_failures} consecutive exports failed. "
            "The device may have disconnected."
        )

    # ------------------------------------------------------------------
    # Worker state handling
    # ------------------------------------------------------------------

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle export worker completion."""
        if event.worker.name != "export_worker":
            return

        if event.state == WorkerState.SUCCESS:
            results = event.worker.result or self._export_results
            self._export_results = results

            cancelled = self._cancel_after_current
            if self._exit_after_cancel:
                self.app.exit()
                return

            self.post_message(
                self.ExportComplete(results=results, cancelled=cancelled)
            )

        elif event.state == WorkerState.ERROR:
            self._log("Export worker failed with error")
            self.post_message(
                self.ExportComplete(
                    results=self._export_results, cancelled=False
                )
            )

        elif event.state == WorkerState.CANCELLED:
            # Cancellation is handled by _cancel_and_return
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Write to the screen-level ActivityLog."""
        try:
            log_widget = self.screen.query_one(ActivityLog)
            log_widget.write(message)
        except Exception:
            pass
