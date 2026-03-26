"""
Chat selection screen for TUI.

Allows users to select which chats to export.
"""

from typing import Optional, List, Set
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align


@dataclass
class ChatInfo:
    """Information about a chat for selection."""

    name: str
    message_count: int = 0
    last_message: str = ""
    is_group: bool = False
    is_community: bool = False
    already_exported: bool = False


class ChatSelectionScreen:
    """
    Chat selection screen.

    Shows:
    - List of available chats
    - Selection checkboxes
    - Filter/search functionality
    - Select all/none options
    """

    def __init__(self, max_visible: int = 15):
        """
        Initialize the chat selection screen.

        Args:
            max_visible: Maximum chats visible at once
        """
        self._chats: List[ChatInfo] = []
        self._selected: Set[str] = set()
        self._cursor: int = 0
        self._scroll_offset: int = 0
        self._max_visible = max_visible
        self._filter_text: str = ""
        self._show_exported: bool = True
        self._loading: bool = False

    @property
    def chats(self) -> List[ChatInfo]:
        """Get all chats."""
        return self._chats

    @property
    def selected_chats(self) -> List[str]:
        """Get list of selected chat names."""
        return list(self._selected)

    @property
    def selection_count(self) -> int:
        """Get number of selected chats."""
        return len(self._selected)

    def set_chats(self, chats: List[ChatInfo]) -> None:
        """Set the available chats."""
        self._chats = chats
        self._cursor = 0
        self._scroll_offset = 0

    def set_loading(self, loading: bool) -> None:
        """Set loading state."""
        self._loading = loading

    def set_filter(self, text: str) -> None:
        """Set filter text."""
        self._filter_text = text.lower()
        self._cursor = 0
        self._scroll_offset = 0

    def toggle_show_exported(self) -> None:
        """Toggle showing already exported chats."""
        self._show_exported = not self._show_exported

    def _filtered_chats(self) -> List[ChatInfo]:
        """Get filtered list of chats."""
        filtered = []
        for chat in self._chats:
            # Apply filter text
            if self._filter_text and self._filter_text not in chat.name.lower():
                continue

            # Apply exported filter
            if not self._show_exported and chat.already_exported:
                continue

            filtered.append(chat)

        return filtered

    def move_up(self) -> None:
        """Move cursor up."""
        filtered = self._filtered_chats()
        if filtered and self._cursor > 0:
            self._cursor -= 1
            self._adjust_scroll()

    def move_down(self) -> None:
        """Move cursor down."""
        filtered = self._filtered_chats()
        if filtered and self._cursor < len(filtered) - 1:
            self._cursor += 1
            self._adjust_scroll()

    def page_up(self) -> None:
        """Move cursor up by a page."""
        self._cursor = max(0, self._cursor - self._max_visible)
        self._adjust_scroll()

    def page_down(self) -> None:
        """Move cursor down by a page."""
        filtered = self._filtered_chats()
        self._cursor = min(len(filtered) - 1, self._cursor + self._max_visible)
        self._adjust_scroll()

    def _adjust_scroll(self) -> None:
        """Adjust scroll to keep cursor visible."""
        if self._cursor < self._scroll_offset:
            self._scroll_offset = self._cursor
        elif self._cursor >= self._scroll_offset + self._max_visible:
            self._scroll_offset = self._cursor - self._max_visible + 1

    def toggle_selection(self) -> None:
        """Toggle selection of current chat."""
        filtered = self._filtered_chats()
        if filtered and 0 <= self._cursor < len(filtered):
            chat = filtered[self._cursor]
            if chat.is_community:
                return  # Can't select community chats
            if chat.name in self._selected:
                self._selected.remove(chat.name)
            else:
                self._selected.add(chat.name)

    def select_all(self) -> None:
        """Select all visible chats."""
        for chat in self._filtered_chats():
            if not chat.is_community:
                self._selected.add(chat.name)

    def select_none(self) -> None:
        """Deselect all chats."""
        self._selected.clear()

    def invert_selection(self) -> None:
        """Invert selection."""
        for chat in self._filtered_chats():
            if chat.is_community:
                continue
            if chat.name in self._selected:
                self._selected.remove(chat.name)
            else:
                self._selected.add(chat.name)

    def render(self) -> Panel:
        """
        Render the chat selection screen.

        Returns:
            Rich Panel containing selection display
        """
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        # Header with selection count
        header = self._render_header()
        table.add_row(header)
        table.add_row("")

        # Filter bar
        filter_bar = self._render_filter_bar()
        table.add_row(filter_bar)
        table.add_row("")

        if self._loading:
            # Loading indicator
            loading_text = Text("Collecting chats from WhatsApp...", style="yellow")
            table.add_row(Align.center(loading_text))
        else:
            # Chat list
            chat_list = self._render_chat_list()
            table.add_row(chat_list)

        # Navigation hints
        table.add_row("")
        hints = self._render_hints()
        table.add_row(hints)

        return Panel(
            table,
            title="[bold white]Select Chats to Export[/]",
            border_style="cyan",
            padding=(1, 2),
        )

    def _render_header(self) -> Text:
        """Render header with selection info."""
        header = Text()

        total = len(self._chats)
        filtered_count = len(self._filtered_chats())
        selected = len(self._selected)

        header.append(f"{selected}", style="bold cyan")
        header.append(f"/{total} selected", style="dim")

        if filtered_count != total:
            header.append(f"  ({filtered_count} shown)", style="dim yellow")

        return header

    def _render_filter_bar(self) -> Text:
        """Render filter/search bar."""
        bar = Text()

        bar.append("🔍 Filter: ", style="dim")
        if self._filter_text:
            bar.append(self._filter_text, style="bold cyan")
        else:
            bar.append("(type to filter)", style="dim")

        bar.append("  ")

        if self._show_exported:
            bar.append("[✓] Show exported", style="dim green")
        else:
            bar.append("[ ] Show exported", style="dim")

        return bar

    def _render_chat_list(self) -> Table:
        """Render the chat list."""
        list_table = Table.grid(expand=True)
        list_table.add_column(width=3)   # Selection marker
        list_table.add_column(width=3)   # Type icon
        list_table.add_column(ratio=1)   # Chat name
        list_table.add_column(width=15)  # Status

        filtered = self._filtered_chats()

        if not filtered:
            no_results = Text("No chats match the filter", style="dim")
            list_table.add_row("", "", Align.center(no_results), "")
            return list_table

        # Scroll indicators
        start = self._scroll_offset
        end = min(start + self._max_visible, len(filtered))

        if start > 0:
            list_table.add_row(
                "",
                "",
                Text(f"↑ {start} more above", style="dim"),
                "",
            )

        for i in range(start, end):
            chat = filtered[i]
            is_current = i == self._cursor
            is_selected = chat.name in self._selected

            # Selection marker
            if chat.is_community:
                marker = "⊘"
                marker_style = "dim red"
            elif is_selected:
                marker = "◉"
                marker_style = "bold green"
            else:
                marker = "○"
                marker_style = "dim"

            # Type icon
            if chat.is_community:
                icon = "🏛"
            elif chat.is_group:
                icon = "👥"
            else:
                icon = "💬"

            # Name styling
            if is_current:
                name_style = "bold white on blue"
            elif chat.is_community:
                name_style = "dim red"
            elif is_selected:
                name_style = "green"
            else:
                name_style = "white"

            # Status
            if chat.is_community:
                status = Text("(cannot export)", style="dim red")
            elif chat.already_exported:
                status = Text("✓ exported", style="dim green")
            else:
                status = Text("", style="dim")

            list_table.add_row(
                Text(marker, style=marker_style),
                Text(icon),
                Text(chat.name, style=name_style),
                status,
            )

        remaining = len(filtered) - end
        if remaining > 0:
            list_table.add_row(
                "",
                "",
                Text(f"↓ {remaining} more below", style="dim"),
                "",
            )

        return list_table

    def _render_hints(self) -> Text:
        """Render navigation hints."""
        hints = Text()

        hints.append("[↑/↓]", style="bold cyan")
        hints.append(" Navigate  ", style="dim")
        hints.append("[Space]", style="bold cyan")
        hints.append(" Toggle  ", style="dim")
        hints.append("[A]", style="bold cyan")
        hints.append(" All  ", style="dim")
        hints.append("[N]", style="bold cyan")
        hints.append(" None  ", style="dim")
        hints.append("[E]", style="bold cyan")
        hints.append(" Toggle exported  ", style="dim")
        hints.append("[Enter]", style="bold cyan")
        hints.append(" Continue", style="dim")

        return hints

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
