"""
Chat list widget with multi-select functionality.

Displays a scrollable list of chats with checkboxes for selection.
Supports keyboard navigation and bulk selection.
Also supports status display during export (completed, in_progress, failed, skipped).
"""

import hashlib
import re
from enum import Enum
from typing import List, Set, Dict, Optional
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, ListView, ListItem, Label
from textual.reactive import reactive
from textual.containers import Vertical
from textual.binding import Binding
from textual.message import Message


class ChatDisplayStatus(str, Enum):
    """Display status for a chat in the list."""
    PENDING = "pending"       # [ ] Not yet processed
    IN_PROGRESS = "progress"  # [●] Currently being exported
    COMPLETED = "completed"   # [✓] Successfully exported
    FAILED = "failed"         # [✗] Export failed
    SKIPPED = "skipped"       # [⊘] Skipped (e.g., community chat)


class ChatListWidget(Widget):
    """
    Scrollable chat list with multi-select checkboxes.

    Features:
    - Keyboard navigation (Up/Down)
    - Toggle selection (Space)
    - Select all (A)
    - Select none (N)
    - Invert selection (I)
    - Status display during export (✓, ●, ✗, ⊘)
    """

    can_focus = True

    BINDINGS = [
        Binding("space", "toggle_current", "Toggle", show=True),
        Binding("a", "select_all", "Select All", show=True),
        Binding("n", "select_none", "Select None", show=True),
        Binding("i", "invert_selection", "Invert", show=False),
    ]

    DEFAULT_CSS = """
    ChatListWidget {
        border: solid $primary;
        height: 100%;
    }
    """

    # Track selected chat names
    selected_chats: reactive[Set[str]] = reactive(set, init=False)

    # Track chat statuses (for export view)
    chat_statuses: reactive[Dict[str, ChatDisplayStatus]] = reactive(dict, init=False)

    # Mode: "select" (selection mode) or "status" (status display mode)
    display_mode: reactive[str] = reactive("select")

    class SelectionChanged(Message):
        """Message sent when selection changes."""

        def __init__(self, selected: Set[str]) -> None:
            self.selected = selected
            super().__init__()

    def __init__(
        self,
        chats: List[str] | None = None,
        title: str = "CHAT INVENTORY",
        locked: bool = False,
        display_mode: str = "select",
        **kwargs,
    ) -> None:
        """
        Initialize the chat list widget.

        Args:
            chats: List of chat names to display
            title: Title for the panel
            locked: If True, selection is disabled
            display_mode: "select" for selection mode, "status" for status display
        """
        super().__init__(**kwargs)
        self._chats: List[str] = chats or []
        self._title = title
        self._locked = locked
        self.display_mode = display_mode
        self.selected_chats = set(self._chats)  # Select all by default
        self.chat_statuses = {}  # Initialize empty statuses
        # Map chat names to their widget IDs (for efficient lookup)
        self._chat_to_widget_id: Dict[str, str] = {}

    @property
    def _listview_id(self) -> str:
        """Derive a unique ListView ID from the parent widget's ID."""
        if self.id:
            return f"{self.id}-listview"
        return "chat-listview"

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static(f" {self._title} ", classes="chat-list-title")
        yield ListView(*self._create_items(), id=self._listview_id)
        yield Static(
            " > SPACE to select | A select all | N none | [bold]ENTER = Start Export[/bold] ",
            classes="hint",
        )

    def _create_items(self) -> List[ListItem]:
        """Create list items for all chats with unique IDs."""
        items = []
        seen_ids = set()
        self._chat_to_widget_id = {}  # Reset mapping

        for chat in self._chats:
            is_selected = chat in self.selected_chats

            # Generate unique ID with collision prevention
            base_id = f"chat-{self._sanitize_id(chat)}"
            unique_id = base_id
            counter = 1
            while unique_id in seen_ids:
                unique_id = f"{base_id}-{counter}"
                counter += 1
            seen_ids.add(unique_id)

            # Store mapping for efficient lookup
            self._chat_to_widget_id[chat] = unique_id

            item = ListItem(
                Label(self._format_chat_label(chat, is_selected)),
                id=unique_id,
                name=chat,
            )
            items.append(item)
        return items

    def _format_chat_label(self, chat: str, selected: bool) -> str:
        """
        Format a chat label with checkbox or status indicator.

        Args:
            chat: Chat name
            selected: Whether the chat is selected (used in select mode)

        Returns:
            Formatted string with checkbox or status symbol
        """
        if self.display_mode == "status":
            # Status display mode - show export status
            return self._format_status_label(chat)
        else:
            # Selection mode - show checkbox
            if selected:
                return f"[green][✓][/green] {chat}"
            else:
                return f"[dim][ ][/dim] {chat}"

    def _format_status_label(self, chat: str) -> str:
        """
        Format a chat label with status indicator.

        Args:
            chat: Chat name

        Returns:
            Formatted string with status symbol
        """
        status = self.chat_statuses.get(chat, ChatDisplayStatus.PENDING)

        if status == ChatDisplayStatus.COMPLETED:
            return f"[green][✓][/green] {chat}"
        elif status == ChatDisplayStatus.IN_PROGRESS:
            return f"[yellow bold][●][/yellow bold] [yellow]{chat}[/yellow]"
        elif status == ChatDisplayStatus.FAILED:
            return f"[red][✗][/red] {chat}"
        elif status == ChatDisplayStatus.SKIPPED:
            return f"[dim][⊘] {chat}[/dim]"
        else:  # PENDING
            return f"[dim][ ][/dim] {chat}"

    def _sanitize_id(self, name: str) -> str:
        """
        Sanitize a name for use as a widget ID.

        Uses hash suffix for long names to ensure uniqueness while
        keeping IDs recognizable for debugging.
        """
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', name)

        # If name is too long, use hash suffix for uniqueness
        if len(sanitized) > 40:
            name_hash = hashlib.md5(name.encode()).hexdigest()[:8]
            sanitized = f"{sanitized[:30]}_{name_hash}"

        return sanitized

    def _get_current_chat(self) -> str | None:
        """Get the currently highlighted chat name."""
        listview = self.query_one(ListView)
        if listview.highlighted_child:
            return listview.highlighted_child.name
        return None

    def _update_item_display(self, chat: str) -> None:
        """Update the display of a specific chat item."""
        # Use the cached widget ID mapping for efficient lookup
        item_id = self._chat_to_widget_id.get(chat)
        if not item_id:
            # Fallback to old method if not in mapping
            item_id = f"chat-{self._sanitize_id(chat)}"

        try:
            item = self.query_one(f"#{item_id}", ListItem)
            is_selected = chat in self.selected_chats
            label = item.query_one(Label)
            label.update(self._format_chat_label(chat, is_selected))
        except Exception:
            pass  # Item may not exist yet

    def _notify_selection_changed(self) -> None:
        """Post message about selection change."""
        self.post_message(self.SelectionChanged(self.selected_chats.copy()))

    # =========================================================================
    # Actions
    # =========================================================================

    def action_toggle_current(self) -> None:
        """Toggle selection of current item."""
        if self._locked:
            return

        chat = self._get_current_chat()
        if chat:
            if chat in self.selected_chats:
                self.selected_chats.discard(chat)
            else:
                self.selected_chats.add(chat)
            self._update_item_display(chat)
            self._notify_selection_changed()

    def action_select_all(self) -> None:
        """Select all chats."""
        if self._locked:
            return

        self.selected_chats = set(self._chats)
        for chat in self._chats:
            self._update_item_display(chat)
        self._notify_selection_changed()

    def action_select_none(self) -> None:
        """Deselect all chats."""
        if self._locked:
            return

        self.selected_chats = set()
        for chat in self._chats:
            self._update_item_display(chat)
        self._notify_selection_changed()

    def action_invert_selection(self) -> None:
        """Invert current selection."""
        if self._locked:
            return

        all_chats = set(self._chats)
        self.selected_chats = all_chats - self.selected_chats
        for chat in self._chats:
            self._update_item_display(chat)
        self._notify_selection_changed()

    # =========================================================================
    # Public API
    # =========================================================================

    def set_chats(self, chats: List[str], select_all: bool = True) -> None:
        """
        Update the chat list.

        Args:
            chats: New list of chat names
            select_all: Whether to select all chats by default
        """
        self._chats = chats
        if select_all:
            self.selected_chats = set(chats)
        else:
            self.selected_chats = set()

        # Schedule async refresh to avoid race conditions
        self.call_later(self._async_refresh_list)

    async def _async_refresh_list(self) -> None:
        """Refresh the list view asynchronously to avoid race conditions."""
        try:
            listview = self.query_one(ListView)
            # Await removal to ensure DOM is updated before adding new items
            await listview.remove_children()

            # Create and mount all items at once
            items = self._create_items()
            if items:
                await listview.mount(*items)
        except Exception:
            pass  # Widget may not be mounted yet

    def get_selected(self) -> List[str]:
        """
        Get list of selected chat names.

        Returns:
            List of selected chat names in original order
        """
        return [chat for chat in self._chats if chat in self.selected_chats]

    def set_locked(self, locked: bool) -> None:
        """
        Lock or unlock selection.

        Args:
            locked: If True, selection changes are disabled
        """
        self._locked = locked
        # Update hint text
        try:
            hint = self.query_one(".hint", Static)
            if locked:
                hint.update(" [dim]Selection locked during export[/dim] ")
            else:
                hint.update(" > SPACE to select | A select all | N none | [bold]ENTER = Start Export[/bold] ")
        except Exception:
            pass  # Widget may not be mounted yet

    def set_display_mode(self, mode: str) -> None:
        """
        Set the display mode.

        Args:
            mode: "select" for selection mode, "status" for status display
        """
        self.display_mode = mode
        # Refresh all items to show new format
        for chat in self._chats:
            self._update_item_display(chat)

    def update_chat_status(self, name: str, status: ChatDisplayStatus) -> None:
        """
        Update the status of a specific chat.

        Args:
            name: Chat name to update
            status: New status for the chat
        """
        # Create a new dict to trigger reactivity
        new_statuses = dict(self.chat_statuses)
        new_statuses[name] = status
        self.chat_statuses = new_statuses
        # Update the display
        self._update_item_display(name)

    def init_statuses_from_selection(self) -> None:
        """
        Initialize chat statuses from current selection.
        Selected chats get PENDING status, unselected get SKIPPED.
        """
        new_statuses = {}
        for chat in self._chats:
            if chat in self.selected_chats:
                new_statuses[chat] = ChatDisplayStatus.PENDING
            else:
                new_statuses[chat] = ChatDisplayStatus.SKIPPED
        self.chat_statuses = new_statuses

    def get_chats_by_status(self, status: ChatDisplayStatus) -> List[str]:
        """
        Get list of chats with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of chat names with the specified status
        """
        return [
            chat for chat in self._chats
            if self.chat_statuses.get(chat) == status
        ]

    def reset_for_reselection(self) -> None:
        """
        Reset widget for re-selection after a cancelled export.

        Keeps completed chats selected and marks them as COMPLETED.
        All other chats are reset to PENDING status and remain selectable.
        """
        completed_chats = set(self.get_chats_by_status(ChatDisplayStatus.COMPLETED))

        # Keep completed chats selected, re-select incomplete ones too
        self.selected_chats = set(self._chats) - completed_chats | completed_chats

        # Reset statuses: completed stay completed, others go to pending
        new_statuses = {}
        for chat in self._chats:
            if chat in completed_chats:
                new_statuses[chat] = ChatDisplayStatus.COMPLETED
            else:
                new_statuses[chat] = ChatDisplayStatus.PENDING
        self.chat_statuses = new_statuses

        # Switch back to selection mode and unlock
        self.set_display_mode("select")
        self.set_locked(False)

        # Refresh all items
        for chat in self._chats:
            self._update_item_display(chat)

    def get_status_counts(self) -> Dict[str, int]:
        """
        Get counts of chats by status.

        Returns:
            Dictionary with status names as keys and counts as values
        """
        counts = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        for chat in self._chats:
            status = self.chat_statuses.get(chat, ChatDisplayStatus.PENDING)
            counts[status.value] = counts.get(status.value, 0) + 1
        return counts
