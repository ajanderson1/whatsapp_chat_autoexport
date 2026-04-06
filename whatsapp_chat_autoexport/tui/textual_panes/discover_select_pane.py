"""
DiscoverSelectPane -- chat discovery and selection pane.

Combines the discovery inventory section (from DiscoveryScreen) with the
chat selection and settings layout (from SelectionScreen) into a single
pane that lives inside the "Discover & Select" TabPane.

Flow:
1. On first show, auto-start chat discovery if driver is connected
2. Live-stream discovered chat names into a ListView
3. When discovery completes, populate ChatListWidget and pre-select all
4. User adjusts selection + settings
5. "Start Export" emits StartExport with the selected chat list
"""

from typing import List

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, Button, ListView, ListItem, Label, Rule
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from ..textual_widgets.activity_log import ActivityLog
from ..textual_widgets.chat_list import ChatListWidget
from ..textual_widgets.settings_panel import SettingsPanel, DEFAULT_OUTPUT_DIR


class DiscoverSelectPane(Container):
    """
    Combined chat discovery and selection pane.

    Responsibilities:
    - Run chat discovery via the WhatsApp driver
    - Live-stream discovered chats into a discovery inventory
    - Present a ChatListWidget for chat selection with a SettingsPanel
    - Emit StartExport when the user is ready to export
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class SelectionChanged(Message):
        """Emitted when chat selection changes."""

        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    class StartExport(Message):
        """Emitted when user clicks Start Export."""

        def __init__(self, selected_chats: list[str]) -> None:
            super().__init__()
            self.selected_chats = selected_chats

    class ConnectionLost(Message):
        """Emitted when driver connection is lost during discovery."""
        pass

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    BINDINGS = [
        Binding("f", "refresh_chats", "Refresh Chats", show=False),
    ]

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._first_show: bool = True
        self._discovery_generation: int = 0
        self._discovered_chats: List[str] = []
        self._scanning_chats: bool = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # --- Discovery section ---
        yield Rule(line_style="heavy")
        yield Static("[bold]DISCOVER CHATS[/bold]", classes="discovery-title")
        yield Static("Discovered 0 chats", id="discovery-count")
        yield ListView(id="discovery-inventory")
        with Horizontal(id="discovery-buttons"):
            yield Button(
                "Refresh Chats",
                id="btn-refresh-chats",
                variant="default",
                disabled=True,
            )

        yield Rule(line_style="heavy")

        # --- Selection section ---
        with Horizontal(classes="main-content"):
            with Vertical(classes="left-panel"):
                yield ChatListWidget(
                    chats=[],
                    title="CHAT INVENTORY",
                    id="chat-select-list",
                )
            with Vertical(classes="right-panel"):
                yield SettingsPanel(
                    include_media=getattr(self.app, "include_media", True),
                    transcribe_audio=getattr(self.app, "transcribe_audio", True),
                    delete_from_drive=getattr(self.app, "delete_from_drive", False),
                    output_folder=str(self.app.output_dir) if hasattr(self.app, "output_dir") and self.app.output_dir else DEFAULT_OUTPUT_DIR,
                    transcription_provider=getattr(self.app, "transcription_provider", "whisper"),
                    id="settings-panel",
                )

        # --- Bottom bar ---
        with Horizontal(classes="bottom-bar"):
            yield Static(
                "[dim]Selected: 0 chats[/dim]",
                id="selection-count",
            )
            yield Button(
                "Start Export",
                id="btn-start-export",
                variant="success",
                disabled=True,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        """Auto-start discovery on first show if driver is connected."""
        if self._first_show:
            self._first_show = False
            if getattr(self.app, "driver", None) is not None:
                self._start_discovery()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _start_discovery(self) -> None:
        """Kick off chat collection in a background worker."""
        if self._scanning_chats:
            return

        self._scanning_chats = True
        self._discovery_generation += 1
        self._discovered_chats = []

        # Reset UI
        try:
            self.query_one("#discovery-count", Static).update("Discovering chats...")
            inventory = self.query_one("#discovery-inventory", ListView)
            inventory.clear()
            self.query_one("#btn-refresh-chats", Button).disabled = True
        except Exception:
            pass

        self._log("Starting chat discovery...")
        self.run_worker(self._collect_chats, exclusive=True, thread=True)

    def _collect_chats(self) -> List[str]:
        """Worker: collect chats from the device (runs in thread)."""
        generation = self._discovery_generation
        driver = getattr(self.app, "driver", None)
        if driver is None:
            raise RuntimeError("No driver connected")

        limit = getattr(self.app, "limit", None)

        def on_found(name: str) -> None:
            """Live callback -- called from driver thread."""
            if self._discovery_generation != generation:
                return  # stale callback
            self.app.call_from_thread(self._add_discovered_chat, name, generation)

        chats = driver.collect_all_chats(
            limit=limit,
            interactive=False,
            on_found_callback=on_found,
        )
        return [c.name if hasattr(c, "name") else str(c) for c in chats]

    def _add_discovered_chat(self, name: str, generation: int) -> None:
        """Add a single chat to the discovery inventory (called on main thread)."""
        if generation != self._discovery_generation:
            return
        self._discovered_chats.append(name)
        try:
            inventory = self.query_one("#discovery-inventory", ListView)
            inventory.append(ListItem(Label(f"  {name}")))
            self.query_one("#discovery-count", Static).update(
                f"Discovered {len(self._discovered_chats)} chats"
            )
        except Exception:
            pass

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle discovery worker completion."""
        if event.state == WorkerState.SUCCESS:
            self._scanning_chats = False
            chat_names = event.worker.result or self._discovered_chats

            # Populate the selection ChatListWidget
            try:
                chat_list = self.query_one("#chat-select-list", ChatListWidget)
                chat_list.set_chats(chat_names, select_all=True)
            except Exception:
                pass

            # Update counts
            count = len(chat_names)
            try:
                self.query_one("#discovery-count", Static).update(
                    f"Discovered {count} chats"
                )
                self.query_one("#selection-count", Static).update(
                    f"[dim]Selected: {count} chats[/dim]"
                )
                self.query_one("#btn-refresh-chats", Button).disabled = False
                self.query_one("#btn-start-export", Button).disabled = (count == 0)
            except Exception:
                pass

            self._log(f"Discovery complete: {count} chats found")
            self.post_message(self.SelectionChanged(count))

        elif event.state == WorkerState.ERROR:
            self._scanning_chats = False
            try:
                self.query_one("#btn-refresh-chats", Button).disabled = False
            except Exception:
                pass
            self._log("Chat discovery failed -- check connection")
            self.post_message(self.ConnectionLost())

        elif event.state == WorkerState.CANCELLED:
            self._scanning_chats = False
            try:
                self.query_one("#btn-refresh-chats", Button).disabled = False
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------

    def on_chat_list_widget_selection_changed(
        self, event: ChatListWidget.SelectionChanged
    ) -> None:
        """Bubble up selection changes."""
        count = len(event.selected)
        try:
            self.query_one("#selection-count", Static).update(
                f"[dim]Selected: {count} chats[/dim]"
            )
            self.query_one("#btn-start-export", Button).disabled = (count == 0)
        except Exception:
            pass
        self.post_message(self.SelectionChanged(count))

    # ------------------------------------------------------------------
    # Settings handling
    # ------------------------------------------------------------------

    def on_settings_panel_settings_changed(
        self, event: SettingsPanel.SettingsChanged
    ) -> None:
        """Persist settings changes to the app."""
        app = self.app
        app.include_media = event.include_media
        app.transcribe_audio = event.transcribe_audio
        app.delete_from_drive = event.delete_from_drive
        if hasattr(app, "output_dir"):
            from pathlib import Path
            app.output_dir = Path(event.output_folder)
        app.transcription_provider = event.transcription_provider

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-refresh-chats":
            self._start_discovery()
        elif event.button.id == "btn-start-export":
            self._handle_start_export()

    def _handle_start_export(self) -> None:
        """Validate and emit StartExport."""
        try:
            chat_list = self.query_one("#chat-select-list", ChatListWidget)
            selected = chat_list.get_selected()
        except Exception:
            selected = []

        if not selected:
            self._log("No chats selected")
            return

        self.post_message(self.StartExport(selected))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh_chats(self) -> None:
        """Action bound to 'f' key."""
        self._start_discovery()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Write to the screen-level ActivityLog."""
        try:
            log_widget = self.screen.query_one(ActivityLog)
            log_widget.write(message)
        except Exception:
            pass
