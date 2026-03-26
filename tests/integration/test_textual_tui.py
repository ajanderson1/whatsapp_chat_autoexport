"""
Integration tests for the Textual TUI application.

Uses Textual's pilot harness to test UI behavior with mocked backends.
All tests run without real Appium, ADB, or device connections.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pytest_asyncio

from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp, PipelineStage
from whatsapp_chat_autoexport.tui.textual_screens.discovery_screen import DiscoveryScreen
from whatsapp_chat_autoexport.tui.textual_screens.selection_screen import SelectionScreen
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
async def test_app_launches_with_discovery_screen(tui_app):
    """App should show DiscoveryScreen on startup."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(tui_app.screen, DiscoveryScreen)


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
# DiscoveryScreen Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_screen_has_device_list(tui_app):
    """DiscoveryScreen should contain a device ListView."""
    from textual.widgets import ListView

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        device_lists = tui_app.screen.query("#device-list")
        assert len(device_lists) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_screen_has_action_buttons(tui_app):
    """DiscoveryScreen should have Refresh and Connect buttons."""
    from textual.widgets import Button

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        refresh_btn = tui_app.screen.query_one("#btn-refresh", Button)
        connect_btn = tui_app.screen.query_one("#btn-connect", Button)
        assert refresh_btn is not None
        assert connect_btn is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discovery_screen_wireless_section(tui_app):
    """DiscoveryScreen should have wireless ADB input fields."""
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
# Dry Run / Transition to Selection
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_transitions_to_selection(tui_app):
    """Pressing 'd' in DiscoveryScreen should enter dry-run and transition to SelectionScreen."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # Press 'd' to use dry-run mode
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        # Should now be on SelectionScreen
        assert isinstance(tui_app.screen, SelectionScreen)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dry_run_populates_chats(tui_app):
    """Dry-run mode should populate discovered_chats with mock data."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        # Should have mock chats populated
        assert len(tui_app.discovered_chats) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_has_chat_list(tui_app):
    """SelectionScreen should render the ChatListWidget."""
    from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import ChatListWidget

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        chat_list = tui_app.screen.query_one("#chat-list", ChatListWidget)
        assert chat_list is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_has_settings_panel(tui_app):
    """SelectionScreen should render the SettingsPanel."""
    from whatsapp_chat_autoexport.tui.textual_widgets.settings_panel import SettingsPanel

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        settings = tui_app.screen.query_one("#settings-panel", SettingsPanel)
        assert settings is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_has_progress_pane_hidden(tui_app):
    """SelectionScreen should have ProgressPane initially hidden."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        progress = tui_app.screen.query_one("#progress-pane", ProgressPane)
        assert progress.display is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_has_start_button(tui_app):
    """SelectionScreen should have Start Export and Back buttons."""
    from textual.widgets import Button

    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        start_btn = tui_app.screen.query_one("#btn-start", Button)
        back_btn = tui_app.screen.query_one("#btn-back", Button)
        assert start_btn is not None
        assert back_btn is not None
        assert "Start Export" in str(start_btn.label)


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
# ProgressPane Widget Tests (unit-level, mounted within an app)
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

        # Go to selection screen so ProgressPane is mounted
        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        pane = app.screen.query_one("#progress-pane", ProgressPane)

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

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        pane = app.screen.query_one("#progress-pane", ProgressPane)

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

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        pane = app.screen.query_one("#progress-pane", ProgressPane)

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

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        pane = app.screen.query_one("#progress-pane", ProgressPane)

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
# SelectionScreen Mode Transition Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_initial_mode():
    """SelectionScreen should start in 'select' mode."""
    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_mode"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, SelectionScreen)
        assert screen._mode == "select"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_mode_to_export():
    """Changing SelectionScreen mode to 'export' should update UI elements."""
    from textual.widgets import Button

    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_mode2"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, SelectionScreen)

        # Manually switch mode to export
        screen._mode = "export"
        await pilot.pause()

        # Progress pane should now be visible
        pane = screen.query_one("#progress-pane", ProgressPane)
        assert pane.display is True

        # Start button should say "Pause"
        start_btn = screen.query_one("#btn-start", Button)
        assert "Pause" in str(start_btn.label)

        # Back button should say "Cancel"
        back_btn = screen.query_one("#btn-back", Button)
        assert "Cancel" in str(back_btn.label)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_screen_mode_to_complete():
    """Changing SelectionScreen mode to 'complete' should show Done button."""
    from textual.widgets import Button

    app = WhatsAppExporterApp(
        output_dir=Path("/tmp/test_mode3"),
        dry_run=True,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await pilot.press("d")
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, SelectionScreen)

        # Manually switch mode to complete
        screen._mode = "complete"
        await pilot.pause()

        start_btn = screen.query_one("#btn-start", Button)
        assert "Done" in str(start_btn.label)

        # Back button should be hidden
        back_btn = screen.query_one("#btn-back", Button)
        assert back_btn.display is False
