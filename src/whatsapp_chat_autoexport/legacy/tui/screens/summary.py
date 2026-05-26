"""
Summary screen for TUI.

Displays export results and statistics.
"""

from typing import Optional, List
from datetime import timedelta
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align

from whatsapp_chat_autoexport.state.models import ChatStatus, ChatState, SessionState


@dataclass
class ExportResult:
    """Result of a single chat export."""

    name: str
    status: ChatStatus
    duration: float = 0.0
    error: Optional[str] = None


class SummaryScreen:
    """
    Summary screen displayed after export completion.

    Shows:
    - Overall statistics
    - List of completed/failed/skipped chats
    - Duration information
    - Next steps
    """

    def __init__(self):
        """Initialize the summary screen."""
        self._results: List[ExportResult] = []
        self._total_duration: float = 0.0
        self._output_path: Optional[str] = None
        self._show_details: bool = True
        self._selected_tab: int = 0  # 0=All, 1=Completed, 2=Failed, 3=Skipped

    @property
    def completed_count(self) -> int:
        """Get number of completed exports."""
        return sum(1 for r in self._results if r.status == ChatStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        """Get number of failed exports."""
        return sum(1 for r in self._results if r.status == ChatStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        """Get number of skipped exports."""
        return sum(1 for r in self._results if r.status == ChatStatus.SKIPPED)

    def set_results(self, results: List[ExportResult]) -> None:
        """Set the export results."""
        self._results = results

    def set_from_session(self, session: SessionState) -> None:
        """
        Set results from a SessionState.

        Args:
            session: SessionState with completed chats
        """
        self._results = []
        for chat in session.chats.values():
            self._results.append(
                ExportResult(
                    name=chat.name,
                    status=chat.status,
                    duration=chat.duration_seconds,
                    error=chat.error_message,
                )
            )

    def set_duration(self, duration: float) -> None:
        """Set total duration in seconds."""
        self._total_duration = duration

    def set_output_path(self, path: str) -> None:
        """Set output path."""
        self._output_path = path

    def toggle_details(self) -> None:
        """Toggle showing detailed results."""
        self._show_details = not self._show_details

    def next_tab(self) -> None:
        """Move to next tab."""
        self._selected_tab = (self._selected_tab + 1) % 4

    def prev_tab(self) -> None:
        """Move to previous tab."""
        self._selected_tab = (self._selected_tab - 1) % 4

    def _filtered_results(self) -> List[ExportResult]:
        """Get results filtered by current tab."""
        if self._selected_tab == 0:
            return self._results
        elif self._selected_tab == 1:
            return [r for r in self._results if r.status == ChatStatus.COMPLETED]
        elif self._selected_tab == 2:
            return [r for r in self._results if r.status == ChatStatus.FAILED]
        else:
            return [r for r in self._results if r.status == ChatStatus.SKIPPED]

    def render(self) -> Panel:
        """
        Render the summary screen.

        Returns:
            Rich Panel containing summary display
        """
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        # Header with overall status
        header = self._render_header()
        table.add_row(header)
        table.add_row("")

        # Statistics panel
        stats = self._render_statistics()
        table.add_row(stats)
        table.add_row("")

        # Tabs
        tabs = self._render_tabs()
        table.add_row(tabs)
        table.add_row("")

        # Details list if enabled
        if self._show_details:
            details = self._render_details()
            table.add_row(details)
            table.add_row("")

        # Output path
        if self._output_path:
            path_text = Text()
            path_text.append("Output: ", style="dim")
            path_text.append(self._output_path, style="cyan")
            table.add_row(path_text)
            table.add_row("")

        # Navigation hints
        hints = self._render_hints()
        table.add_row(hints)

        # Determine border color based on results
        if self.failed_count > 0:
            border_style = "yellow"
            title_style = "bold yellow"
        else:
            border_style = "green"
            title_style = "bold green"

        return Panel(
            table,
            title=f"[{title_style}]Export Complete[/]",
            border_style=border_style,
            padding=(1, 2),
        )

    def _render_header(self) -> Text:
        """Render header with overall status."""
        header = Text()

        total = len(self._results)
        completed = self.completed_count
        failed = self.failed_count

        if failed == 0:
            header.append("✓ ", style="bold green")
            header.append(f"All {completed} chats exported successfully!", style="green")
        elif completed == 0:
            header.append("✗ ", style="bold red")
            header.append("Export failed for all chats", style="red")
        else:
            header.append("⚠ ", style="bold yellow")
            header.append(f"{completed} of {total} chats exported", style="yellow")

        return Align.center(header)

    def _render_statistics(self) -> Panel:
        """Render statistics panel."""
        stats_table = Table.grid(expand=True)
        stats_table.add_column(ratio=1)
        stats_table.add_column(ratio=1)
        stats_table.add_column(ratio=1)
        stats_table.add_column(ratio=1)

        # Completed
        completed = Text()
        completed.append(f"{self.completed_count}\n", style="bold green")
        completed.append("Completed", style="dim")

        # Failed
        failed = Text()
        failed.append(f"{self.failed_count}\n", style="bold red")
        failed.append("Failed", style="dim")

        # Skipped
        skipped = Text()
        skipped.append(f"{self.skipped_count}\n", style="bold yellow")
        skipped.append("Skipped", style="dim")

        # Duration
        duration = Text()
        duration.append(f"{self._format_duration(self._total_duration)}\n", style="bold cyan")
        duration.append("Duration", style="dim")

        stats_table.add_row(
            Align.center(completed),
            Align.center(failed),
            Align.center(skipped),
            Align.center(duration),
        )

        return Panel(
            stats_table,
            border_style="dim",
            padding=(0, 2),
        )

    def _render_tabs(self) -> Text:
        """Render filter tabs."""
        tabs = Text()

        tab_names = [
            f"All ({len(self._results)})",
            f"Completed ({self.completed_count})",
            f"Failed ({self.failed_count})",
            f"Skipped ({self.skipped_count})",
        ]

        for i, name in enumerate(tab_names):
            if i == self._selected_tab:
                tabs.append(f" [{name}] ", style="bold white on blue")
            else:
                tabs.append(f" {name} ", style="dim")

        return Align.center(tabs)

    def _render_details(self) -> Table:
        """Render detailed results list."""
        details = Table.grid(expand=True)
        details.add_column(width=3)
        details.add_column(ratio=1)
        details.add_column(width=10)
        details.add_column(width=30)

        filtered = self._filtered_results()

        if not filtered:
            details.add_row(
                "",
                Text("No results in this category", style="dim"),
                "",
                "",
            )
            return details

        # Show max 10 results
        for result in filtered[:10]:
            # Status icon
            if result.status == ChatStatus.COMPLETED:
                icon = "✓"
                icon_style = "green"
                name_style = "green"
            elif result.status == ChatStatus.FAILED:
                icon = "✗"
                icon_style = "red"
                name_style = "red"
            else:
                icon = "◌"
                icon_style = "yellow"
                name_style = "yellow"

            # Duration
            if result.duration > 0:
                duration_text = Text(self._format_duration(result.duration), style="dim")
            else:
                duration_text = Text("-", style="dim")

            # Error/info
            if result.error:
                info = result.error[:27] + "..." if len(result.error) > 30 else result.error
                info_text = Text(info, style="dim red" if result.status == ChatStatus.FAILED else "dim yellow")
            else:
                info_text = Text("")

            details.add_row(
                Text(icon, style=icon_style),
                Text(result.name, style=name_style),
                duration_text,
                info_text,
            )

        if len(filtered) > 10:
            details.add_row(
                "",
                Text(f"... and {len(filtered) - 10} more", style="dim"),
                "",
                "",
            )

        return details

    def _render_hints(self) -> Text:
        """Render navigation hints."""
        hints = Text()

        hints.append("[←/→]", style="bold cyan")
        hints.append(" Switch tabs  ", style="dim")
        hints.append("[D]", style="bold cyan")
        hints.append(" Toggle details  ", style="dim")
        hints.append("[R]", style="bold cyan")
        hints.append(" Retry failed  ", style="dim")
        hints.append("[Enter]", style="bold cyan")
        hints.append(" Exit", style="dim")

        return Align.center(hints)

    def _format_duration(self, seconds: float) -> str:
        """Format duration for display."""
        if seconds < 60:
            return f"{seconds:.1f}s"

        minutes = int(seconds // 60)
        secs = int(seconds % 60)

        if minutes < 60:
            return f"{minutes}m {secs}s"

        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m"

    def render_failed_details(self) -> Panel:
        """Render detailed view of failed exports."""
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        failed = [r for r in self._results if r.status == ChatStatus.FAILED]

        if not failed:
            table.add_row(Text("No failed exports", style="dim"))
        else:
            for result in failed:
                entry = Text()
                entry.append(f"✗ {result.name}\n", style="bold red")
                if result.error:
                    entry.append(f"  {result.error}\n", style="dim red")
                table.add_row(entry)

        return Panel(
            table,
            title="[bold red]Failed Exports[/]",
            border_style="red",
            padding=(1, 2),
        )

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
