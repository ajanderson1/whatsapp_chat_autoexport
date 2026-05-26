"""
MainScreen with TabbedContent for the WhatsApp Exporter TUI.

Replaces the previous DiscoveryScreen + SelectionScreen two-screen model
with a single screen containing 4 tabs: Connect, Select, Export, Summary.

Message handlers on this screen orchestrate tab transitions and auto-advance:
- ConnectPane.Connected       -> store driver, unlock D&S, auto-advance
- DiscoverSelectPane.SelectionChanged -> unlock/lock Export tab
- DiscoverSelectPane.StartExport      -> switch to Export, start export
- ExportPane.ExportComplete           -> unlock Summary, start processing
- ExportPane.CancelledReturnToSelection -> switch to D&S, reset export
- DiscoverSelectPane.ConnectionLost   -> cascade disable downstream tabs
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static, TabbedContent, TabPane
from textual.reactive import reactive

from ..textual_panes.connect_pane import ConnectPane
from ..textual_panes.discover_select_pane import DiscoverSelectPane
from ..textual_panes.export_pane import ExportPane
from ..textual_panes.summary_pane import SummaryPane
from ..textual_widgets.activity_log import ActivityLog


class MainScreen(Screen):
    """
    Single-screen layout with tabbed navigation for the export workflow.

    Tabs are progressively enabled as the user advances through the workflow:
    1. Connect - always enabled
    2. Select - enabled after device connection
    3. Export - enabled after chat selection
    4. Summary - enabled after export completes
    """

    BINDINGS = [
        Binding("1", "switch_tab('connect')", "Connect", show=False),
        Binding("2", "switch_tab('discover-select')", "Select", show=False),
        Binding("3", "switch_tab('export')", "Export", show=False),
        Binding("4", "switch_tab('summary')", "Summary", show=False),
        Binding("e", "trigger_export", "Start Export", show=False),
    ]

    # Reactive state that drives tab enable/disable cascade
    _connected: reactive[bool] = reactive(False)
    _has_selection: reactive[bool] = reactive(False)
    _export_complete: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the main screen layout."""
        with TabbedContent():
            with TabPane("1 Connect", id="connect"):
                yield ConnectPane()
            with TabPane("2 Select", id="discover-select"):
                yield DiscoverSelectPane()
            with TabPane("3 Export", id="export"):
                yield ExportPane()
            with TabPane("4 Summary", id="summary"):
                yield SummaryPane()
        yield ActivityLog()

    def on_mount(self) -> None:
        """Disable all tabs except Connect on mount."""
        tabbed = self.query_one(TabbedContent)
        tabbed.disable_tab("discover-select")
        tabbed.disable_tab("export")
        tabbed.disable_tab("summary")

    # ------------------------------------------------------------------
    # Reactive watchers — drive tab enable/disable cascade
    # ------------------------------------------------------------------

    def watch__connected(self, value: bool) -> None:
        """Enable/disable tabs based on connection state."""
        tabbed = self.query_one(TabbedContent)
        if value:
            tabbed.enable_tab("discover-select")
        else:
            # Cascade reset
            self._has_selection = False
            self._export_complete = False
            tabbed.disable_tab("discover-select")
            tabbed.disable_tab("export")
            tabbed.disable_tab("summary")

    def watch__has_selection(self, value: bool) -> None:
        """Enable/disable tabs based on selection state."""
        tabbed = self.query_one(TabbedContent)
        if value:
            tabbed.enable_tab("export")
        else:
            # Cascade reset
            self._export_complete = False
            tabbed.disable_tab("export")
            tabbed.disable_tab("summary")

    def watch__export_complete(self, value: bool) -> None:
        """Enable/disable summary tab based on export state."""
        tabbed = self.query_one(TabbedContent)
        if value:
            tabbed.enable_tab("summary")
        else:
            tabbed.disable_tab("summary")

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a tab if it is not disabled."""
        tabbed = self.query_one(TabbedContent)
        tab = tabbed.get_tab(tab_id)
        if not tab.disabled:
            tabbed.active = tab_id

    def action_trigger_export(self) -> None:
        """Trigger start export from keyboard shortcut."""
        tabbed = self.query_one(TabbedContent)
        if tabbed.active == "discover-select":
            ds = self.query_one(DiscoverSelectPane)
            ds._handle_start_export()

    # ------------------------------------------------------------------
    # Message handlers — orchestrate workflow transitions
    # ------------------------------------------------------------------

    def on_connect_pane_connected(self, event: ConnectPane.Connected) -> None:
        """Handle device connection -- store driver, unlock Select, auto-advance."""
        # If a previous discovery is still running (e.g. on a stale driver
        # after a disconnect/reconnect), cancel it before swapping the driver
        # so the fresh discovery we are about to kick off isn't dropped by the
        # `_scanning_chats` guard in DiscoverSelectPane.start_discovery().
        ds = self.query_one(DiscoverSelectPane)
        ds.stop_discovery()

        self.app._whatsapp_driver = event.driver
        self._connected = True

        # Read WhatsApp version from device (non-blocking, best-effort)
        if event.driver is not None:
            try:
                self.app._whatsapp_version = event.driver.get_whatsapp_version()
                if self.app._whatsapp_version:
                    from ...constants import TESTED_WHATSAPP_VERSION
                    if self.app._whatsapp_version != TESTED_WHATSAPP_VERSION:
                        self._log(
                            f"WhatsApp version {self.app._whatsapp_version} "
                            f"(tested with {TESTED_WHATSAPP_VERSION}) — things may break"
                        )
                    else:
                        self._log(f"WhatsApp version {self.app._whatsapp_version}")
            except Exception:
                pass

        # Auto-start discovery (R1) then advance to Select tab
        ds.start_discovery()
        self.query_one(TabbedContent).active = "discover-select"

    def on_discover_select_pane_selection_changed(
        self, event: DiscoverSelectPane.SelectionChanged
    ) -> None:
        """Handle selection changes -- unlock/lock Export tab."""
        self._has_selection = event.count > 0

    def on_discover_select_pane_start_export(
        self, event: DiscoverSelectPane.StartExport
    ) -> None:
        """Handle start export -- enable Export tab, switch to it, start export."""
        self._has_selection = True
        tabbed = self.query_one(TabbedContent)
        tabbed.enable_tab("export")
        tabbed.active = "export"
        self._log(f"Starting export of {len(event.selected_chats)} chats")
        export_pane = self.query_one(ExportPane)
        export_pane.start_export(event.selected_chats)

    def on_export_pane_export_complete(
        self, event: ExportPane.ExportComplete
    ) -> None:
        """Handle export completion -- unlock Summary, optionally auto-advance."""
        self._export_complete = True
        tabbed = self.query_one(TabbedContent)
        # Auto-advance to Summary only if user is still on Export tab
        if tabbed.active == "export":
            tabbed.active = "summary"
        # Start processing if not cancelled and transcription/output is configured
        if not event.cancelled and (
            self.app.transcribe_audio or self.app.output_dir
        ):
            summary_pane = self.query_one(SummaryPane)
            summary_pane.start_processing(event.results)

    def on_export_pane_cancelled_return_to_selection(
        self, event: ExportPane.CancelledReturnToSelection
    ) -> None:
        """Handle cancel-and-return -- switch to D&S, reset export state."""
        tabbed = self.query_one(TabbedContent)
        tabbed.active = "discover-select"
        # Reset export pane state
        export_pane = self.query_one(ExportPane)
        export_pane.reset()

    def on_discover_select_pane_connection_lost(
        self, event: DiscoverSelectPane.ConnectionLost
    ) -> None:
        """Handle connection loss -- cascade disable downstream tabs."""
        self._connected = False
        self.query_one(TabbedContent).active = "connect"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Write to the screen-level ActivityLog."""
        try:
            log_widget = self.query_one(ActivityLog)
            log_widget.log(message)
        except Exception:
            pass
