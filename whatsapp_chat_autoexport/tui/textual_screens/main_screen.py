"""
MainScreen with TabbedContent for the WhatsApp Exporter TUI.

Replaces the previous DiscoveryScreen + SelectionScreen two-screen model
with a single screen containing 4 tabs: Connect, Discover & Select, Export, Summary.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static, TabbedContent, TabPane
from textual.reactive import reactive

from ..textual_panes.connect_pane import ConnectPane
from ..textual_panes.discover_select_pane import DiscoverSelectPane
from ..textual_widgets.activity_log import ActivityLog


class MainScreen(Screen):
    """
    Single-screen layout with tabbed navigation for the export workflow.

    Tabs are progressively enabled as the user advances through the workflow:
    1. Connect - always enabled
    2. Discover & Select - enabled after device connection
    3. Export - enabled after chat selection
    4. Summary - enabled after export completes
    """

    BINDINGS = [
        Binding("1", "switch_tab('connect')", "Connect", show=False),
        Binding("2", "switch_tab('discover-select')", "Discover", show=False),
        Binding("3", "switch_tab('export')", "Export", show=False),
        Binding("4", "switch_tab('summary')", "Summary", show=False),
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
            with TabPane("2 Discover & Select", id="discover-select"):
                yield DiscoverSelectPane()
            with TabPane("3 Export", id="export"):
                yield Static("Content goes here")
            with TabPane("4 Summary", id="summary"):
                yield Static("Content goes here")
        yield ActivityLog()

    def on_mount(self) -> None:
        """Disable all tabs except Connect on mount."""
        tabbed = self.query_one(TabbedContent)
        tabbed.disable_tab("discover-select")
        tabbed.disable_tab("export")
        tabbed.disable_tab("summary")

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

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a tab if it is not disabled."""
        tabbed = self.query_one(TabbedContent)
        tab = tabbed.get_tab(tab_id)
        if not tab.disabled:
            tabbed.active = tab_id
