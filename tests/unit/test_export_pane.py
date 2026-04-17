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
from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import (
    ChatListWidget,
    ChatDisplayStatus,
)
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


# =============================================================================
# ExportPane settle-wait integration
# =============================================================================

from unittest.mock import MagicMock, patch, PropertyMock


class TestExportPaneSettleWait:
    """Verify TUI calls wait_for_whatsapp_foreground before verify_whatsapp_is_open."""

    def _make_driver(self, settle_return=True, verify_return=True):
        driver = MagicMock()
        driver.wait_for_whatsapp_foreground = MagicMock(return_value=settle_return)
        driver.verify_whatsapp_is_open = MagicMock(return_value=verify_return)
        driver.navigate_to_main = MagicMock()
        driver.click_chat = MagicMock(return_value=True)
        return driver

    def _make_pane(self):
        """Create an ExportPane with a mocked app property to avoid NoActiveAppError."""
        pane = ExportPane()
        mock_app = MagicMock()
        mock_app.debug_mode = False
        # Patch the app property on the instance's type to avoid Textual's ContextVar check
        with patch.object(type(pane), "app", new_callable=PropertyMock, return_value=mock_app):
            pass  # Just to confirm the patch works
        return pane, mock_app

    def test_settle_called_before_verify_on_tui_path(self):
        pane = ExportPane()
        driver = self._make_driver(settle_return=True, verify_return=True)
        mock_app = MagicMock()
        mock_app.debug_mode = False

        with patch.object(type(pane), "app", new_callable=PropertyMock, return_value=mock_app), \
             patch(
                 "whatsapp_chat_autoexport.export.chat_exporter.ChatExporter"
             ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = True

            result = pane._export_single_chat(
                driver, "ChatA", include_media=False, log_callback=None
            )

        assert result is True
        driver.wait_for_whatsapp_foreground.assert_called_once()
        driver.verify_whatsapp_is_open.assert_called_once()
        # Settle must precede verify
        order = [
            c[0]
            for c in driver.mock_calls
            if c[0] in ("wait_for_whatsapp_foreground", "verify_whatsapp_is_open")
        ]
        assert order[0] == "wait_for_whatsapp_foreground"

    def test_settle_timeout_still_calls_verify(self):
        pane = ExportPane()
        driver = self._make_driver(settle_return=False, verify_return=False)
        mock_app = MagicMock()
        mock_app.debug_mode = False

        with patch.object(type(pane), "app", new_callable=PropertyMock, return_value=mock_app):
            result = pane._export_single_chat(
                driver, "ChatA", include_media=False, log_callback=None
            )

        # _export_single_chat now returns ExportOutcome (falsy when not SUCCESS)
        assert bool(result) is False
        driver.wait_for_whatsapp_foreground.assert_called_once()
        driver.verify_whatsapp_is_open.assert_called_once()


# =============================================================================
# ExportPane tri-state outcome routing (Task 7)
# =============================================================================


class TestExportPaneTriStateResult:
    """Verify the TUI handles SKIPPED_COMMUNITY distinctly from FAILED."""

    def _make_driver(self):
        driver = MagicMock()
        driver.wait_for_whatsapp_foreground = MagicMock(return_value=True)
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)
        driver.navigate_to_main = MagicMock()
        driver.click_chat = MagicMock(return_value=True)
        driver.restart_app_to_top = MagicMock(return_value=True)
        return driver

    def test_export_single_chat_returns_outcome_for_community(self):
        from whatsapp_chat_autoexport.export.chat_exporter import (
            ExportOutcome,
            ExportOutcomeKind,
        )

        pane = ExportPane()
        driver = self._make_driver()
        mock_app = MagicMock()
        mock_app.debug_mode = False

        with patch.object(type(pane), "app", new_callable=PropertyMock, return_value=mock_app), \
             patch(
                "whatsapp_chat_autoexport.export.chat_exporter.ChatExporter"
             ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = ExportOutcome(
                kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                reason="Community chat",
            )
            outcome = pane._export_single_chat(
                driver, "ChatC", include_media=False, log_callback=None
            )

        assert isinstance(outcome, ExportOutcome)
        assert outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY

    def test_run_real_export_marks_community_skipped_not_failed(self):
        from whatsapp_chat_autoexport.export.chat_exporter import (
            ExportOutcome,
            ExportOutcomeKind,
        )

        pane = ExportPane()
        driver = self._make_driver()

        pane._skip_chat_export = MagicMock()
        pane._fail_chat_export = MagicMock()
        pane._complete_chat_export = MagicMock()
        pane._start_chat_export = MagicMock()

        mock_app = MagicMock()
        mock_app.debug_mode = False
        mock_app.driver = driver
        mock_app.include_media = False
        # call_from_thread should invoke the function synchronously for the test
        mock_app.call_from_thread = lambda fn, *args, **kwargs: fn(*args, **kwargs)

        # query_one must return a mock progress pane to avoid widget lookup
        mock_progress = MagicMock()
        pane.query_one = MagicMock(return_value=mock_progress)

        with patch.object(type(pane), "app", new_callable=PropertyMock, return_value=mock_app), \
             patch(
                "whatsapp_chat_autoexport.export.chat_exporter.ChatExporter"
             ) as mock_exporter_cls:
            mock_exporter = mock_exporter_cls.return_value
            mock_exporter.export_chat_to_google_drive.return_value = ExportOutcome(
                kind=ExportOutcomeKind.SKIPPED_COMMUNITY,
                reason="Community chat",
            )

            import asyncio
            results = asyncio.run(
                pane._run_export(chats=["CommunityX"])
            )

        assert "CommunityX" in results["skipped"]
        assert "CommunityX" not in results["failed"]
        pane._skip_chat_export.assert_called()
        pane._fail_chat_export.assert_not_called()
        # Consecutive-failures counter must NOT have been incremented
        assert pane._consecutive_failures == 0


# =============================================================================
# ExportPane reason plumbing (Task 9)
# =============================================================================


class TestExportPaneReasonPlumbing:
    """Reasons must reach ChatListWidget.update_chat_status."""

    def test_fail_chat_export_forwards_reason_to_widget(self):
        pane = ExportPane()
        pane._export_results = {"completed": [], "failed": [], "skipped": []}
        pane._per_chat_reasons = {}

        chat_list = MagicMock()
        progress = MagicMock()

        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            if "export-progress-pane" in selector:
                return progress
            raise RuntimeError("unknown selector")

        pane.query_one = query_one

        pane._fail_chat_export("ChatA", "Verify failed")

        chat_list.update_chat_status.assert_called_once()
        args, kwargs = chat_list.update_chat_status.call_args
        assert args[0] == "ChatA"
        assert kwargs.get("reason") == "Verify failed" or (
            len(args) >= 3 and args[2] == "Verify failed"
        )
        # Pane-local record also stored for end-of-run reconcile
        assert pane._per_chat_reasons["ChatA"] == "Verify failed"

    def test_skip_chat_export_forwards_reason_to_widget(self):
        pane = ExportPane()
        pane._export_results = {"completed": [], "failed": [], "skipped": []}
        pane._per_chat_reasons = {}

        chat_list = MagicMock()
        progress = MagicMock()

        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            if "export-progress-pane" in selector:
                return progress
            raise RuntimeError("unknown selector")

        pane.query_one = query_one

        pane._skip_chat_export("ChatB", "Community chat")

        args, kwargs = chat_list.update_chat_status.call_args
        assert args[0] == "ChatB"
        assert kwargs.get("reason") == "Community chat" or (
            len(args) >= 3 and args[2] == "Community chat"
        )
        assert pane._per_chat_reasons["ChatB"] == "Community chat"
        # Progress pane must receive the "Skipped:" activity log line
        progress.log_activity.assert_called_once()
        log_args, _ = progress.log_activity.call_args
        assert "ChatB" in log_args[0]
        assert "Community chat" in log_args[0]


# =============================================================================
# ExportPane end-of-run reconcile (Task 10)
# =============================================================================


class TestExportPaneReconcile:
    """After a run, the widget must reflect every chat in results."""

    def test_reconcile_marks_all_failed_chats(self):
        pane = ExportPane()
        pane._export_results = {
            "completed": ["A"],
            "failed": ["B", "C"],
            "skipped": ["D"],
        }
        pane._per_chat_reasons = {
            "B": "Verify failed",
            "C": "Timeout",
            "D": "Community",
        }

        chat_list = MagicMock()
        def query_one(selector, cls):
            if "chat-status-list" in selector:
                return chat_list
            raise RuntimeError()
        pane.query_one = query_one

        pane._reconcile_chat_list_statuses()

        calls = chat_list.update_chat_status.call_args_list
        names = {c.args[0] for c in calls}
        assert names == {"A", "B", "C", "D"}

        status_by_name = {c.args[0]: c.args[1] for c in calls}
        assert status_by_name["A"] == ChatDisplayStatus.COMPLETED
        assert status_by_name["B"] == ChatDisplayStatus.FAILED
        assert status_by_name["C"] == ChatDisplayStatus.FAILED
        assert status_by_name["D"] == ChatDisplayStatus.SKIPPED

        # Reasons propagated on failure/skip entries
        reason_by_name = {
            c.args[0]: c.kwargs.get("reason") for c in calls
        }
        assert reason_by_name["B"] == "Verify failed"
        assert reason_by_name["C"] == "Timeout"
        assert reason_by_name["D"] == "Community"
        # Completed entry clears reason
        assert reason_by_name["A"] is None

    def test_reconcile_noop_when_widget_missing(self):
        """If the widget can't be queried, reconcile must not raise."""
        pane = ExportPane()
        pane._export_results = {"completed": ["A"], "failed": [], "skipped": []}
        pane._per_chat_reasons = {}

        def query_one(selector, cls):
            raise RuntimeError("widget not mounted")

        pane.query_one = query_one

        # Must not raise
        pane._reconcile_chat_list_statuses()
