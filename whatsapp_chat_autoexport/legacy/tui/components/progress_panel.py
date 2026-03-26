"""
Progress panel component for TUI.

Displays multi-phase progress tracking with visual indicators.
"""

from typing import Optional, List
from datetime import datetime, timedelta

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
    SpinnerColumn,
)
from rich.table import Table
from rich.text import Text
from rich.live import Live

from whatsapp_chat_autoexport.state.models import ExportProgress, PipelineProgress


class ProgressPanel:
    """
    Rich-based progress panel for export operations.

    Displays:
    - Overall progress bar
    - Current chat and step information
    - Elapsed time and estimated remaining
    - Statistics (completed, failed, skipped)
    """

    def __init__(self):
        """Initialize the progress panel."""
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            expand=True,
        )
        self._task_id: Optional[int] = None
        self._current_chat: Optional[str] = None
        self._current_step: str = ""
        self._start_time: Optional[datetime] = None

        # Statistics
        self._total: int = 0
        self._completed: int = 0
        self._failed: int = 0
        self._skipped: int = 0

    def start(self, total_chats: int) -> None:
        """
        Start tracking progress.

        Args:
            total_chats: Total number of chats to process
        """
        self._total = total_chats
        self._completed = 0
        self._failed = 0
        self._skipped = 0
        self._start_time = datetime.now()

        if self._task_id is not None:
            self._progress.remove_task(self._task_id)

        self._task_id = self._progress.add_task(
            "Exporting chats...",
            total=total_chats,
        )

    def update_chat(self, chat_name: str, step: str = "") -> None:
        """
        Update current chat being processed.

        Args:
            chat_name: Name of the current chat
            step: Current export step
        """
        self._current_chat = chat_name
        self._current_step = step

        if self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"[bold blue]{chat_name}[/] - {step}",
            )

    def advance(self, status: str = "completed") -> None:
        """
        Advance progress by one chat.

        Args:
            status: Outcome status (completed, failed, skipped)
        """
        if status == "completed":
            self._completed += 1
        elif status == "failed":
            self._failed += 1
        elif status == "skipped":
            self._skipped += 1

        if self._task_id is not None:
            self._progress.advance(self._task_id)

    def update_from_progress(self, progress: ExportProgress) -> None:
        """
        Update panel from ExportProgress model.

        Args:
            progress: ExportProgress instance
        """
        self._current_chat = progress.current_chat
        self._current_step = progress.current_step
        self._total = progress.chats_total
        self._completed = progress.chats_completed
        self._failed = progress.chats_failed
        self._skipped = progress.chats_skipped

        if self._task_id is not None:
            processed = self._completed + self._failed + self._skipped
            self._progress.update(
                self._task_id,
                completed=processed,
                total=self._total,
                description=f"[bold blue]{progress.current_chat or 'Waiting...'}[/]",
            )

    def render(self) -> Panel:
        """
        Render the progress panel.

        Returns:
            Rich Panel containing progress display
        """
        # Create main table
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        # Progress bar
        table.add_row(self._progress)

        # Current status
        if self._current_chat:
            status_text = Text()
            status_text.append("Current: ", style="dim")
            status_text.append(self._current_chat, style="bold cyan")
            if self._current_step:
                status_text.append(" → ", style="dim")
                status_text.append(self._current_step, style="yellow")
            table.add_row(status_text)

        # Statistics row
        stats = self._build_stats_row()
        table.add_row(stats)

        # Timing row
        timing = self._build_timing_row()
        table.add_row(timing)

        return Panel(
            table,
            title="[bold white]Export Progress[/]",
            border_style="blue",
            padding=(1, 2),
        )

    def _build_stats_row(self) -> Text:
        """Build statistics row."""
        stats = Text()

        # Completed
        stats.append("✓ ", style="green")
        stats.append(str(self._completed), style="bold green")
        stats.append(" completed  ", style="dim")

        # Failed
        stats.append("✗ ", style="red")
        stats.append(str(self._failed), style="bold red")
        stats.append(" failed  ", style="dim")

        # Skipped
        stats.append("○ ", style="yellow")
        stats.append(str(self._skipped), style="bold yellow")
        stats.append(" skipped  ", style="dim")

        # Remaining
        remaining = self._total - self._completed - self._failed - self._skipped
        stats.append("◌ ", style="dim")
        stats.append(str(remaining), style="dim")
        stats.append(" remaining", style="dim")

        return stats

    def _build_timing_row(self) -> Text:
        """Build timing information row."""
        timing = Text()

        if self._start_time:
            elapsed = datetime.now() - self._start_time
            timing.append("Elapsed: ", style="dim")
            timing.append(self._format_duration(elapsed), style="white")

            # Estimate remaining
            processed = self._completed + self._failed + self._skipped
            if processed > 0:
                avg_per_chat = elapsed.total_seconds() / processed
                remaining = self._total - processed
                est_remaining = timedelta(seconds=avg_per_chat * remaining)

                timing.append("  |  ", style="dim")
                timing.append("Est. remaining: ", style="dim")
                timing.append(self._format_duration(est_remaining), style="white")

        return timing

    def _format_duration(self, duration: timedelta) -> str:
        """Format a duration for display."""
        total_seconds = int(duration.total_seconds())

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()


