"""
Integration tests for the Textual TUI application.

Uses Textual's pilot harness to test UI behavior with mocked backends.
All tests run without real Appium, ADB, or device connections.

Updated for the MainScreen tab-navigation model (Units 1-7 refactor):
- App starts with a single MainScreen containing TabbedContent
- Tabs: connect, discover-select, export, summary
- ConnectPane, DiscoverSelectPane, ExportPane, SummaryPane live inside tab panes
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pytest_asyncio

from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp, PipelineStage
from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen
from whatsapp_chat_autoexport.tui.textual_panes.connect_pane import ConnectPane
from whatsapp_chat_autoexport.tui.textual_panes.discover_select_pane import DiscoverSelectPane
from whatsapp_chat_autoexport.tui.textual_panes.export_pane import ExportPane
from whatsapp_chat_autoexport.tui.textual_panes.summary_pane import SummaryPane
from whatsapp_chat_autoexport.tui.textual_widgets.cancel_modal import CancelModal
from whatsapp_chat_autoexport.tui.textual_widgets.progress_pane import ProgressPane


# The `tui_app` fixture is defined in tests/conftest.py and available to all tests.


MOCK_CHATS = [
    "John Doe",
    "Family Group",
    "Work Chat",
    "Best Friend",
    "Mom",
]


# ---------------------------------------------------------------------------
# App Launch Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_launches_with_main_screen(tui_app):
    """App should show MainScreen on startup."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(tui_app.screen, MainScreen)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_starts_on_connect_tab(tui_app):
    """App should start with the Connect tab active."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent
        tabbed = tui_app.screen.query_one(TabbedContent)
        assert tabbed.active == "connect"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_has_header_and_footer(tui_app):
    """App should render Header and Footer widgets."""
    from textual.widgets import Header, Footer

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Header and Footer are composed at the App level
        headers = tui_app.query("Header")
        footers = tui_app.query("Footer")
        assert len(headers) >= 1
        assert len(footers) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_initial_pipeline_stage(tui_app):
    """App should start on the CONNECT pipeline stage."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert tui_app.current_stage == PipelineStage.CONNECT


