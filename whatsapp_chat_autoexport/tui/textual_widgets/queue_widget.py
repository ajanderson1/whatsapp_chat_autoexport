"""
Queue widget for displaying export queue status.

Shows a table of chats with their current status:
- Pending (dimmed)
- In Progress (yellow, bold)
- Completed (green)
- Failed (red)
- Skipped (dimmed, italic)
"""

from typing import List, Optional, Dict
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, DataTable
from textual.widgets.data_table import RowKey
from textual.containers import Vertical

from ...state.models import ChatStatus, ChatState


class QueueWidget(Widget):
    """
    Widget displaying export queue as a table.

    Shows chat names with color-coded status indicators.
    Uses incremental updates for better performance.
    """

    DEFAULT_CSS = """
    QueueWidget {
        border: solid $primary;
        height: 100%;
    }
    """

    STATUS_SYMBOLS = {
        ChatStatus.PENDING: ("○", "dim"),
        ChatStatus.IN_PROGRESS: ("●", "yellow bold"),
        ChatStatus.COMPLETED: ("✓", "green"),
        ChatStatus.FAILED: ("✗", "red"),
        ChatStatus.SKIPPED: ("⊘", "dim italic"),
    }

    def __init__(
        self,
        title: str = "EXPORT QUEUE",
        **kwargs,
    ) -> None:
        """
        Initialize the queue widget.

        Args:
            title: Title for the panel
        """
        super().__init__(**kwargs)
        self._title = title
        self._chats: List[ChatState] = []
        # Map chat names to row keys for incremental updates
        self._chat_row_keys: Dict[str, RowKey] = {}

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static(f" {self._title} ", classes="queue-title")
        yield DataTable(id="queue-table", zebra_stripes=True)

    def on_mount(self) -> None:
        """Set up the table when mounted."""
        table = self.query_one("#queue-table", DataTable)
        table.add_columns("Status", "Chat", "Step")
        table.cursor_type = "row"
        table.show_cursor = False

    def _format_status(self, status: ChatStatus) -> str:
        """
        Format status with symbol and style.

        Args:
            status: The chat status

        Returns:
            Rich-formatted status string
        """
        symbol, style = self.STATUS_SYMBOLS.get(
            status,
            ("?", "dim"),
        )
        return f"[{style}]{symbol}[/{style}]"

    def _format_chat_name(self, chat: ChatState) -> str:
        """
        Format chat name with appropriate style.

        Args:
            chat: The chat state

        Returns:
            Rich-formatted chat name
        """
        name = chat.name
        if len(name) > 25:
            name = name[:22] + "..."

        if chat.status == ChatStatus.IN_PROGRESS:
            return f"[yellow bold]{name}[/yellow bold]"
        elif chat.status == ChatStatus.COMPLETED:
            return f"[green]{name}[/green]"
        elif chat.status == ChatStatus.FAILED:
            return f"[red]{name}[/red]"
        elif chat.status == ChatStatus.SKIPPED:
            return f"[dim italic]{name}[/dim italic]"
        else:
            return f"[dim]{name}[/dim]"

    def _format_step(self, chat: ChatState) -> str:
        """
        Format current step or status info.

        Args:
            chat: The chat state

        Returns:
            Formatted step string
        """
        if chat.status == ChatStatus.IN_PROGRESS:
            step = chat.current_step or "Starting..."
            return f"[yellow]{step}[/yellow]"
        elif chat.status == ChatStatus.FAILED:
            error = chat.error_message or "Error"
            if len(error) > 20:
                error = error[:17] + "..."
            return f"[red]{error}[/red]"
        elif chat.status == ChatStatus.SKIPPED:
            reason = chat.skip_reason or "Skipped"
            if len(reason) > 20:
                reason = reason[:17] + "..."
            return f"[dim]{reason}[/dim]"
        elif chat.status == ChatStatus.COMPLETED:
            return "[green]Done[/green]"
        else:
            return "[dim]Waiting[/dim]"

    def update_queue(self, chats: List[ChatState]) -> None:
        """
        Update the queue with new chat states (full rebuild).

        Args:
            chats: List of ChatState objects
        """
        self._chats = chats
        self._chat_row_keys = {}  # Reset row key mapping
        table = self.query_one("#queue-table", DataTable)
        table.clear()

        for chat in chats:
            row_key = table.add_row(
                self._format_status(chat.status),
                self._format_chat_name(chat),
                self._format_step(chat),
            )
            # Store row key for incremental updates
            self._chat_row_keys[chat.name] = row_key

    def update_chat(
        self,
        name: str,
        status: Optional[ChatStatus] = None,
        step: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Update a specific chat in the queue efficiently.

        Uses incremental cell updates instead of full table rebuild
        for better performance with large queues.

        Args:
            name: Chat name to update
            status: New status (if changing)
            step: Current step (if in progress)
            error: Error message (if failed)
        """
        # Find and update the chat state
        chat_to_update = None
        for chat in self._chats:
            if chat.name == name:
                chat_to_update = chat
                if status is not None:
                    chat.status = status
                if step is not None:
                    chat.current_step = step
                if error is not None:
                    chat.error_message = error
                break

        if chat_to_update is None:
            return

        # Try incremental update using stored row key
        row_key = self._chat_row_keys.get(name)
        if row_key is None:
            # Fallback to full rebuild if row key not found
            self.update_queue(self._chats)
            return

        table = self.query_one("#queue-table", DataTable)

        try:
            # Get column keys (they're stored in order: Status, Chat, Step)
            columns = list(table.columns.keys())
            if len(columns) >= 3:
                # Update each cell in the row
                table.update_cell(row_key, columns[0], self._format_status(chat_to_update.status))
                table.update_cell(row_key, columns[1], self._format_chat_name(chat_to_update))
                table.update_cell(row_key, columns[2], self._format_step(chat_to_update))
            else:
                # Columns not properly set up, fallback to full rebuild
                self.update_queue(self._chats)
        except Exception:
            # Fallback to full rebuild if cell update fails
            self.update_queue(self._chats)

    def get_counts(self) -> dict:
        """
        Get counts for each status.

        Returns:
            Dictionary with status counts
        """
        counts = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        for chat in self._chats:
            if chat.status == ChatStatus.PENDING:
                counts["pending"] += 1
            elif chat.status == ChatStatus.IN_PROGRESS:
                counts["in_progress"] += 1
            elif chat.status == ChatStatus.COMPLETED:
                counts["completed"] += 1
            elif chat.status == ChatStatus.FAILED:
                counts["failed"] += 1
            elif chat.status == ChatStatus.SKIPPED:
                counts["skipped"] += 1
        return counts
