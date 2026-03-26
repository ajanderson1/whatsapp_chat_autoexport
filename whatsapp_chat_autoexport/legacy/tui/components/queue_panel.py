"""
Queue panel component for TUI.

Displays the export queue with status indicators.
"""

from typing import Optional, List
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from whatsapp_chat_autoexport.state.models import ChatStatus, ChatState


@dataclass
class QueueItemDisplay:
    """Display information for a queue item."""

    name: str
    status: ChatStatus
    step: str = ""
    error: Optional[str] = None


class QueuePanel:
    """
    Rich-based queue panel for export operations.

    Displays:
    - List of chats in the queue
    - Status indicators (pending, in progress, completed, failed, skipped)
    - Current processing step for active chat
    """

    # Status icons and colors
    STATUS_DISPLAY = {
        ChatStatus.PENDING: ("○", "dim white"),
        ChatStatus.IN_PROGRESS: ("●", "bold yellow"),
        ChatStatus.COMPLETED: ("✓", "green"),
        ChatStatus.FAILED: ("✗", "red"),
        ChatStatus.SKIPPED: ("◌", "yellow"),
        ChatStatus.PAUSED: ("⏸", "cyan"),
    }

    def __init__(self, max_visible: int = 10):
        """
        Initialize the queue panel.

        Args:
            max_visible: Maximum number of items to show at once
        """
        self._items: List[QueueItemDisplay] = []
        self._max_visible = max_visible
        self._scroll_offset = 0
        self._current_index: int = 0

    def set_items(self, items: List[QueueItemDisplay]) -> None:
        """
        Set the queue items.

        Args:
            items: List of queue items to display
        """
        self._items = items

    def update_from_chats(self, chats: List[ChatState]) -> None:
        """
        Update from list of ChatState objects.

        Args:
            chats: List of ChatState instances
        """
        self._items = [
            QueueItemDisplay(
                name=chat.name,
                status=chat.status,
                step=chat.steps_completed[-1] if chat.steps_completed else "",
                error=chat.error_message,
            )
            for chat in sorted(chats, key=lambda c: c.index)
        ]

        # Auto-scroll to current item
        for i, item in enumerate(self._items):
            if item.status == ChatStatus.IN_PROGRESS:
                self._current_index = i
                self._adjust_scroll()
                break

    def update_item(
        self,
        name: str,
        status: Optional[ChatStatus] = None,
        step: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Update a specific item in the queue.

        Args:
            name: Name of the chat to update
            status: New status (optional)
            step: Current step (optional)
            error: Error message (optional)
        """
        for i, item in enumerate(self._items):
            if item.name == name:
                if status is not None:
                    item.status = status
                    if status == ChatStatus.IN_PROGRESS:
                        self._current_index = i
                        self._adjust_scroll()
                if step is not None:
                    item.step = step
                if error is not None:
                    item.error = error
                break

    def scroll_up(self) -> None:
        """Scroll the view up."""
        if self._scroll_offset > 0:
            self._scroll_offset -= 1

    def scroll_down(self) -> None:
        """Scroll the view down."""
        max_offset = max(0, len(self._items) - self._max_visible)
        if self._scroll_offset < max_offset:
            self._scroll_offset += 1

    def _adjust_scroll(self) -> None:
        """Adjust scroll to keep current item visible."""
        if self._current_index < self._scroll_offset:
            self._scroll_offset = self._current_index
        elif self._current_index >= self._scroll_offset + self._max_visible:
            self._scroll_offset = self._current_index - self._max_visible + 1

    def render(self) -> Panel:
        """
        Render the queue panel.

        Returns:
            Rich Panel containing queue display
        """
        # Create table
        table = Table.grid(expand=True)
        table.add_column(width=3)  # Status icon
        table.add_column(ratio=1)  # Chat name
        table.add_column(width=20)  # Step/status info

        # Calculate visible range
        start = self._scroll_offset
        end = min(start + self._max_visible, len(self._items))

        # Show scroll indicator if needed
        if start > 0:
            table.add_row(
                Text("↑", style="dim"),
                Text(f"... {start} more above", style="dim"),
                Text(""),
            )

        # Render visible items
        for i in range(start, end):
            item = self._items[i]
            icon, color = self.STATUS_DISPLAY.get(
                item.status,
                ("?", "white"),
            )

            # Icon
            icon_text = Text(icon, style=color)

            # Name with highlight for current
            name_style = "bold " + color if item.status == ChatStatus.IN_PROGRESS else color
            name_text = Text(item.name, style=name_style)

            # Status info
            if item.status == ChatStatus.IN_PROGRESS and item.step:
                info_text = Text(item.step, style="yellow")
            elif item.status == ChatStatus.FAILED and item.error:
                # Truncate error message
                error = item.error[:17] + "..." if len(item.error) > 20 else item.error
                info_text = Text(error, style="red")
            elif item.status == ChatStatus.SKIPPED and item.error:
                info_text = Text(item.error[:17] + "...", style="yellow")
            else:
                info_text = Text(item.status.value, style="dim")

            table.add_row(icon_text, name_text, info_text)

        # Show scroll indicator if needed
        remaining = len(self._items) - end
        if remaining > 0:
            table.add_row(
                Text("↓", style="dim"),
                Text(f"... {remaining} more below", style="dim"),
                Text(""),
            )

        # Build title with counts
        title = self._build_title()

        return Panel(
            table,
            title=title,
            border_style="blue",
            padding=(0, 1),
        )

    def _build_title(self) -> str:
        """Build panel title with counts."""
        counts = {
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "pending": 0,
        }

        for item in self._items:
            if item.status == ChatStatus.COMPLETED:
                counts["completed"] += 1
            elif item.status == ChatStatus.FAILED:
                counts["failed"] += 1
            elif item.status == ChatStatus.SKIPPED:
                counts["skipped"] += 1
            elif item.status in (ChatStatus.PENDING, ChatStatus.IN_PROGRESS):
                counts["pending"] += 1

        parts = []
        if counts["completed"]:
            parts.append(f"[green]{counts['completed']}✓[/]")
        if counts["failed"]:
            parts.append(f"[red]{counts['failed']}✗[/]")
        if counts["skipped"]:
            parts.append(f"[yellow]{counts['skipped']}◌[/]")

        stats = " ".join(parts) if parts else ""
        return f"[bold white]Queue[/] ({len(self._items)} chats) {stats}"

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()


class CompactQueuePanel(QueuePanel):
    """
    Compact version of queue panel showing only summary.

    Shows completed/failed/skipped/pending counts without individual items.
    """

    def render(self) -> Panel:
        """Render compact queue summary."""
        counts = {
            ChatStatus.COMPLETED: 0,
            ChatStatus.FAILED: 0,
            ChatStatus.SKIPPED: 0,
            ChatStatus.IN_PROGRESS: 0,
            ChatStatus.PENDING: 0,
            ChatStatus.PAUSED: 0,
        }

        current_chat = None
        for item in self._items:
            counts[item.status] += 1
            if item.status == ChatStatus.IN_PROGRESS:
                current_chat = item.name

        # Build summary text
        summary = Text()

        # Current chat
        if current_chat:
            summary.append("Processing: ", style="dim")
            summary.append(current_chat, style="bold cyan")
            summary.append("\n")

        # Stats line
        summary.append("✓ ", style="green")
        summary.append(str(counts[ChatStatus.COMPLETED]), style="bold green")
        summary.append("  ", style="dim")

        summary.append("✗ ", style="red")
        summary.append(str(counts[ChatStatus.FAILED]), style="bold red")
        summary.append("  ", style="dim")

        summary.append("◌ ", style="yellow")
        summary.append(str(counts[ChatStatus.SKIPPED]), style="bold yellow")
        summary.append("  ", style="dim")

        remaining = counts[ChatStatus.PENDING] + counts[ChatStatus.IN_PROGRESS]
        summary.append("○ ", style="dim")
        summary.append(str(remaining), style="dim")
        summary.append(" remaining", style="dim")

        return Panel(
            summary,
            title="[bold white]Queue Summary[/]",
            border_style="blue",
            padding=(0, 1),
        )
