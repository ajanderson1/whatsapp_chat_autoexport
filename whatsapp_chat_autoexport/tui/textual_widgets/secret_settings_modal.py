"""
Secret settings modal triggered by '/' key.

Provides access to hidden settings like color scheme selection.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, ListItem, ListView, Label
from textual.containers import Vertical
from textual.binding import Binding


class SecretSettingsModal(ModalScreen[str | None]):
    """
    Hidden settings modal triggered by '/' key.

    Provides access to:
    - Color Scheme selection
    - (Future options can be added here)

    Returns:
    - Selected option ID if an option is chosen
    - None if dismissed
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "select_option", "Select", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    DEFAULT_CSS = """
    SecretSettingsModal {
        align: center middle;
    }

    SecretSettingsModal .modal-container {
        width: 50;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    SecretSettingsModal .modal-title {
        text-style: bold;
        text-align: center;
        color: $primary;
        padding-bottom: 1;
    }

    SecretSettingsModal ListView {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
        padding: 0;
    }

    SecretSettingsModal ListItem {
        padding: 0 1;
        height: auto;
    }

    SecretSettingsModal ListItem:hover {
        background: $primary-background-lighten-1;
    }

    SecretSettingsModal ListItem.-selected {
        background: $primary-background-lighten-2;
    }

    SecretSettingsModal .option-label {
        width: 100%;
    }

    SecretSettingsModal .modal-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary-background;
        margin-top: 1;
    }
    """

    # Available settings options
    OPTIONS = [
        ("color-scheme", "Color Scheme"),
        # Future options can be added here:
        # ("keyboard-shortcuts", "Keyboard Shortcuts"),
        # ("advanced", "Advanced Settings"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-container"):
            yield Static("SECRET SETTINGS", classes="modal-title")

            with ListView(id="options-list"):
                for option_id, option_label in self.OPTIONS:
                    yield ListItem(
                        Label(f"  {option_label}", classes="option-label"),
                        id=f"option-{option_id}",
                    )

            yield Static("[Escape] Close", classes="modal-footer")

    def on_mount(self) -> None:
        """Focus the list view on mount."""
        list_view = self.query_one("#options-list", ListView)
        list_view.focus()
        # Select first item
        if list_view.children:
            list_view.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle option selection from list."""
        self._handle_selection(event.item.id)

    def action_select_option(self) -> None:
        """Handle Enter key to select current option."""
        list_view = self.query_one("#options-list", ListView)
        if list_view.highlighted_child:
            self._handle_selection(list_view.highlighted_child.id)

    def _handle_selection(self, item_id: str | None) -> None:
        """Handle selection of an option."""
        if item_id is None:
            return

        # Extract option ID from "option-{id}" format
        option_id = item_id.replace("option-", "")

        if option_id == "color-scheme":
            self._open_color_scheme_modal()
        else:
            # Future options would be handled here
            self.dismiss(option_id)

    def _open_color_scheme_modal(self) -> None:
        """Open the color scheme selection modal."""
        from .color_scheme_modal import ColorSchemeModal

        def on_color_scheme_dismissed(result: str | None) -> None:
            """Handle color scheme modal dismissal."""
            if result:
                # Theme was selected and applied, close this modal too
                self.dismiss(result)
            # If result is None, user pressed escape - stay in this modal

        self.app.push_screen(ColorSchemeModal(), on_color_scheme_dismissed)

    def action_dismiss_modal(self) -> None:
        """Dismiss the modal."""
        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Move cursor up in the list."""
        list_view = self.query_one("#options-list", ListView)
        list_view.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down in the list."""
        list_view = self.query_one("#options-list", ListView)
        list_view.action_cursor_down()
