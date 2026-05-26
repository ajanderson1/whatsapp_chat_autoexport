"""
Color scheme selection modal.

Allows users to select from 10 predefined color schemes.
The selected theme is applied immediately and persisted to disk.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, ListItem, ListView, Label
from textual.containers import Vertical
from textual.binding import Binding

from ...config.themes import (
    get_all_theme_names,
    get_theme_display_name,
)
from ...config.theme_manager import get_theme_manager


class ColorSchemeModal(ModalScreen[str | None]):
    """
    Color scheme selection modal.

    Displays all available themes with the current theme marked.
    Selecting a theme applies it immediately and closes the modal.

    Returns:
    - Theme name if a theme was selected
    - None if dismissed with Escape
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Back", show=False),
        Binding("enter", "select_theme", "Apply", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    ColorSchemeModal {
        align: center middle;
    }

    ColorSchemeModal .modal-container {
        width: 50;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    ColorSchemeModal .modal-title {
        text-style: bold;
        text-align: center;
        color: $primary;
        padding-bottom: 1;
    }

    ColorSchemeModal ListView {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
        padding: 0;
    }

    ColorSchemeModal ListItem {
        padding: 0 1;
        height: auto;
    }

    ColorSchemeModal ListItem:hover {
        background: $primary-background-lighten-1;
    }

    ColorSchemeModal ListItem.-selected {
        background: $primary-background-lighten-2;
    }

    ColorSchemeModal .theme-label {
        width: 100%;
    }

    ColorSchemeModal .theme-current {
        color: $success;
    }

    ColorSchemeModal .modal-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary-background;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._theme_manager = get_theme_manager()
        self._current_theme = self._theme_manager.get_saved_theme()

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-container"):
            yield Static("SELECT COLOR SCHEME", classes="modal-title")

            with ListView(id="theme-list"):
                for theme_name in get_all_theme_names():
                    display_name = get_theme_display_name(theme_name)
                    is_current = theme_name == self._current_theme

                    # Create label with checkmark for current theme
                    if is_current:
                        label_text = f"  {display_name} [green]\u2713[/green]"
                        label_classes = "theme-label theme-current"
                    else:
                        label_text = f"  {display_name}"
                        label_classes = "theme-label"

                    yield ListItem(
                        Label(label_text, classes=label_classes),
                        id=f"theme-{theme_name}",
                    )

            yield Static("[Enter] Apply  [Escape] Back", classes="modal-footer")

    def on_mount(self) -> None:
        """Focus the list view and select current theme."""
        list_view = self.query_one("#theme-list", ListView)
        list_view.focus()

        # Find and select the current theme
        theme_names = get_all_theme_names()
        try:
            current_index = theme_names.index(self._current_theme)
            list_view.index = current_index
        except ValueError:
            list_view.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle theme selection from list (double-click or Enter)."""
        self._apply_theme(event.item.id)

    def action_select_theme(self) -> None:
        """Handle Enter key to select current theme."""
        list_view = self.query_one("#theme-list", ListView)
        if list_view.highlighted_child:
            self._apply_theme(list_view.highlighted_child.id)

    def _apply_theme(self, item_id: str | None) -> None:
        """Apply the selected theme."""
        if item_id is None:
            return

        # Extract theme name from "theme-{name}" format
        theme_name = item_id.replace("theme-", "")

        # Apply the theme to the app
        self.app.theme = theme_name

        # Save the theme preference
        self._theme_manager.save_theme(theme_name)

        # Dismiss with the theme name to signal success
        self.dismiss(theme_name)

    def action_dismiss_modal(self) -> None:
        """Dismiss the modal without changing theme."""
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Move cursor up in the list."""
        list_view = self.query_one("#theme-list", ListView)
        list_view.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down in the list."""
        list_view = self.query_one("#theme-list", ListView)
        list_view.action_cursor_down()
