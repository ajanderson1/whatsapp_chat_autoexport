"""
Integration tests for MainScreen tab navigation and orchestration.

Tests the full workflow of tab transitions, auto-advance, and message handling
using the Textual pilot test harness.
"""

import tempfile
from pathlib import Path

import pytest

from textual.widgets import TabbedContent

from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp
from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen
from whatsapp_chat_autoexport.tui.textual_panes.connect_pane import ConnectPane
from whatsapp_chat_autoexport.tui.textual_panes.discover_select_pane import DiscoverSelectPane
from whatsapp_chat_autoexport.tui.textual_panes.export_pane import ExportPane
from whatsapp_chat_autoexport.tui.textual_panes.summary_pane import SummaryPane


def _make_app(**kwargs) -> WhatsAppExporterApp:
    """Create a WhatsAppExporterApp configured for testing."""
    defaults = {
        "dry_run": True,
        "output_dir": Path(tempfile.mkdtemp()),
    }
    defaults.update(kwargs)
    return WhatsAppExporterApp(**defaults)


def _get_main_screen(app: WhatsAppExporterApp) -> MainScreen:
    """Get the MainScreen from the app's screen stack."""
    screen = app.screen
    assert isinstance(screen, MainScreen), f"Expected MainScreen, got {type(screen)}"
    return screen


# ------------------------------------------------------------------
# Test: App launches with Connect tab active
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_starts_with_connect_tab():
    """App should launch with MainScreen and Connect tab active."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)
        assert tabbed.active == "connect"


# ------------------------------------------------------------------
# Test: Dry-run connect auto-advances to D&S tab
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_connect_auto_advances_to_discover_select():
    """After ConnectPane.Connected, MainScreen should auto-advance to D&S tab."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Simulate the Connected message from ConnectPane
        connect_pane = main.query_one(ConnectPane)
        connect_pane.post_message(ConnectPane.Connected(driver=None))
        await pilot.pause()

        assert tabbed.active == "discover-select"
        assert not tabbed.get_tab("discover-select").disabled


# ------------------------------------------------------------------
# Test: Connected message stores driver on app
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connected_stores_driver_on_app():
    """ConnectPane.Connected should store the driver on the app."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)

        # Use None driver (dry-run style) -- a non-None driver would trigger
        # DiscoverSelectPane auto-discovery which requires a real driver
        connect_pane = main.query_one(ConnectPane)
        connect_pane.post_message(ConnectPane.Connected(driver=None))
        await pilot.pause()

        # The handler stores event.driver on app._whatsapp_driver
        assert app._whatsapp_driver is None
        # And the D&S tab was enabled (driver stored + auto-advance happened)
        tabbed = main.query_one(TabbedContent)
        assert tabbed.active == "discover-select"


# ------------------------------------------------------------------
# Test: Tab hotkeys work for enabled tabs
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotkey_switches_to_enabled_tab():
    """Pressing '1' should switch to Connect tab when on another tab."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Enable and switch to D&S
        main._connected = True
        await pilot.pause()
        tabbed.active = "discover-select"
        await pilot.pause()

        # Press '1' to go back to Connect
        await pilot.press("1")
        await pilot.pause()
        assert tabbed.active == "connect"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotkey_2_switches_to_discover_select_when_enabled():
    """Pressing '2' should switch to D&S tab when enabled."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Enable D&S
        main._connected = True
        await pilot.pause()

        # Start on Connect
        tabbed.active = "connect"
        await pilot.pause()

        # Press '2'
        await pilot.press("2")
        await pilot.pause()
        assert tabbed.active == "discover-select"


# ------------------------------------------------------------------
# Test: Tab hotkeys are no-op for disabled tabs
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotkey_noop_for_disabled_tab():
    """Pressing '3' (Export) should be a no-op when Export tab is disabled."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        assert tabbed.active == "connect"

        # Press '3' -- Export is disabled
        await pilot.press("3")
        await pilot.pause()
        assert tabbed.active == "connect"  # Should not change


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hotkey_4_noop_when_summary_disabled():
    """Pressing '4' (Summary) should be a no-op when Summary tab is disabled."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Enable only Connect and D&S
        main._connected = True
        await pilot.pause()

        # Press '4' -- Summary is disabled
        await pilot.press("4")
        await pilot.pause()
        assert tabbed.active != "summary"


# ------------------------------------------------------------------
# Test: SelectionChanged unlocks/locks Export tab
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_changed_unlocks_export():
    """SelectionChanged with count>0 should enable the Export tab."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Connect first
        main._connected = True
        await pilot.pause()

        # Simulate selection change
        ds_pane = main.query_one(DiscoverSelectPane)
        ds_pane.post_message(DiscoverSelectPane.SelectionChanged(count=3))
        await pilot.pause()

        assert not tabbed.get_tab("export").disabled


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_changed_zero_locks_export():
    """SelectionChanged with count=0 should disable the Export tab."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Connect and select
        main._connected = True
        main._has_selection = True
        await pilot.pause()
        assert not tabbed.get_tab("export").disabled

        # Deselect
        ds_pane = main.query_one(DiscoverSelectPane)
        ds_pane.post_message(DiscoverSelectPane.SelectionChanged(count=0))
        await pilot.pause()

        assert tabbed.get_tab("export").disabled


# ------------------------------------------------------------------
# Test: ConnectionLost cascades disable and switches to Connect
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connection_lost_cascades_disable():
    """ConnectionLost should disable D&S, Export, Summary and switch to Connect."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Set up connected state
        main._connected = True
        main._has_selection = True
        await pilot.pause()
        tabbed.active = "discover-select"
        await pilot.pause()

        # Emit connection lost
        ds_pane = main.query_one(DiscoverSelectPane)
        ds_pane.post_message(DiscoverSelectPane.ConnectionLost())
        await pilot.pause()

        assert tabbed.active == "connect"
        assert tabbed.get_tab("discover-select").disabled
        assert tabbed.get_tab("export").disabled
        assert tabbed.get_tab("summary").disabled


# ------------------------------------------------------------------
# Test: CancelledReturnToSelection switches back to D&S
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancelled_return_to_selection():
    """CancelledReturnToSelection should switch to D&S tab."""
    app = _make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        main = _get_main_screen(app)
        tabbed = main.query_one(TabbedContent)

        # Set up export state
        main._connected = True
        main._has_selection = True
        await pilot.pause()
        tabbed.active = "export"
        await pilot.pause()

        # Emit cancel-and-return
        export_pane = main.query_one(ExportPane)
        export_pane.post_message(ExportPane.CancelledReturnToSelection())
        await pilot.pause()

        assert tabbed.active == "discover-select"
