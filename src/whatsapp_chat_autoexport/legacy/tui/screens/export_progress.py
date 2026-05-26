"""
Export progress screen for TUI.

Displays real-time export progress with detailed status.
"""

from typing import Optional, List
from datetime import datetime, timedelta

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.layout import Layout
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
    SpinnerColumn,
)

from whatsapp_chat_autoexport.legacy.tui.components.progress_panel import ProgressPanel, StepProgressPanel
from whatsapp_chat_autoexport.legacy.tui.components.queue_panel import QueuePanel, CompactQueuePanel
from whatsapp_chat_autoexport.legacy.tui.components.status_bar import StatusBar
from whatsapp_chat_autoexport.state.models import ExportProgress, ChatStatus, ChatState


class ExportProgressScreen:
    """
    Export progress screen.

    Shows:
    - Overall progress with current chat
    - Step-by-step progress for current chat
    - Queue view with status indicators
    - Controls for pause/resume/skip
    """

    def __init__(self, compact_mode: bool = False):
        """
        Initialize the export progress screen.

        Args:
            compact_mode: Use compact layout for smaller terminals
        """
        self._compact_mode = compact_mode
        self._progress_panel = ProgressPanel()
        self._step_panel = StepProgressPanel()
        self._queue_panel = CompactQueuePanel() if compact_mode else QueuePanel()
        self._status_bar = StatusBar()

        # State
        self._paused: bool = False
        self._current_chat: Optional[str] = None
        self._current_step: int = 0
        self._start_time: Optional[datetime] = None

    @property
    def paused(self) -> bool:
        """Check if export is paused."""
        return self._paused

    def start(self, total_chats: int, chats: List[ChatState]) -> None:
        """
        Start tracking export progress.

        Args:
            total_chats: Total number of chats to export
            chats: List of ChatState objects
        """
        self._start_time = datetime.now()
        self._progress_panel.start(total_chats)
        self._queue_panel.update_from_chats(chats)
        self._status_bar.set_status("Exporting", "green")
        self._status_bar.set_device_status("Connected", connected=True)

    def update_progress(self, progress: ExportProgress) -> None:
        """
        Update from ExportProgress model.

        Args:
            progress: ExportProgress instance
        """
        self._progress_panel.update_from_progress(progress)
        self._current_chat = progress.current_chat
        self._current_step = progress.step_index

    def start_chat(self, chat_name: str) -> None:
        """
        Mark a chat as started.

        Args:
            chat_name: Name of the chat starting
        """
        self._current_chat = chat_name
        self._step_panel.set_chat(chat_name)
        self._progress_panel.update_chat(chat_name, "Starting...")
        self._queue_panel.update_item(chat_name, status=ChatStatus.IN_PROGRESS)

    def update_step(self, chat_name: str, step_index: int, step_name: str) -> None:
        """
        Update current step for a chat.

        Args:
            chat_name: Name of the chat
            step_index: Step index (0-5)
            step_name: Step name
        """
        self._step_panel.set_step(step_index)
        self._progress_panel.update_chat(chat_name, step_name)
        self._queue_panel.update_item(chat_name, step=step_name)

    def complete_chat(self, chat_name: str) -> None:
        """
        Mark a chat as completed.

        Args:
            chat_name: Name of the completed chat
        """
        self._step_panel.complete()
        self._progress_panel.advance("completed")
        self._queue_panel.update_item(chat_name, status=ChatStatus.COMPLETED)

    def fail_chat(self, chat_name: str, error: str) -> None:
        """
        Mark a chat as failed.

        Args:
            chat_name: Name of the failed chat
            error: Error message
        """
        self._step_panel.fail()
        self._progress_panel.advance("failed")
        self._queue_panel.update_item(
            chat_name,
            status=ChatStatus.FAILED,
            error=error,
        )

    def skip_chat(self, chat_name: str, reason: str) -> None:
        """
        Mark a chat as skipped.

        Args:
            chat_name: Name of the skipped chat
            reason: Skip reason
        """
        self._progress_panel.advance("skipped")
        self._queue_panel.update_item(
            chat_name,
            status=ChatStatus.SKIPPED,
            error=reason,
        )

    def pause(self) -> None:
        """Pause the export."""
        self._paused = True
        self._status_bar.set_paused(True)
        self._status_bar.set_status("Paused", "yellow")

    def resume(self) -> None:
        """Resume the export."""
        self._paused = False
        self._status_bar.set_paused(False)
        self._status_bar.set_status("Exporting", "green")

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        if self._paused:
            self.resume()
        else:
            self.pause()

    def set_device_disconnected(self) -> None:
        """Mark device as disconnected."""
        self._status_bar.set_device_status("Disconnected", connected=False)
        self._status_bar.set_status("Device disconnected", "red")

    def update_from_chats(self, chats: List[ChatState]) -> None:
        """
        Update queue from list of ChatState objects.

        Args:
            chats: List of ChatState instances
        """
        self._queue_panel.update_from_chats(chats)

    def render(self) -> Panel:
        """
        Render the export progress screen.

        Returns:
            Rich Panel containing progress display
        """
        if self._compact_mode:
            return self._render_compact()

        return self._render_full()

    def _render_full(self) -> Panel:
        """Render full layout."""
        # Main container
        main_table = Table.grid(expand=True)
        main_table.add_column(ratio=1)

        # Top section: Overall progress
        main_table.add_row(self._progress_panel.render())

        # Middle section: Step progress and queue side by side
        middle = Table.grid(expand=True)
        middle.add_column(ratio=1)
        middle.add_column(ratio=1)

        middle.add_row(
            self._step_panel.render(),
            self._queue_panel.render(),
        )

        main_table.add_row(middle)

        # Bottom: Status bar
        main_table.add_row(self._status_bar.render())

        return Panel(
            main_table,
            title="[bold white]Export Progress[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    def _render_compact(self) -> Panel:
        """Render compact layout."""
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        # Progress panel (compact)
        table.add_row(self._progress_panel.render())

        # Queue summary (compact)
        table.add_row(self._queue_panel.render())

        # Status line
        table.add_row(self._status_bar.render_compact())

        return Panel(
            table,
            title="[bold white]Exporting[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    def render_paused_overlay(self) -> Panel:
        """Render paused state overlay."""
        content = Table.grid(expand=True)
        content.add_column(justify="center", ratio=1)

        pause_text = Text()
        pause_text.append("\n⏸ PAUSED\n\n", style="bold yellow")
        pause_text.append("Press ", style="dim")
        pause_text.append("[Space]", style="bold cyan")
        pause_text.append(" to resume\n", style="dim")
        pause_text.append("Press ", style="dim")
        pause_text.append("[Q]", style="bold cyan")
        pause_text.append(" to quit", style="dim")

        content.add_row(Align.center(pause_text))

        return Panel(
            content,
            border_style="yellow",
            padding=(2, 4),
        )

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
