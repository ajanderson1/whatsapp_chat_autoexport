"""
DiscoverSelectPane -- chat discovery and selection pane.

Flow:
1. MainScreen calls start_discovery() after device connection
2. Live-stream discovered chat names directly into ChatListWidget
3. When discovery completes, finalize counts and enable export
4. User adjusts selection + settings
5. "Start Export" emits StartExport with the selected chat list
"""

from typing import List

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, Button
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
    - Live-stream discovered chats directly into ChatListWidget
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
        self._discovery_generation: int = 0
        self._discovered_count: int = 0
        self._scanning_chats: bool = False
        self._discovery_worker: Worker | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        # --- Discovery status + selection ---
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
                "Refresh Chats",
                id="btn-refresh-chats",
                variant="default",
                disabled=True,
            )
            yield Button(
                "Start Export",
                id="btn-start-export",
                variant="success",
                disabled=True,
            )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def start_discovery(self) -> None:
        """Kick off chat collection in a background worker."""
        if self._scanning_chats:
            return
        if getattr(self.app, "driver", None) is None:
            return

        self._scanning_chats = True
        self._discovery_generation += 1
        self._discovered_count = 0

        # Reset the ChatListWidget for a fresh scan
        try:
            chat_list = self.query_one("#chat-select-list", ChatListWidget)
            chat_list.clear_chats()
            self.query_one("#btn-refresh-chats", Button).disabled = True
            self.query_one("#btn-start-export", Button).disabled = True
            self.query_one("#selection-count", Static).update(
                "[dim]Discovering chats...[/dim]"
            )
        except Exception:
            pass

        self._log("Starting chat discovery...")
        self._discovery_worker = self.run_worker(
            self._collect_chats, exclusive=True, thread=True
        )

    def stop_discovery(self) -> None:
        """Cancel a running discovery worker, if any."""
        if self._discovery_worker is not None:
            self._discovery_worker.cancel()
            self._discovery_worker = None
        self._scanning_chats = False
        self._discovery_generation += 1

    def _collect_chats(self) -> List[str]:
        """Worker: collect chats from the device (runs in thread)."""
        generation = self._discovery_generation
        driver = getattr(self.app, "driver", None)
        if driver is None:
            raise RuntimeError("No driver connected")

        limit = getattr(self.app, "limit", None)

        def on_found(chat: object) -> None:
            """Live callback -- called from driver thread with ChatMetadata."""
            if self._discovery_generation != generation:
                return  # stale callback
            name = chat.name if hasattr(chat, "name") else str(chat)
            self.app.call_from_thread(self._add_discovered_chat, name, generation)

        chats = driver.collect_all_chats(
            limit=limit,
            on_chat_found=on_found,
        )
        return [c.name if hasattr(c, "name") else str(c) for c in chats]

    def _add_discovered_chat(self, name: str, generation: int) -> None:
        """Add a single chat directly to the ChatListWidget (called on main thread)."""
        if generation != self._discovery_generation:
            return

        try:
            chat_list = self.query_one("#chat-select-list", ChatListWidget)
            chat_list.add_chat(name, selected=True)
            self._discovered_count += 1
            self.query_one("#selection-count", Static).update(
                f"[dim]Discovering... {self._discovered_count} chats found[/dim]"
            )
        except Exception:
            pass

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle discovery worker completion."""
        # Ignore state changes from stale workers (e.g. a previous discovery
        # that was superseded by a reconnect). Only react to the worker we
        # currently track as "the" discovery worker.
        if event.worker is not self._discovery_worker:
            return

        if event.state == WorkerState.SUCCESS:
            self._scanning_chats = False

            try:
                chat_list = self.query_one("#chat-select-list", ChatListWidget)
                count = len(chat_list.get_selected())
                self.query_one("#btn-refresh-chats", Button).disabled = False
                self.query_one("#btn-start-export", Button).disabled = (count == 0)
            except Exception:
                pass

            self._update_selection_count()
            self._log(f"Discovery complete: {self._discovered_count} chats found")
            self.post_message(self.SelectionChanged(self._discovered_count))

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
            self.query_one("#btn-start-export", Button).disabled = (count == 0)
        except Exception:
            pass
        self._update_selection_count()
        self.post_message(self.SelectionChanged(count))

    def on_chat_list_widget_refresh_requested(
        self, event: ChatListWidget.RefreshRequested
    ) -> None:
        """Re-run chat discovery when the Refresh button is clicked."""
        # Cancel any stale/in-flight discovery first so a manual refresh is
        # never silently dropped by the `_scanning_chats` guard.
        self.stop_discovery()
        self.start_discovery()

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
            self.start_discovery()
        elif event.button.id in ("btn-start-export", "btn-chat-start-export"):
            self._handle_start_export()

    def _handle_start_export(self) -> None:
        """Validate and emit StartExport. Stops discovery if still running."""
        self.stop_discovery()
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
        self.start_discovery()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_selection_count(self) -> None:
        """Update the selection count display with 'Selected X of Y chats'."""
        try:
            chat_list = self.query_one("#chat-select-list", ChatListWidget)
            selected = len(chat_list.get_selected())
            total = len(chat_list._chats)
            self.query_one("#selection-count", Static).update(
                f"[dim]Selected {selected} of {total} chats[/dim]"
            )
        except Exception:
            pass

    def _log(self, message: str) -> None:
        """Write to the screen-level ActivityLog."""
        try:
            log_widget = self.screen.query_one(ActivityLog)
            log_widget.log(message)
        except Exception:
            pass
