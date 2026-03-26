"""
Help screen showing keyboard shortcuts and usage information.

Displayed as a modal overlay when user presses H.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Vertical, Container
from textual.binding import Binding


class HelpScreen(ModalScreen):
    """
    Modal help screen showing keyboard shortcuts.

    Displayed as an overlay that can be dismissed with Escape or H.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("h", "dismiss", "Close", show=False),
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Compose the help screen layout."""
        with Container(classes="help-container"):
            yield Static("[bold]KEYBOARD SHORTCUTS[/bold]", classes="help-title")

            yield Static("[bold cyan]Global[/bold cyan]", classes="help-section")
            yield self._shortcut("Q", "Quit application")
            yield self._shortcut("H", "Show/hide this help")
            yield self._shortcut("Escape", "Go back / Close")

            yield Static("[bold cyan]Discovery Screen[/bold cyan]", classes="help-section")
            yield self._shortcut("R", "Refresh device list")
            yield self._shortcut("Enter", "Connect to selected device")
            yield self._shortcut("D", "Use dry-run mode (testing)")

            yield Static("[bold cyan]Selection Screen[/bold cyan]", classes="help-section")
            yield self._shortcut("Space", "Toggle chat selection")
            yield self._shortcut("A", "Select all chats")
            yield self._shortcut("N", "Deselect all chats")
            yield self._shortcut("I", "Invert selection")
            yield self._shortcut("Enter", "Confirm and start export")
            yield self._shortcut("Up/Down", "Navigate chat list")

            yield Static("[bold cyan]Export Screen[/bold cyan]", classes="help-section")
            yield self._shortcut("P", "Pause/Resume export")
            yield self._shortcut("S", "Skip current chat")

            yield Static(
                "\n[dim]Press Escape, H, or ? to close[/dim]",
                classes="help-footer",
            )

    def _shortcut(self, key: str, description: str) -> Static:
        """
        Create a shortcut help line.

        Args:
            key: The keyboard key
            description: Description of what it does

        Returns:
            Static widget with formatted shortcut
        """
        return Static(f"  [bold cyan]{key:12}[/bold cyan] {description}")

    def action_dismiss(self) -> None:
        """Dismiss the help screen."""
        self.app.pop_screen()
