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
from ..textual_widgets.prerequisite_banner import PrerequisiteBanner, BannerStatus
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

    def on_mount(self) -> None:
        """Refresh prerequisite banners on mount."""
        self._refresh_banners()

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

        # --- Prerequisite banners ---
        with Vertical(id="prerequisite-banners"):
            yield PrerequisiteBanner(
                key="drive",
                label="Google Drive",
                status=BannerStatus.UNMET,
                detail="not signed in",
                hint="open Settings tab to configure",
            )
            yield PrerequisiteBanner(
                key="apikey",
                label="Transcription API key",
                status=BannerStatus.OK,
            )
            yield PrerequisiteBanner(
                key="whatsapp-version",
                label="WhatsApp version",
                status=BannerStatus.OK,
            )

        # --- Bottom bar ---
        with Horizontal(classes="bottom-bar"):
            yield Static(
                "[dim]Selected: 0 chats[/dim]",
                id="selection-count",
            )
            yield Static(
                "",
                id="blocker-reason",
                classes="blocker-reason",
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
                self.query_one("#btn-refresh-chats", Button).disabled = False
            except Exception:
                pass

            self._update_selection_count()
            self._update_gate()
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
        self._update_selection_count()
        self._update_gate()
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
        self._refresh_banners()

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
    # Prerequisite banners
    # ------------------------------------------------------------------

    def on_settings_panel_drive_status_changed(
        self, event: SettingsPanel.DriveStatusChanged
    ) -> None:
        """Refresh banners when Drive auth state changes."""
        self._refresh_banners()

    def _refresh_banners(self) -> None:
        """Re-evaluate all prerequisite banners from current app state."""
        self._refresh_drive_banner()
        self._refresh_apikey_banner()
        self._refresh_whatsapp_version_banner()
        self._update_gate()

    def _refresh_drive_banner(self) -> None:
        """Update the Drive prerequisite banner."""
        try:
            banner = self.query_one("#banner-drive", PrerequisiteBanner)
            if getattr(self.app, "drive_credentials", None) is not None:
                email = getattr(self.app, "drive_user_email", None) or "unknown"
                banner.update_status(
                    BannerStatus.OK,
                    detail=f"signed in as {email}",
                )
            else:
                # Check if client_secrets at least exists
                try:
                    from ...google_drive.auth import GoogleDriveAuth
                    auth = GoogleDriveAuth()
                    if auth.has_client_secrets():
                        banner.update_status(
                            BannerStatus.UNMET,
                            detail="not signed in",
                            hint="open Settings tab and click Sign in to Drive",
                        )
                    else:
                        banner.update_status(
                            BannerStatus.UNMET,
                            detail="client_secrets.json not found",
                            hint="open Settings tab to configure",
                        )
                except Exception:
                    banner.update_status(
                        BannerStatus.UNMET,
                        detail="not configured",
                        hint="open Settings tab to configure",
                    )
        except Exception:
            pass

    def _refresh_apikey_banner(self) -> None:
        """Update the API key prerequisite banner."""
        try:
            banner = self.query_one("#banner-apikey", PrerequisiteBanner)
            transcribe = getattr(self.app, "transcribe_audio", False)
            if not transcribe:
                banner.update_status(BannerStatus.OK)
                return

            provider = getattr(self.app, "transcription_provider", "whisper")
            try:
                settings = self.query_one("#settings-panel", SettingsPanel)
                if settings.has_valid_transcription_provider():
                    banner.update_status(BannerStatus.OK)
                else:
                    display = "OpenAI" if provider == "whisper" else provider.title()
                    banner.update_status(
                        BannerStatus.UNMET,
                        detail=f"{display} API key missing or invalid",
                        hint="open Settings tab to configure",
                    )
            except Exception:
                banner.update_status(BannerStatus.OK)
        except Exception:
            pass

    def _refresh_whatsapp_version_banner(self) -> None:
        """Update the WhatsApp version warning banner."""
        try:
            banner = self.query_one("#banner-whatsapp-version", PrerequisiteBanner)
            device_version = getattr(self.app, "whatsapp_version", None)
            if device_version is None:
                banner.update_status(BannerStatus.OK)
                return

            from ...constants import TESTED_WHATSAPP_VERSION
            if device_version == TESTED_WHATSAPP_VERSION:
                banner.update_status(BannerStatus.OK)
            else:
                banner.update_status(
                    BannerStatus.WARNING,
                    detail=f"v{device_version} (tested with v{TESTED_WHATSAPP_VERSION})",
                    hint="things may break",
                )
        except Exception:
            pass

    def _compute_blocking_prerequisites(self) -> list[str]:
        """Return human-readable list of unmet prerequisites that block export."""
        blockers = []
        try:
            drive_banner = self.query_one("#banner-drive", PrerequisiteBanner)
            if drive_banner.is_blocking:
                blockers.append("Drive not signed in")
        except Exception:
            pass
        try:
            apikey_banner = self.query_one("#banner-apikey", PrerequisiteBanner)
            if apikey_banner.is_blocking:
                blockers.append("API key missing")
        except Exception:
            pass
        return blockers

    def _update_gate(self) -> None:
        """Update Start Export button and blocker reason based on prerequisites + selection."""
        blockers = self._compute_blocking_prerequisites()

        try:
            chat_list = self.query_one("#chat-select-list", ChatListWidget)
            has_selection = len(chat_list.get_selected()) > 0
        except Exception:
            has_selection = False

        can_export = has_selection and not blockers

        try:
            self.query_one("#btn-start-export", Button).disabled = not can_export
        except Exception:
            pass

        try:
            reason_widget = self.query_one("#blocker-reason", Static)
            if blockers:
                reason_widget.update(
                    f"[red]Cannot export \u2014 {', '.join(blockers)}[/red]"
                )
            else:
                reason_widget.update("")
        except Exception:
            pass

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
