"""
Main TUI application for WhatsApp Chat Auto-Export.

Provides the primary Rich-based terminal interface with:
- Live display updates
- Keyboard input handling
- Screen management
- Event integration
"""

from typing import Optional, Callable, Any
from datetime import datetime
import threading

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from .wizard import ExportWizard, WizardController, WizardStep
from .screens import ExportProgressScreen
from .components import ProgressPanel, QueuePanel, StatusBar
from whatsapp_chat_autoexport.state.models import SessionState, ChatState, ExportProgress
from whatsapp_chat_autoexport.core.events import EventBus, EventType, Event


class WhatsAppExportTUI:
    """
    Main TUI application.

    Provides:
    - Rich Live display with automatic refresh
    - Keyboard input handling
    - Screen-based navigation
    - Event-driven updates
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        event_bus: Optional[EventBus] = None,
        refresh_rate: float = 4.0,
    ):
        """
        Initialize the TUI application.

        Args:
            console: Rich console for output
            event_bus: Event bus for state notifications
            refresh_rate: Screen refresh rate in Hz
        """
        self._console = console or Console()
        self._event_bus = event_bus or EventBus()
        self._refresh_rate = refresh_rate

        # Components
        self._wizard = ExportWizard(self._console)
        self._controller = WizardController(self._wizard)

        # State
        self._running = False
        self._live: Optional[Live] = None
        self._input_thread: Optional[threading.Thread] = None

        # Subscribe to events
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Set up event bus handlers."""
        self._event_bus.subscribe(
            EventType.STATE_CHANGED,
            self._on_state_changed,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_STEP_COMPLETED,
            self._on_export_progress,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_COMPLETED,
            self._on_export_completed,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_FAILED,
            self._on_export_failed,
        )

    def _on_state_changed(self, event: Event) -> None:
        """Handle state change events."""
        # Trigger refresh
        pass

    def _on_export_progress(self, event: Event) -> None:
        """Handle export progress events."""
        # Update progress display
        if hasattr(event, "chat_name"):
            self._wizard._export_progress.update_step(
                event.chat_name,
                getattr(event, "step_index", 0),
                getattr(event, "step_name", ""),
            )

    def _on_export_completed(self, event: Event) -> None:
        """Handle export completed events."""
        if hasattr(event, "chat_name"):
            self._wizard._export_progress.complete_chat(event.chat_name)

    def _on_export_failed(self, event: Event) -> None:
        """Handle export failed events."""
        if hasattr(event, "chat_name"):
            error = getattr(event, "error", "Unknown error")
            self._wizard._export_progress.fail_chat(event.chat_name, error)

    def render(self) -> Panel:
        """
        Render the current TUI state.

        Returns:
            Rich Panel with current display
        """
        return self._wizard.render_current()

    def run(self) -> None:
        """
        Run the TUI application.

        Blocks until the user exits.
        """
        self._running = True

        with Live(
            self.render(),
            console=self._console,
            refresh_per_second=self._refresh_rate,
            screen=True,
        ) as live:
            self._live = live

            while self._running and self._wizard.state.is_running:
                # Update display
                live.update(self.render())

                # Note: In a real implementation, we would use
                # proper async keyboard input handling here.
                # For now, this serves as the structure.
                import time
                time.sleep(0.1)

        self._live = None

    def run_progress_only(
        self,
        session: SessionState,
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Run just the progress screen (non-interactive mode).

        Args:
            session: Session state to display
            on_pause: Callback when paused
            on_resume: Callback when resumed
        """
        self._wizard.go_to_step(WizardStep.EXPORT_PROGRESS)

        # Initialize progress screen
        chats = list(session.chats.values())
        self._wizard._export_progress.start(
            len(chats),
            chats,
        )

        with Live(
            self.render(),
            console=self._console,
            refresh_per_second=self._refresh_rate,
        ) as live:
            self._live = live

            while self._running:
                # Update from session state
                self._wizard._export_progress.update_from_chats(
                    list(session.chats.values())
                )

                live.update(self.render())

                import time
                time.sleep(0.25)

    def stop(self) -> None:
        """Stop the TUI application."""
        self._running = False

    def update_progress(self, progress: ExportProgress) -> None:
        """
        Update the progress display.

        Args:
            progress: Current export progress
        """
        self._wizard._export_progress.update_progress(progress)

        if self._live:
            self._live.update(self.render())

    def start_chat(self, chat_name: str) -> None:
        """
        Mark a chat as starting.

        Args:
            chat_name: Name of the chat
        """
        self._wizard._export_progress.start_chat(chat_name)

    def complete_chat(self, chat_name: str) -> None:
        """
        Mark a chat as completed.

        Args:
            chat_name: Name of the chat
        """
        self._wizard._export_progress.complete_chat(chat_name)

    def fail_chat(self, chat_name: str, error: str) -> None:
        """
        Mark a chat as failed.

        Args:
            chat_name: Name of the chat
            error: Error message
        """
        self._wizard._export_progress.fail_chat(chat_name, error)

    def skip_chat(self, chat_name: str, reason: str) -> None:
        """
        Mark a chat as skipped.

        Args:
            chat_name: Name of the chat
            reason: Skip reason
        """
        self._wizard._export_progress.skip_chat(chat_name, reason)

    def pause(self) -> None:
        """Pause the export."""
        self._wizard.pause_export()

    def resume(self) -> None:
        """Resume the export."""
        self._wizard.resume_export()


class ProgressOnlyTUI:
    """
    Simplified TUI showing only export progress.

    For use in non-interactive export mode.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        refresh_rate: float = 4.0,
    ):
        """
        Initialize progress-only TUI.

        Args:
            console: Rich console for output
            refresh_rate: Refresh rate in Hz
        """
        self._console = console or Console()
        self._refresh_rate = refresh_rate
        self._progress_screen = ExportProgressScreen(compact_mode=True)
        self._running = False
        self._live: Optional[Live] = None

    def start(self, total_chats: int, chats: list) -> None:
        """
        Start the progress display.

        Args:
            total_chats: Total number of chats
            chats: List of ChatState objects
        """
        self._progress_screen.start(total_chats, chats)
        self._running = True

        self._live = Live(
            self._progress_screen.render(),
            console=self._console,
            refresh_per_second=self._refresh_rate,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the progress display."""
        self._running = False
        if self._live:
            self._live.stop()
            self._live = None

    def update(self) -> None:
        """Refresh the display."""
        if self._live:
            self._live.update(self._progress_screen.render())

    def start_chat(self, chat_name: str) -> None:
        """Mark a chat as started."""
        self._progress_screen.start_chat(chat_name)
        self.update()

    def update_step(self, chat_name: str, step_index: int, step_name: str) -> None:
        """Update current step."""
        self._progress_screen.update_step(chat_name, step_index, step_name)
        self.update()

    def complete_chat(self, chat_name: str) -> None:
        """Mark a chat as completed."""
        self._progress_screen.complete_chat(chat_name)
        self.update()

    def fail_chat(self, chat_name: str, error: str) -> None:
        """Mark a chat as failed."""
        self._progress_screen.fail_chat(chat_name, error)
        self.update()

    def skip_chat(self, chat_name: str, reason: str) -> None:
        """Mark a chat as skipped."""
        self._progress_screen.skip_chat(chat_name, reason)
        self.update()

    def pause(self) -> None:
        """Show paused state."""
        self._progress_screen.pause()
        self.update()

    def resume(self) -> None:
        """Show resumed state."""
        self._progress_screen.resume()
        self.update()

    def update_from_chats(self, chats: list) -> None:
        """Update queue from chat list."""
        self._progress_screen.update_from_chats(chats)
        self.update()

    def __enter__(self) -> "ProgressOnlyTUI":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
