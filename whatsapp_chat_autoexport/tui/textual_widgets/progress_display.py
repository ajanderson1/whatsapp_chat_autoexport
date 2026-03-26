"""
Progress display widget for showing export/processing progress.

Shows:
- Overall progress bar
- Current item being processed
- Step-by-step breakdown with status indicators
"""

from typing import List, Optional
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, ProgressBar, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive


class ProgressDisplay(Widget):
    """
    Widget showing progress bar and step breakdown.

    Features:
    - Overall progress percentage
    - Current item name
    - Step-by-step progress with status symbols
    """

    DEFAULT_CSS = """
    ProgressDisplay {
        height: auto;
        padding: 1;
    }
    """

    EXPORT_STEPS = [
        "Open chat",
        "Open menu",
        "Click More",
        "Click Export",
        "Select media option",
        "Select Drive",
        "Confirm upload",
    ]

    # Reactive state
    current_item: reactive[str] = reactive("")
    current_step: reactive[int] = reactive(0)
    total_items: reactive[int] = reactive(0)
    completed_items: reactive[int] = reactive(0)

    def __init__(
        self,
        title: str = "EXPORT PROGRESS",
        steps: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the progress display.

        Args:
            title: Title for the display
            steps: Custom step names (defaults to export steps)
        """
        super().__init__(**kwargs)
        self._title = title
        self._steps = steps or self.EXPORT_STEPS
        self._is_paused = False

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        with Vertical():
            yield Static(f"[bold]{self._title}[/bold]", classes="progress-title")
            yield Static("", id="current-item", classes="progress-current")
            yield ProgressBar(id="main-progress", total=100, show_eta=False)
            yield Static("", id="progress-stats")
            yield Static("", id="step-display")

    def _format_step_display(self) -> str:
        """
        Format the step-by-step display.

        Returns:
            Rich-formatted string showing all steps
        """
        if not self.current_item:
            return ""

        lines = []
        for i, step in enumerate(self._steps):
            if i < self.current_step:
                # Completed step
                lines.append(f"  [green]✓[/green] {step}")
            elif i == self.current_step:
                # Current step
                lines.append(f"  [yellow bold]●[/yellow bold] [yellow]{step}[/yellow]")
            else:
                # Pending step
                lines.append(f"  [dim]○ {step}[/dim]")

        return "\n".join(lines)

    def _update_display(self) -> None:
        """Update all display elements."""
        # Update current item
        current_label = self.query_one("#current-item", Static)
        if self.current_item:
            status = "[yellow]PAUSED[/yellow]" if self._is_paused else ""
            current_label.update(f"Current: [cyan]{self.current_item}[/cyan] {status}")
        else:
            current_label.update("")

        # Update progress bar
        progress_bar = self.query_one("#main-progress", ProgressBar)
        if self.total_items > 0:
            percentage = (self.completed_items / self.total_items) * 100
            progress_bar.update(progress=percentage)
        else:
            progress_bar.update(progress=0)

        # Update stats
        stats = self.query_one("#progress-stats", Static)
        stats.update(
            f"Progress: {self.completed_items}/{self.total_items} chats "
            f"({int((self.completed_items / max(1, self.total_items)) * 100)}%)"
        )

        # Update step display
        step_display = self.query_one("#step-display", Static)
        step_display.update(self._format_step_display())

    def watch_current_item(self, value: str) -> None:
        """React to current item changes."""
        self._update_display()

    def watch_current_step(self, value: int) -> None:
        """React to step changes."""
        self._update_display()

    def watch_completed_items(self, value: int) -> None:
        """React to completed count changes."""
        self._update_display()

    # =========================================================================
    # Public API
    # =========================================================================

    def start(self, total: int) -> None:
        """
        Start progress tracking.

        Args:
            total: Total number of items to process
        """
        self.total_items = total
        self.completed_items = 0
        self.current_item = ""
        self.current_step = 0
        self._update_display()

    def start_item(self, name: str) -> None:
        """
        Start processing a new item.

        Args:
            name: Name of the item
        """
        self.current_item = name
        self.current_step = 0
        self._update_display()

    def advance_step(self, step_index: Optional[int] = None) -> None:
        """
        Advance to the next step.

        Args:
            step_index: Specific step index (or None to increment)
        """
        if step_index is not None:
            self.current_step = step_index
        else:
            self.current_step += 1
        self._update_display()

    def complete_item(self) -> None:
        """Mark current item as completed."""
        self.completed_items += 1
        self.current_item = ""
        self.current_step = 0
        self._update_display()

    def fail_item(self) -> None:
        """Mark current item as failed (still advances count)."""
        self.completed_items += 1
        self.current_item = ""
        self.current_step = 0
        self._update_display()

    def skip_item(self) -> None:
        """Mark current item as skipped (still advances count)."""
        self.completed_items += 1
        self.current_item = ""
        self.current_step = 0
        self._update_display()

    def pause(self) -> None:
        """Show paused state."""
        self._is_paused = True
        self._update_display()

    def resume(self) -> None:
        """Clear paused state."""
        self._is_paused = False
        self._update_display()

    def set_steps(self, steps: List[str]) -> None:
        """
        Set custom step names.

        Args:
            steps: List of step names
        """
        self._steps = steps
        self._update_display()
