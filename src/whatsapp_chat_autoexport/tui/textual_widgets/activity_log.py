"""
Activity log widget for displaying real-time updates.

Shows a scrolling log of export activities with:
- Timestamped messages
- Color-coded status (success, error, warning, info)
- Auto-scroll to latest
"""

from datetime import datetime
from typing import List
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, RichLog
from textual.containers import Vertical


class ActivityLog(Widget):
    """
    Scrollable activity log with colored status messages.

    Features:
    - Auto-scroll to latest message
    - Color-coded message types
    - Timestamp prefixes
    - Maximum message limit to prevent memory issues
    """

    DEFAULT_CSS = """
    ActivityLog {
        border: solid $primary;
        height: 100%;
    }
    """

    MAX_MESSAGES = 500  # Maximum messages to keep

    def __init__(
        self,
        title: str = "ACTIVITY",
        show_timestamps: bool = True,
        **kwargs,
    ) -> None:
        """
        Initialize the activity log.

        Args:
            title: Title for the panel
            show_timestamps: Whether to show timestamps
        """
        super().__init__(**kwargs)
        self._title = title
        self._show_timestamps = show_timestamps
        self._message_count = 0

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static(f" {self._title} ", classes="activity-title")
        yield RichLog(
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
            max_lines=self.MAX_MESSAGES,  # Enforce message limit to prevent memory growth
            id="activity-richlog",
        )

    def _get_timestamp(self) -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%H:%M:%S")

    def _format_message(self, message: str, style: str = "") -> str:
        """
        Format a message with optional timestamp and style.

        Args:
            message: The message text
            style: Optional Rich style string

        Returns:
            Formatted message string
        """
        parts = []

        if self._show_timestamps:
            parts.append(f"[dim]{self._get_timestamp()}[/dim]")

        if style:
            parts.append(f"[{style}]{message}[/{style}]")
        else:
            parts.append(message)

        return " ".join(parts)

    def log(self, message: str) -> None:
        """
        Add a regular log message.

        Args:
            message: Message to log
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        richlog.write(self._format_message(message))
        self._message_count += 1

    def log_info(self, message: str) -> None:
        """
        Add an info message (cyan).

        Args:
            message: Message to log
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        richlog.write(self._format_message(message, "cyan"))
        self._message_count += 1

    def log_success(self, message: str) -> None:
        """
        Add a success message (green).

        Args:
            message: Message to log
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(f"[bold green]OK[/bold green] {message}")
        richlog.write(formatted)
        self._message_count += 1

    def log_warning(self, message: str) -> None:
        """
        Add a warning message (yellow).

        Args:
            message: Message to log
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(f"[bold yellow]![/bold yellow] {message}", "yellow")
        richlog.write(formatted)
        self._message_count += 1

    def log_error(self, message: str) -> None:
        """
        Add an error message (red).

        Args:
            message: Message to log
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(f"[bold red]X[/bold red] {message}", "red")
        richlog.write(formatted)
        self._message_count += 1

    def log_step(self, chat: str, step: str) -> None:
        """
        Log an export step for a chat.

        Args:
            chat: Chat name
            step: Step description
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(
            f"[cyan]{step}[/cyan]",
        )
        richlog.write(formatted)
        self._message_count += 1

    def log_chat_start(self, chat: str) -> None:
        """
        Log the start of a chat export.

        Args:
            chat: Chat name
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(
            f"[bold]Starting:[/bold] {chat}",
            "white",
        )
        richlog.write(formatted)
        self._message_count += 1

    def log_chat_complete(self, chat: str) -> None:
        """
        Log completion of a chat export.

        Args:
            chat: Chat name
        """
        self.log_success(f"Completed: {chat}")

    def log_chat_failed(self, chat: str, error: str) -> None:
        """
        Log failure of a chat export.

        Args:
            chat: Chat name
            error: Error message
        """
        self.log_error(f"Failed: {chat} - {error}")

    def log_chat_skipped(self, chat: str, reason: str) -> None:
        """
        Log skipping of a chat.

        Args:
            chat: Chat name
            reason: Skip reason
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        formatted = self._format_message(
            f"[dim]Skipped: {chat} ({reason})[/dim]",
        )
        richlog.write(formatted)
        self._message_count += 1

    def clear(self) -> None:
        """Clear all log messages."""
        richlog = self.query_one("#activity-richlog", RichLog)
        richlog.clear()
        self._message_count = 0

    def write_batch(self, messages: List[str]) -> None:
        """
        Write multiple messages at once.

        Args:
            messages: List of messages to write
        """
        richlog = self.query_one("#activity-richlog", RichLog)
        for message in messages:
            richlog.write(self._format_message(message))
        self._message_count += len(messages)
