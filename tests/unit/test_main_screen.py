"""
Unit tests for MainScreen with TabbedContent tab navigation.

Tests the 4-tab layout, progressive tab enabling via reactive properties,
and cascade disable logic.
"""

import pytest

from textual.widgets import TabbedContent

from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen
from whatsapp_chat_autoexport.tui.textual_widgets.activity_log import ActivityLog


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_screen_has_four_tab_panes(tui_app):
    """MainScreen should mount with exactly 4 tab panes."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        assert isinstance(screen, MainScreen)
        tabbed = screen.query_one(TabbedContent)
        pane_ids = [pane.id for pane in tabbed.query("TabPane")]
        assert pane_ids == ["connect", "discover-select", "export", "summary"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_only_connect_tab_enabled_on_mount(tui_app):
    """Only the Connect tab should be enabled on mount; other 3 disabled."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        connect_tab = tabbed.get_tab("connect")
        discover_tab = tabbed.get_tab("discover-select")
        export_tab = tabbed.get_tab("export")
        summary_tab = tabbed.get_tab("summary")

        assert not connect_tab.disabled
        assert discover_tab.disabled
        assert export_tab.disabled
        assert summary_tab.disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connected_enables_discover_select_tab(tui_app):
    """Setting _connected=True should enable discover-select tab."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        screen._connected = True
        await pilot.pause()

        assert not tabbed.get_tab("discover-select").disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_has_selection_enables_export_tab(tui_app):
    """Setting _has_selection=True should enable export tab."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()

        assert not tabbed.get_tab("export").disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_complete_enables_summary_tab(tui_app):
    """Setting _export_complete=True should enable summary tab."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        screen._connected = True
        screen._has_selection = True
        screen._export_complete = True
        await pilot.pause()

        assert not tabbed.get_tab("summary").disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_disconnect_cascades_disables(tui_app):
    """Setting _connected=False after True should disable discover-select, export, summary."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        # Enable everything
        screen._connected = True
        screen._has_selection = True
        screen._export_complete = True
        await pilot.pause()

        # Disconnect
        screen._connected = False
        await pilot.pause()

        assert tabbed.get_tab("discover-select").disabled
        assert tabbed.get_tab("export").disabled
        assert tabbed.get_tab("summary").disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deselect_disables_export_not_discover(tui_app):
    """Setting _has_selection=False should disable export and summary but not discover-select."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        tabbed = screen.query_one(TabbedContent)

        screen._connected = True
        screen._has_selection = True
        screen._export_complete = True
        await pilot.pause()

        screen._has_selection = False
        await pilot.pause()

        assert not tabbed.get_tab("discover-select").disabled
        assert tabbed.get_tab("export").disabled
        assert tabbed.get_tab("summary").disabled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activity_log_visible(tui_app):
    """ActivityLog should be visible regardless of active tab."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        logs = screen.query(ActivityLog)
        assert len(logs) == 1
        assert logs.first().display is True
