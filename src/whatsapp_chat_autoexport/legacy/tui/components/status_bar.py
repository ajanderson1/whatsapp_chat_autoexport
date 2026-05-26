"""
Status bar component for TUI.

Displays keyboard shortcuts and current application status.
"""

from typing import Optional, List
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class KeyBinding:
    """A keyboard shortcut binding."""

    key: str
    description: str
    enabled: bool = True


class StatusBar:
    """
    Rich-based status bar for the application.

    Displays:
    - Keyboard shortcuts
    - Application status
    - Connection status
    """

    DEFAULT_BINDINGS = [
        KeyBinding("Space", "Pause/Resume"),
        KeyBinding("Q", "Quit"),
        KeyBinding("R", "Retry Failed"),
        KeyBinding("S", "Skip Current"),
        KeyBinding("↑/↓", "Scroll Queue"),
    ]

    def __init__(self, bindings: Optional[List[KeyBinding]] = None):
        """
        Initialize the status bar.

        Args:
            bindings: Optional custom key bindings
        """
        self._bindings = bindings or self.DEFAULT_BINDINGS
        self._status: str = "Ready"
        self._status_style: str = "green"
        self._device_status: str = "Disconnected"
        self._device_style: str = "red"
        self._paused: bool = False

    def set_status(self, status: str, style: str = "white") -> None:
        """
        Set the current status message.

        Args:
            status: Status message
            style: Rich style for the status
        """
        self._status = status
        self._status_style = style

    def set_device_status(self, status: str, connected: bool = False) -> None:
        """
        Set the device connection status.

        Args:
            status: Device status message
            connected: Whether device is connected
        """
        self._device_status = status
        self._device_style = "green" if connected else "red"

    def set_paused(self, paused: bool) -> None:
        """
        Set paused state.

        Args:
            paused: Whether export is paused
        """
        self._paused = paused

    def enable_binding(self, key: str, enabled: bool = True) -> None:
        """
        Enable or disable a key binding.

        Args:
            key: Key to update
            enabled: Whether binding is enabled
        """
        for binding in self._bindings:
            if binding.key == key:
                binding.enabled = enabled
                break

    def render(self) -> Panel:
        """
        Render the status bar.

        Returns:
            Rich Panel containing status bar
        """
        # Main container
        table = Table.grid(expand=True)
        table.add_column(ratio=1)  # Key bindings
        table.add_column(width=30)  # Status
        table.add_column(width=25)  # Device status

        # Key bindings
        bindings_text = self._render_bindings()

        # Status
        status_text = Text()
        if self._paused:
            status_text.append("⏸ PAUSED", style="bold yellow")
        else:
            status_text.append("● ", style=self._status_style)
            status_text.append(self._status, style=self._status_style)

        # Device status
        device_text = Text()
        device_text.append("📱 ", style=self._device_style)
        device_text.append(self._device_status, style=self._device_style)

        table.add_row(bindings_text, status_text, device_text)

        return Panel(
            table,
            border_style="dim",
            padding=(0, 1),
        )

    def _render_bindings(self) -> Text:
        """Render key bindings."""
        text = Text()

        for i, binding in enumerate(self._bindings):
            if i > 0:
                text.append("  ", style="dim")

            if binding.enabled:
                text.append(f"[{binding.key}]", style="bold cyan")
                text.append(f" {binding.description}", style="white")
            else:
                text.append(f"[{binding.key}]", style="dim")
                text.append(f" {binding.description}", style="dim")

        return text

    def render_compact(self) -> Text:
        """
        Render a compact single-line status bar.

        Returns:
            Rich Text with status information
        """
        text = Text()

        # Pause indicator
        if self._paused:
            text.append(" ⏸ PAUSED ", style="bold yellow on dark_red")
            text.append(" ")

        # Status
        text.append(f"● {self._status}", style=self._status_style)
        text.append(" | ", style="dim")

        # Device
        text.append(f"📱 {self._device_status}", style=self._device_style)
        text.append(" | ", style="dim")

        # Key hints
        text.append("[Space]", style="bold cyan")
        text.append(" pause ", style="dim")
        text.append("[Q]", style="bold cyan")
        text.append(" quit", style="dim")

        return text

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()


class MinimalStatusBar:
    """
    Minimal status bar showing only essential information.

    For use in screens where space is limited.
    """

    def __init__(self):
        """Initialize minimal status bar."""
        self._message: str = ""
        self._message_style: str = "dim"

    def set_message(self, message: str, style: str = "dim") -> None:
        """Set the status message."""
        self._message = message
        self._message_style = style

    def info(self, message: str) -> None:
        """Show an info message."""
        self.set_message(f"ℹ {message}", "blue")

    def success(self, message: str) -> None:
        """Show a success message."""
        self.set_message(f"✓ {message}", "green")

    def warning(self, message: str) -> None:
        """Show a warning message."""
        self.set_message(f"⚠ {message}", "yellow")

    def error(self, message: str) -> None:
        """Show an error message."""
        self.set_message(f"✗ {message}", "red")

    def render(self) -> Text:
        """Render the minimal status bar."""
        return Text(self._message, style=self._message_style)

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
