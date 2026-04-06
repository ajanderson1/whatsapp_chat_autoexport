"""
Unit tests for DiscoverSelectPane -- the combined discovery and selection pane.

Tests cover:
- Widget composition (discovery inventory, chat list, settings panel, buttons)
- Message classes (SelectionChanged, StartExport, ConnectionLost)
- Pane-level state initialisation
"""

import pytest

from whatsapp_chat_autoexport.tui.textual_panes.discover_select_pane import (
    DiscoverSelectPane,
)
from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen
from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import ChatListWidget
from whatsapp_chat_autoexport.tui.textual_widgets.settings_panel import SettingsPanel

from textual.containers import Container
from textual.message import Message
from textual.widgets import Button, ListView, Static, TabbedContent


# =============================================================================
# DiscoverSelectPane Initialisation
# =============================================================================


class TestDiscoverSelectPaneInit:
    """Tests for DiscoverSelectPane initialisation and state."""

    def test_is_container_subclass(self):
        """DiscoverSelectPane should be a Container, not a Screen."""
        pane = DiscoverSelectPane()
        assert isinstance(pane, Container)

    def test_discovery_worker_defaults_none(self):
        """_discovery_worker should default to None."""
        pane = DiscoverSelectPane()
        assert pane._discovery_worker is None

    def test_start_discovery_is_public(self):
        """start_discovery() should be a public method."""
        pane = DiscoverSelectPane()
        assert callable(getattr(pane, "start_discovery", None))

    def test_discovery_generation_defaults_zero(self):
        """_discovery_generation counter should default to 0."""
        pane = DiscoverSelectPane()
        assert pane._discovery_generation == 0

    def test_discovered_chats_defaults_empty(self):
        """_discovered_chats should default to empty list."""
        pane = DiscoverSelectPane()
        assert pane._discovered_chats == []

    def test_scanning_chats_defaults_false(self):
        """_scanning_chats should default to False."""
        pane = DiscoverSelectPane()
        assert pane._scanning_chats is False

    def test_no_on_show_method(self):
        """DiscoverSelectPane should not have an on_show auto-trigger."""
        pane = DiscoverSelectPane()
        # on_show was removed — discovery is now triggered by MainScreen
        assert not hasattr(pane, "_first_show")

    def test_stop_discovery_is_public(self):
        """stop_discovery() should be a public method."""
        pane = DiscoverSelectPane()
        assert callable(getattr(pane, "stop_discovery", None))

    def test_stop_discovery_noop_when_no_worker(self):
        """stop_discovery() should be safe to call when no worker is running."""
        pane = DiscoverSelectPane()
        assert pane._discovery_worker is None
        # Should not raise
        pane.stop_discovery()
        assert pane._scanning_chats is False

    def test_stop_discovery_increments_generation(self):
        """stop_discovery() should increment _discovery_generation."""
        pane = DiscoverSelectPane()
        gen_before = pane._discovery_generation
        pane.stop_discovery()
        assert pane._discovery_generation == gen_before + 1


# =============================================================================
# Message Classes
# =============================================================================


class TestDiscoverSelectPaneMessages:
    """Tests for DiscoverSelectPane message classes."""

    def test_selection_changed_exists(self):
        """DiscoverSelectPane.SelectionChanged should exist."""
        assert hasattr(DiscoverSelectPane, "SelectionChanged")

    def test_selection_changed_carries_count(self):
        """SelectionChanged should carry a count attribute."""
        msg = DiscoverSelectPane.SelectionChanged(count=5)
        assert msg.count == 5

    def test_selection_changed_is_message(self):
        """SelectionChanged should be a Textual Message subclass."""
        msg = DiscoverSelectPane.SelectionChanged(count=0)
        assert isinstance(msg, Message)

    def test_start_export_exists(self):
        """DiscoverSelectPane.StartExport should exist."""
        assert hasattr(DiscoverSelectPane, "StartExport")

    def test_start_export_carries_selected_chats(self):
        """StartExport should carry a selected_chats list."""
        chats = ["Alice", "Bob"]
        msg = DiscoverSelectPane.StartExport(selected_chats=chats)
        assert msg.selected_chats == chats

    def test_start_export_is_message(self):
        """StartExport should be a Textual Message subclass."""
        msg = DiscoverSelectPane.StartExport(selected_chats=[])
        assert isinstance(msg, Message)

    def test_connection_lost_exists(self):
        """DiscoverSelectPane.ConnectionLost should exist."""
        assert hasattr(DiscoverSelectPane, "ConnectionLost")

    def test_connection_lost_is_message(self):
        """ConnectionLost should be a Textual Message subclass."""
        msg = DiscoverSelectPane.ConnectionLost()
        assert isinstance(msg, Message)


# =============================================================================
# Widget Composition (mounted inside MainScreen via tui_app)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_discovery_inventory(tui_app):
    """DiscoverSelectPane should contain a ListView with id 'discovery-inventory'."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        assert isinstance(screen, MainScreen)

        # Enable and switch to discover-select tab
        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        inventory = pane.query_one("#discovery-inventory", ListView)
        assert inventory is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_chat_list(tui_app):
    """DiscoverSelectPane should contain a ChatListWidget with id 'chat-select-list'."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        chat_list = pane.query_one("#chat-select-list", ChatListWidget)
        assert chat_list is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_settings_panel(tui_app):
    """DiscoverSelectPane should contain a SettingsPanel with id 'settings-panel'."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        settings = pane.query_one("#settings-panel", SettingsPanel)
        assert settings is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_start_export_button(tui_app):
    """DiscoverSelectPane should contain a 'Start Export' button (disabled initially)."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        btn = pane.query_one("#btn-start-export", Button)
        assert btn is not None
        assert "Start Export" in btn.label.plain
        assert btn.disabled is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_refresh_button(tui_app):
    """DiscoverSelectPane should contain a 'Refresh Chats' button."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        btn = pane.query_one("#btn-refresh-chats", Button)
        assert btn is not None
        assert "Refresh" in btn.label.plain


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_mounts_selection_count(tui_app):
    """DiscoverSelectPane should contain a selection-count Static widget."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        pane = screen.query_one(DiscoverSelectPane)
        count_widget = pane.query_one("#selection-count", Static)
        assert count_widget is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discover_select_pane_inside_discover_select_tab(tui_app):
    """DiscoverSelectPane should be inside the 'discover-select' TabPane."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "discover-select"
        await pilot.pause()

        panes = screen.query(DiscoverSelectPane)
        assert len(panes) == 1
