"""
Unit tests for ExportPane -- the export progress pane.

Tests cover:
- Widget composition (ChatListWidget in status mode, ProgressPane, buttons)
- Message classes (ExportComplete, CancelledReturnToSelection)
- Pane-level state initialisation
- Public API (start_export, reset)
"""

import pytest

from whatsapp_chat_autoexport.tui.textual_panes.export_pane import ExportPane
from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen
from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import ChatListWidget
from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import ProgressPane

from textual.containers import Container
from textual.message import Message
from textual.widgets import Button, Static, TabbedContent


# =============================================================================
# ExportPane Initialisation
# =============================================================================


class TestExportPaneInit:
    """Tests for ExportPane initialisation and state."""

    def test_is_container_subclass(self):
        """ExportPane should be a Container, not a Screen."""
        pane = ExportPane()
        assert isinstance(pane, Container)

    def test_export_results_defaults_empty(self):
        """_export_results should default to empty lists."""
        pane = ExportPane()
        assert pane._export_results == {
            "completed": [],
            "failed": [],
            "skipped": [],
        }

    def test_consecutive_failures_defaults_zero(self):
        """_consecutive_failures should default to 0."""
        pane = ExportPane()
        assert pane._consecutive_failures == 0

    def test_cancel_after_current_defaults_false(self):
        """_cancel_after_current should default to False."""
        pane = ExportPane()
        assert pane._cancel_after_current is False

    def test_paused_defaults_false(self):
        """_paused should default to False."""
        pane = ExportPane()
        assert pane._paused is False

    def test_current_chat_defaults_none(self):
        """_current_chat should default to None."""
        pane = ExportPane()
        assert pane._current_chat is None

    def test_export_worker_defaults_none(self):
        """_export_worker should default to None."""
        pane = ExportPane()
        assert pane._export_worker is None


# =============================================================================
# Message Classes
# =============================================================================


class TestExportPaneMessages:
    """Tests for ExportPane message classes."""

    def test_export_complete_exists(self):
        """ExportPane.ExportComplete should exist."""
        assert hasattr(ExportPane, "ExportComplete")

    def test_export_complete_carries_results(self):
        """ExportComplete should carry a results dict."""
        results = {"completed": ["A"], "failed": [], "skipped": []}
        msg = ExportPane.ExportComplete(results=results)
        assert msg.results == results

    def test_export_complete_carries_cancelled(self):
        """ExportComplete should carry a cancelled flag."""
        results = {"completed": [], "failed": [], "skipped": []}
        msg = ExportPane.ExportComplete(results=results, cancelled=True)
        assert msg.cancelled is True

    def test_export_complete_cancelled_defaults_false(self):
        """ExportComplete cancelled should default to False."""
        results = {"completed": [], "failed": [], "skipped": []}
        msg = ExportPane.ExportComplete(results=results)
        assert msg.cancelled is False

    def test_export_complete_is_message(self):
        """ExportComplete should be a Textual Message subclass."""
        results = {"completed": [], "failed": [], "skipped": []}
        msg = ExportPane.ExportComplete(results=results)
        assert isinstance(msg, Message)

    def test_cancelled_return_to_selection_exists(self):
        """ExportPane.CancelledReturnToSelection should exist."""
        assert hasattr(ExportPane, "CancelledReturnToSelection")

    def test_cancelled_return_to_selection_is_message(self):
        """CancelledReturnToSelection should be a Textual Message subclass."""
        msg = ExportPane.CancelledReturnToSelection()
        assert isinstance(msg, Message)


# =============================================================================
# Public API existence
# =============================================================================


class TestExportPaneAPI:
    """Tests for ExportPane public methods."""

    def test_start_export_method_exists(self):
        """ExportPane should have a start_export method."""
        pane = ExportPane()
        assert callable(getattr(pane, "start_export", None))

    def test_reset_method_exists(self):
        """ExportPane should have a reset method."""
        pane = ExportPane()
        assert callable(getattr(pane, "reset", None))

    def test_max_consecutive_failures_constant(self):
        """ExportPane should define MAX_CONSECUTIVE_FAILURES."""
        assert ExportPane.MAX_CONSECUTIVE_FAILURES == 3


# =============================================================================
# Widget Composition (mounted inside MainScreen via tui_app)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_mounts_chat_status_list(tui_app):
    """ExportPane should contain a ChatListWidget with id 'chat-status-list'."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen
        assert isinstance(screen, MainScreen)

        # Enable and switch to export tab
        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        chat_list = pane.query_one("#chat-status-list", ChatListWidget)
        assert chat_list is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_chat_list_in_status_mode(tui_app):
    """ChatListWidget in ExportPane should be in status display mode."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        chat_list = pane.query_one("#chat-status-list", ChatListWidget)
        assert chat_list.display_mode == "status"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_mounts_progress_pane(tui_app):
    """ExportPane should contain a ProgressPane."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        progress = pane.query_one("#export-progress-pane", ProgressPane)
        assert progress is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_mounts_pause_button(tui_app):
    """ExportPane should contain a Pause button."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        btn = pane.query_one("#btn-pause", Button)
        assert btn is not None
        assert "Pause" in btn.label.plain


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_mounts_cancel_button(tui_app):
    """ExportPane should contain a Cancel button."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        btn = pane.query_one("#btn-cancel", Button)
        assert btn is not None
        assert "Cancel" in btn.label.plain


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_mounts_status_label(tui_app):
    """ExportPane should contain an export-status Static widget."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        pane = screen.query_one(ExportPane)
        status = pane.query_one("#export-status", Static)
        assert status is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_pane_inside_export_tab(tui_app):
    """ExportPane should be inside the 'export' TabPane."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        screen._connected = True
        screen._has_selection = True
        await pilot.pause()
        tabbed = screen.query_one(TabbedContent)
        tabbed.active = "export"
        await pilot.pause()

        panes = screen.query(ExportPane)
        assert len(panes) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_duplicate_listview_ids_with_both_panes(tui_app):
    """ChatListWidgets in DiscoverSelect and Export should have distinct ListView IDs."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = tui_app.screen

        # Enable all tabs
        screen._connected = True
        screen._has_selection = True
        await pilot.pause()

        # Both panes are mounted (ContentSwitcher keeps both in DOM)
        from textual.widgets import ListView
        listviews = screen.query(ListView)
        ids = [lv.id for lv in listviews if lv.id and "listview" in lv.id]
        # Should have at least two distinct IDs (one from each ChatListWidget)
        assert len(ids) == len(set(ids)), f"Duplicate ListView IDs found: {ids}"
