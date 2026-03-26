"""
Welcome screen for TUI.

Displays application title and initial options.
"""

from typing import Optional, Callable

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align


class WelcomeScreen:
    """
    Welcome screen displayed on application start.

    Shows:
    - Application title/logo
    - Version info
    - Quick start options
    """

    LOGO = """
╦ ╦┬ ┬┌─┐┌┬┐┌─┐╔═╗┌─┐┌─┐
║║║├─┤├─┤ │ └─┐╠═╣├─┘├─┘
╚╩╝┴ ┴┴ ┴ ┴ └─┘╩ ╩┴  ┴
    Export Tool
"""

    def __init__(self, version: str = "2.0.0"):
        """
        Initialize the welcome screen.

        Args:
            version: Application version string
        """
        self._version = version
        self._selected_option: int = 0
        self._options = [
            ("Export Wizard", "Interactive step-by-step export"),
            ("Quick Export", "Export all chats with default settings"),
            ("Settings", "Configure export options"),
            ("Help", "View documentation and tips"),
            ("Exit", "Quit the application"),
        ]

    @property
    def selected_option(self) -> int:
        """Get the currently selected option index."""
        return self._selected_option

    def select_next(self) -> None:
        """Move selection to next option."""
        self._selected_option = (self._selected_option + 1) % len(self._options)

    def select_prev(self) -> None:
        """Move selection to previous option."""
        self._selected_option = (self._selected_option - 1) % len(self._options)

    def get_selected_action(self) -> str:
        """Get the action name for the selected option."""
        actions = ["wizard", "quick", "settings", "help", "exit"]
        return actions[self._selected_option]

    def render(self) -> Panel:
        """
        Render the welcome screen.

        Returns:
            Rich Panel containing welcome display
        """
        # Main container
        table = Table.grid(expand=True)
        table.add_column(justify="center", ratio=1)

        # Logo
        logo_text = Text(self.LOGO, style="bold cyan")
        table.add_row(Align.center(logo_text))

        # Version
        version_text = Text(f"Version {self._version}", style="dim")
        table.add_row(Align.center(version_text))

        # Spacer
        table.add_row("")

        # Options
        options_table = Table.grid()
        options_table.add_column(width=3)
        options_table.add_column(width=20)
        options_table.add_column()

        for i, (name, description) in enumerate(self._options):
            if i == self._selected_option:
                marker = "▸"
                marker_style = "bold cyan"
                name_style = "bold white"
                desc_style = "cyan"
            else:
                marker = " "
                marker_style = "dim"
                name_style = "white"
                desc_style = "dim"

            options_table.add_row(
                Text(marker, style=marker_style),
                Text(name, style=name_style),
                Text(f"  {description}", style=desc_style),
            )

        table.add_row(Align.center(options_table))

        # Spacer
        table.add_row("")

        # Navigation hints
        hints = Text()
        hints.append("[↑/↓]", style="bold cyan")
        hints.append(" Navigate  ", style="dim")
        hints.append("[Enter]", style="bold cyan")
        hints.append(" Select  ", style="dim")
        hints.append("[Q]", style="bold cyan")
        hints.append(" Quit", style="dim")
        table.add_row(Align.center(hints))

        return Panel(
            table,
            title="[bold white]WhatsApp Chat Auto-Export[/]",
            border_style="cyan",
            padding=(1, 2),
        )

    def render_compact(self) -> Panel:
        """
        Render a compact version for smaller terminals.

        Returns:
            Rich Panel with compact layout
        """
        table = Table.grid(expand=True)
        table.add_column(justify="center", ratio=1)

        # Title
        title = Text("WhatsApp Export Tool", style="bold cyan")
        table.add_row(Align.center(title))

        # Options inline
        options = Text()
        for i, (name, _) in enumerate(self._options):
            if i == self._selected_option:
                options.append(f" [{name}] ", style="bold white on blue")
            else:
                options.append(f" {name} ", style="dim")

        table.add_row(Align.center(options))

        return Panel(
            table,
            border_style="cyan",
            padding=(0, 1),
        )

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
