"""
Unit tests for ConnectPane -- the device connection pane extracted from DiscoveryScreen.

Tests cover:
- Widget composition (device list, wireless inputs, buttons)
- ConnectPane.Connected message class
- Pane-level state initialisation
"""

import pytest

from whatsapp_chat_autoexport.tui.textual_panes.connect_pane import ConnectPane
from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen

from textual.widgets import Button, Input, ListView, Static, TabbedContent


# =============================================================================
# ConnectPane Initialisation
# =============================================================================


class TestConnectPaneInit:
    """Tests for ConnectPane initialisation and state."""

    def test_init_default_state(self):
        """ConnectPane should initialise with correct default state."""
        pane = ConnectPane()
        assert pane._devices == []
        assert pane._selected_device is None
        assert pane._connecting is False
        assert pane._wireless_connecting is False
        assert pane._appium_started is False

    def test_is_container_subclass(self):
        """ConnectPane should be a Container, not a Screen."""
        from textual.containers import Container

        pane = ConnectPane()
        assert isinstance(pane, Container)

    def test_has_connected_message_class(self):
        """ConnectPane.Connected message class should exist."""
        assert hasattr(ConnectPane, "Connected")
        msg = ConnectPane.Connected(driver="fake_driver")
        assert msg.driver == "fake_driver"

    def test_connected_message_carries_driver(self):
        """ConnectPane.Connected should carry the driver attribute."""
        sentinel = object()
        msg = ConnectPane.Connected(driver=sentinel)
        assert msg.driver is sentinel

    def test_connected_message_is_message_subclass(self):
        """ConnectPane.Connected should be a Textual Message subclass."""
        from textual.message import Message

        msg = ConnectPane.Connected(driver=None)
        assert isinstance(msg, Message)

    def test_has_wireless_methods(self):
        """ConnectPane should have the wireless ADB methods."""
        pane = ConnectPane()
        assert callable(getattr(pane, "_start_wireless_connect", None))
        assert callable(getattr(pane, "_wireless_pair", None))
        assert callable(getattr(pane, "_wireless_connect", None))
        assert callable(getattr(pane, "_handle_wireless_pair_result", None))
        assert callable(getattr(pane, "_handle_wireless_connect_result", None))


# =============================================================================
# Widget Composition (mounted inside MainScreen via tui_app)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_device_list(tui_app):
    """ConnectPane should contain a ListView with id 'device-list'."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        assert isinstance(screen, MainScreen)
        pane = screen.query_one(ConnectPane)
        device_list = pane.query_one("#device-list", ListView)
        assert device_list is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_refresh_button(tui_app):
    """ConnectPane should contain a Refresh button."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = tui_app.screen.query_one(ConnectPane)
        btn = pane.query_one("#btn-refresh", Button)
        assert btn is not None
        assert btn.label.plain == "Refresh"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_connect_button(tui_app):
    """ConnectPane should contain a Connect button (disabled initially)."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = tui_app.screen.query_one(ConnectPane)
        btn = pane.query_one("#btn-connect", Button)
        assert btn is not None
        assert btn.disabled is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_wireless_inputs(tui_app):
    """ConnectPane should contain wireless IP:Port and pairing code inputs."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = tui_app.screen.query_one(ConnectPane)
        ip_input = pane.query_one("#wireless-ip-port", Input)
        code_input = pane.query_one("#wireless-pairing-code", Input)
        assert ip_input is not None
        assert code_input is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_wireless_connect_button(tui_app):
    """ConnectPane should contain a 'Connect Wirelessly' button."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = tui_app.screen.query_one(ConnectPane)
        btn = pane.query_one("#btn-wireless-connect", Button)
        assert btn is not None
        assert "Wirelessly" in btn.label.plain


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_mounts_device_status(tui_app):
    """ConnectPane should contain a device-status Static widget."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        pane = tui_app.screen.query_one(ConnectPane)
        status = pane.query_one("#device-status", Static)
        assert status is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connect_pane_inside_connect_tab(tui_app):
    """ConnectPane should be inside the 'connect' TabPane."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        tabbed = tui_app.screen.query_one(TabbedContent)
        # The active tab should be 'connect' on mount
        assert tabbed.active == "connect"
        # And a ConnectPane should be queryable from the screen
        panes = tui_app.screen.query(ConnectPane)
        assert len(panes) == 1