class StepProgressPanel:
    """
    Progress panel for individual export steps.

    Shows the 6 export steps with current progress.
    """

    STEPS = [
        ("open_menu", "Open Menu", "Opening chat menu..."),
        ("click_more", "Click More", "Clicking more options..."),
        ("click_export", "Export Chat", "Selecting export option..."),
        ("select_media", "Media Option", "Choosing media inclusion..."),
        ("select_drive", "Google Drive", "Selecting Google Drive..."),
        ("click_upload", "Upload", "Initiating upload..."),
    ]

    def __init__(self):
        """Initialize step progress panel."""
        self._current_step: int = 0
        self._chat_name: str = ""
        self._status: str = "pending"  # pending, in_progress, completed, failed

    def set_chat(self, chat_name: str) -> None:
        """Set the current chat being processed."""
        self._chat_name = chat_name
        self._current_step = 0
        self._status = "in_progress"

    def advance_step(self) -> None:
        """Advance to the next step."""
        if self._current_step < len(self.STEPS):
            self._current_step += 1

    def set_step(self, step_index: int) -> None:
        """Set the current step by index."""
        self._current_step = min(step_index, len(self.STEPS))

    def complete(self) -> None:
        """Mark current chat as completed."""
        self._current_step = len(self.STEPS)
        self._status = "completed"

    def fail(self) -> None:
        """Mark current chat as failed."""
        self._status = "failed"

    def render(self) -> Panel:
        """Render the step progress panel."""
        table = Table.grid(expand=True)
        table.add_column(width=3)
        table.add_column(ratio=1)
        table.add_column(width=30)

        for i, (step_id, step_name, step_desc) in enumerate(self.STEPS):
            # Determine step state
            if i < self._current_step:
                # Completed
                icon = "✓"
                icon_style = "green"
                name_style = "green"
                desc_style = "dim green"
            elif i == self._current_step and self._status == "in_progress":
                # Current
                icon = "●"
                icon_style = "bold yellow"
                name_style = "bold yellow"
                desc_style = "yellow"
            elif i == self._current_step and self._status == "failed":
                # Failed at this step
                icon = "✗"
                icon_style = "bold red"
                name_style = "bold red"
                desc_style = "red"
            else:
                # Pending
                icon = "○"
                icon_style = "dim"
                name_style = "dim"
                desc_style = "dim"

            table.add_row(
                Text(icon, style=icon_style),
                Text(step_name, style=name_style),
                Text(step_desc, style=desc_style),
            )

        title = f"[bold white]Steps: {self._chat_name}[/]" if self._chat_name else "[bold white]Export Steps[/]"

        return Panel(
            table,
            title=title,
            border_style="cyan",
            padding=(0, 1),
        )

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
