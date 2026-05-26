"""
Cancel confirmation modal for export/processing operations.

Shows a dialog when the user presses Escape during an active export,
allowing them to return to selection, exit the app, or continue.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Checkbox
from textual.containers import Vertical, Horizontal
from textual.binding import Binding


class CancelModal(ModalScreen[str]):
    """
    Modal confirmation dialog shown when cancelling an export.

    Returns one of:
    - "btn-return": Return to chat selection
    - "btn-exit": Exit application
    - "btn-continue": Dismiss and continue export
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Continue", show=False),
    ]

    DEFAULT_CSS = """
    CancelModal {
        align: center middle;
    }

    CancelModal .modal-container {
        width: 75;
        height: auto;
        max-height: 80%;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }

    CancelModal .modal-title {
        text-style: bold;
        text-align: center;
        color: $warning;
        padding-bottom: 1;
    }

    CancelModal .modal-message {
        color: $text;
        padding-bottom: 1;
    }

    CancelModal .modal-checkbox {
        padding: 0 0 1 0;
    }

    CancelModal .modal-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    CancelModal .modal-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        current_chat: Optional[str] = None,
        completed: int = 0,
        total: int = 0,
        message: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the cancel modal.

        Args:
            current_chat: Name of the chat currently being exported (if any)
            completed: Number of chats completed so far
            total: Total number of chats selected for export
            message: Optional override message (e.g., for failure warnings)
        """
        super().__init__(**kwargs)
        self._current_chat = current_chat
        self._completed = completed
        self._total = total
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-container"):
            yield Static("Cancel Export?", classes="modal-title")

            # Progress message
            if self._message:
                msg = self._message
            elif self._total > 0:
                msg = f"Progress: {self._completed} of {self._total} chats exported."
            else:
                msg = "Export is in progress."
            if self._current_chat:
                msg += f"\nCurrently exporting: [yellow]{self._current_chat}[/yellow]"
            yield Static(msg, classes="modal-message")

            # Option to wait for current chat
            if self._current_chat:
                yield Checkbox(
                    "Wait for current chat to finish",
                    value=True,
                    id="wait-for-current",
                    classes="modal-checkbox",
                )

            with Horizontal(classes="modal-buttons"):
                yield Button(
                    "Return to Selection",
                    id="btn-return",
                    variant="primary",
                )
                yield Button(
                    "Exit App",
                    id="btn-exit",
                    variant="error",
                )
                yield Button(
                    "Continue Export",
                    id="btn-continue",
                    variant="default",
                )

    @property
    def wait_for_current(self) -> bool:
        """Whether the user wants to wait for the current chat to finish."""
        try:
            checkbox = self.query_one("#wait-for-current", Checkbox)
            return checkbox.value
        except Exception:
            return False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        self.dismiss(event.button.id)

    def action_dismiss_modal(self) -> None:
        """Dismiss modal (continue export)."""
        self.dismiss("btn-continue")