# ---------------------------------------------------------------------------
# ConnectPane Tests (formerly DiscoveryScreen)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_pane_has_device_list(tui_app):
    """ConnectPane should contain a device ListView."""
    from textual.widgets import ListView

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        device_lists = tui_app.screen.query("#device-list")
        assert len(device_lists) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_pane_has_action_buttons(tui_app):
    """ConnectPane should have Refresh and Connect buttons."""
    from textual.widgets import Button

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        refresh_btn = tui_app.screen.query_one("#btn-refresh", Button)
        connect_btn = tui_app.screen.query_one("#btn-connect", Button)
        assert refresh_btn is not None
        assert connect_btn is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_pane_wireless_section(tui_app):
    """ConnectPane should have wireless ADB input fields."""
    from textual.widgets import Input, Button

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        ip_port = tui_app.screen.query_one("#wireless-ip-port", Input)
        pairing_code = tui_app.screen.query_one("#wireless-pairing-code", Input)
        wireless_btn = tui_app.screen.query_one("#btn-wireless-connect", Button)
        assert ip_port is not None
        assert pairing_code is not None
        assert wireless_btn is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_device_scan_shows_devices(tui_app):
    """When adb returns a device, it should appear in the list."""
    mock_adb_output = (
        "List of devices attached\n"
        "ABCDEF123456\tdevice\tmodel:Pixel_6\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = mock_adb_output
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        async with tui_app.run_test(size=(120, 40)) as pilot:
            # Wait for device scan worker to complete and UI to update
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

            from textual.widgets import ListView
            device_list = tui_app.screen.query_one("#device-list", ListView)
            # Should have at least one item
            assert len(device_list.children) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_device_scan_no_devices(tui_app):
    """When adb returns no devices, the status should reflect that."""
    mock_adb_output = "List of devices attached\n\n"

    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = mock_adb_output
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        async with tui_app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

            from textual.widgets import Static
            status = tui_app.screen.query_one("#device-status", Static)
            # Access the content set via update() (name-mangled __content)
            content = str(getattr(status, "_Static__content", ""))
            assert "no devices" in content.lower()


# ---------------------------------------------------------------------------
# Dry Run / Tab Transition
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_transitions_to_discover_select_tab(tui_app):
    """Dry-run connect should auto-advance to discover-select tab."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Trigger dry-run by calling the action directly on ConnectPane
        # (key bindings on Container may not fire if focus is on a child widget)
        connect_pane = tui_app.screen.query_one(ConnectPane)
        connect_pane.action_use_dry_run()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        # Should now be on the discover-select tab
        from textual.widgets import TabbedContent
        tabbed = tui_app.screen.query_one(TabbedContent)
        assert tabbed.active == "discover-select"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_select_tab_has_chat_list(tui_app):
    """DiscoverSelectPane should render the ChatListWidget."""
    from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import ChatListWidget

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Trigger dry-run to advance to discover-select tab
        connect_pane = tui_app.screen.query_one(ConnectPane)
        connect_pane.action_use_dry_run()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        chat_list = tui_app.screen.query_one("#chat-select-list", ChatListWidget)
        assert chat_list is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_select_tab_has_settings_panel(tui_app):
    """DiscoverSelectPane should render the SettingsPanel."""
    from whatsapp_chat_autoexport.tui.textual_widgets.settings_panel import SettingsPanel

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        connect_pane = tui_app.screen.query_one(ConnectPane)
        connect_pane.action_use_dry_run()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        settings = tui_app.screen.query_one("#settings-panel", SettingsPanel)
        assert settings is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_select_tab_has_start_export_button(tui_app):
    """DiscoverSelectPane should have a Start Export button."""
    from textual.widgets import Button

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        connect_pane = tui_app.screen.query_one(ConnectPane)
        connect_pane.action_use_dry_run()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        start_btn = tui_app.screen.query_one("#btn-start-export", Button)
        assert start_btn is not None
        assert "Start Export" in str(start_btn.label)


# ---------------------------------------------------------------------------
# Tab Enable/Disable Cascade
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tabs_disabled_on_startup(tui_app):
    """All tabs except Connect should be disabled on startup."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        from textual.widgets import TabbedContent
        tabbed = tui_app.screen.query_one(TabbedContent)
        # discover-select, export, summary should be disabled
        assert tabbed.get_tab("discover-select").disabled is True
        assert tabbed.get_tab("export").disabled is True
        assert tabbed.get_tab("summary").disabled is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_enables_discover_select_tab(tui_app):
    """After dry-run connect, discover-select tab should be enabled."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        connect_pane = tui_app.screen.query_one(ConnectPane)
        connect_pane.action_use_dry_run()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        from textual.widgets import TabbedContent
        tabbed = tui_app.screen.query_one(TabbedContent)
        assert tabbed.get_tab("discover-select").disabled is False


# ---------------------------------------------------------------------------
# CancelModal Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_modal_with_custom_message():
    """CancelModal should render with a custom message."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_cancel"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Push cancel modal with custom message
        modal = CancelModal(
            message="Pipeline failed: connection error",
            completed=3,
            total=10,
        )
        await app.push_screen(modal)
        await pilot.pause()

        # Modal should be on the screen stack
        assert isinstance(app.screen, CancelModal)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_modal_with_default_message():
    """CancelModal should render with default progress message when no custom message."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_cancel2"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        modal = CancelModal(
            current_chat="Family Group",
            completed=2,
            total=5,
        )
        await app.push_screen(modal)
        await pilot.pause()

        assert isinstance(app.screen, CancelModal)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_modal_buttons():
    """CancelModal should have Return, Exit, and Continue buttons."""
    from textual.widgets import Button

    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_cancel3"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        modal = CancelModal(completed=1, total=5)
        await app.push_screen(modal)
        await pilot.pause()

        return_btn = app.screen.query_one("#btn-return", Button)
        exit_btn = app.screen.query_one("#btn-exit", Button)
        continue_btn = app.screen.query_one("#btn-continue", Button)
        assert return_btn is not None
        assert exit_btn is not None
        assert continue_btn is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_modal_dismiss_on_escape():
    """CancelModal should dismiss when Escape is pressed."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_cancel4"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        modal = CancelModal(completed=0, total=5)
        await app.push_screen(modal)
        await pilot.pause()
        assert isinstance(app.screen, CancelModal)

        # Press escape to dismiss
        await pilot.press("escape")
        await pilot.pause()

        # Should no longer be on the CancelModal
        assert not isinstance(app.screen, CancelModal)


# ---------------------------------------------------------------------------
# ProgressPane Widget Tests (mounted within ExportPane)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_progress_pane_update_pipeline_phase():
    """ProgressPane.update_pipeline_phase() should set correct phase state."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_progress"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Get the ExportPane's ProgressPane directly (it's mounted even if tab is disabled)
        pane = app.screen.query_one("#export-progress-pane", ProgressPane)

        # Switch to processing mode and update phase
        pane.mode = "processing"
        pane.update_pipeline_phase("download")
        await pilot.pause()

        assert pane.current_phase == "Download"
        assert pane.phase_number == 1

        pane.update_pipeline_phase("transcribe")
        await pilot.pause()

        assert pane.current_phase == "Transcribe"
        assert pane.phase_number == 3

        pane.update_pipeline_phase("build_output")
        await pilot.pause()

        assert pane.current_phase == "Build"
        assert pane.phase_number == 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_progress_pane_update_pipeline_item():
    """ProgressPane.update_pipeline_item() should update item-level progress."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_progress2"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        pane = app.screen.query_one("#export-progress-pane", ProgressPane)

        pane.mode = "processing"
        pane.update_pipeline_phase("transcribe")
        pane.update_pipeline_item("PTT-001.opus", 3, 10)
        await pilot.pause()

        assert pane.pipeline_item == "PTT-001.opus"
        assert pane.pipeline_item_current == 3
        assert pane.pipeline_item_total == 10


@pytest.mark.integration
@pytest.mark.asyncio
async def test_progress_pane_export_mode():
    """ProgressPane export mode should track chat progress."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_progress3"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        pane = app.screen.query_one("#export-progress-pane", ProgressPane)

        pane.start_export(5)
        await pilot.pause()

        assert pane.mode == "export"
        assert pane.total_chats == 5
        assert pane.completed_chats == 0

        pane.update_export_progress(chat="John Doe", step="Open menu", step_num=2, completed=0)
        await pilot.pause()

        assert pane.current_chat == "John Doe"
        assert pane.current_step == "Open menu"
        assert pane.step_number == 2

        pane.complete_chat("John Doe")
        await pilot.pause()

        assert pane.completed_chats == 1
        assert pane.current_chat == ""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_progress_pane_complete_mode():
    """ProgressPane.set_complete() should switch to complete mode with summary."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_progress4"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        pane = app.screen.query_one("#export-progress-pane", ProgressPane)

        pane.set_complete({
            "exported": 5,
            "failed": 1,
            "transcribed": 12,
            "output_path": "/tmp/test_output",
        })
        await pilot.pause()

        assert pane.mode == "complete"


# ---------------------------------------------------------------------------
# App State and Event Bus Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_activity_log(tui_app):
    """App should track activity messages."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        tui_app._log_activity("Test message 1")
        tui_app._log_activity("Test message 2")

        assert len(tui_app.activity_log) >= 2
        assert "Test message 1" in tui_app.activity_log
        assert "Test message 2" in tui_app.activity_log


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_quit_action(tui_app):
    """Pressing 'q' should trigger quit."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Press q to quit - the app should exit
        await pilot.press("q")
        await pilot.pause()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_help_screen_opens():
    """Pressing 'h' should open the help screen."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_help"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Press 'h' to open help
        await pilot.press("h")
        await pilot.pause()

        # Screen stack should have more than one screen
        assert len(app.screen_stack) > 1


# ---------------------------------------------------------------------------
# ExportPane Tests (replaced SelectionScreen mode tests)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_pane_has_pause_and_cancel_buttons():
    """ExportPane should have Pause and Cancel buttons."""
    from textual.widgets import Button

    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_export_pane"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        pause_btn = app.screen.query_one("#btn-pause", Button)
        cancel_btn = app.screen.query_one("#btn-cancel", Button)
        assert pause_btn is not None
        assert cancel_btn is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_pane_has_chat_status_list():
    """ExportPane should have a ChatListWidget in status mode."""
    from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import ChatListWidget

    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_export_pane2"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        chat_list = app.screen.query_one("#chat-status-list", ChatListWidget)
        assert chat_list is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_pane_has_progress_pane():
    """ExportPane should have a ProgressPane."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_export_pane3"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        pane = app.screen.query_one("#export-progress-pane", ProgressPane)
        assert pane is not None
