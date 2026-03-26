"""
Tests for legacy Rich TUI package.

Tests cover:
- Component rendering (ProgressPanel, QueuePanel, StatusBar)
- Screen state management
- Wizard navigation

NOTE: These test the Rich-based TUI code that has been moved to legacy/.
"""

import pytest
from datetime import datetime, timedelta

from whatsapp_chat_autoexport.legacy.tui.app import WhatsAppExportTUI
from whatsapp_chat_autoexport.legacy.tui.wizard import (
    ExportWizard,
    WizardStep,
    WizardState,
    WizardController,
)
from whatsapp_chat_autoexport.legacy.tui.components import (
    ProgressPanel,
    QueuePanel,
    StatusBar,
)
from whatsapp_chat_autoexport.legacy.tui.components.progress_panel import StepProgressPanel
from whatsapp_chat_autoexport.legacy.tui.components.queue_panel import QueueItemDisplay, CompactQueuePanel
from whatsapp_chat_autoexport.legacy.tui.components.status_bar import KeyBinding, MinimalStatusBar
from whatsapp_chat_autoexport.legacy.tui.screens import (
    WelcomeScreen,
    DeviceConnectScreen,
    ChatSelectionScreen,
    ExportProgressScreen,
    SummaryScreen,
)
from whatsapp_chat_autoexport.legacy.tui.screens.device_connect import DeviceInfo, ConnectionState
from whatsapp_chat_autoexport.legacy.tui.screens.chat_selection import ChatInfo
from whatsapp_chat_autoexport.legacy.tui.screens.summary import ExportResult
from whatsapp_chat_autoexport.state.models import ChatStatus, ChatState


# =============================================================================
# ProgressPanel Tests
# =============================================================================


class TestProgressPanel:
    """Tests for ProgressPanel component."""

    def test_create_progress_panel(self):
        """Test creating a progress panel."""
        panel = ProgressPanel()
        assert panel is not None

    def test_start_tracking(self):
        """Test starting progress tracking."""
        panel = ProgressPanel()
        panel.start(10)

        # Panel should track totals
        assert panel._total == 10
        assert panel._completed == 0

    def test_update_chat(self):
        """Test updating current chat."""
        panel = ProgressPanel()
        panel.start(5)
        panel.update_chat("Test Chat", "Opening menu")

        assert panel._current_chat == "Test Chat"
        assert panel._current_step == "Opening menu"

    def test_advance_progress(self):
        """Test advancing progress."""
        panel = ProgressPanel()
        panel.start(5)

        panel.advance("completed")
        assert panel._completed == 1

        panel.advance("failed")
        assert panel._failed == 1

        panel.advance("skipped")
        assert panel._skipped == 1

    def test_render_returns_panel(self):
        """Test that render returns a Rich Panel."""
        from rich.panel import Panel

        progress_panel = ProgressPanel()
        progress_panel.start(5)

        result = progress_panel.render()
        assert isinstance(result, Panel)

    def test_rich_protocol(self):
        """Test Rich protocol implementation."""
        panel = ProgressPanel()
        panel.start(5)

        result = panel.__rich__()
        assert result is not None


class TestStepProgressPanel:
    """Tests for StepProgressPanel component."""

    def test_create_step_panel(self):
        """Test creating step progress panel."""
        panel = StepProgressPanel()
        assert len(panel.STEPS) == 6

    def test_set_chat(self):
        """Test setting current chat."""
        panel = StepProgressPanel()
        panel.set_chat("Test Chat")

        assert panel._chat_name == "Test Chat"
        assert panel._current_step == 0
        assert panel._status == "in_progress"

    def test_advance_step(self):
        """Test advancing steps."""
        panel = StepProgressPanel()
        panel.set_chat("Test Chat")

        panel.advance_step()
        assert panel._current_step == 1

        panel.advance_step()
        assert panel._current_step == 2

    def test_complete(self):
        """Test completing chat."""
        panel = StepProgressPanel()
        panel.set_chat("Test Chat")
        panel.complete()

        assert panel._current_step == 6
        assert panel._status == "completed"

    def test_fail(self):
        """Test failing chat."""
        panel = StepProgressPanel()
        panel.set_chat("Test Chat")
        panel.fail()

        assert panel._status == "failed"

    def test_render(self):
        """Test rendering step panel."""
        from rich.panel import Panel

        step_panel = StepProgressPanel()
        step_panel.set_chat("Test Chat")

        result = step_panel.render()
        assert isinstance(result, Panel)


# =============================================================================
# QueuePanel Tests
# =============================================================================


class TestQueuePanel:
    """Tests for QueuePanel component."""

    def test_create_queue_panel(self):
        """Test creating queue panel."""
        panel = QueuePanel()
        assert panel is not None

    def test_set_items(self):
        """Test setting queue items."""
        panel = QueuePanel()

        items = [
            QueueItemDisplay(name="Chat 1", status=ChatStatus.PENDING),
            QueueItemDisplay(name="Chat 2", status=ChatStatus.IN_PROGRESS),
            QueueItemDisplay(name="Chat 3", status=ChatStatus.COMPLETED),
        ]

        panel.set_items(items)
        assert len(panel._items) == 3

    def test_update_from_chats(self):
        """Test updating from ChatState list."""
        panel = QueuePanel()

        chats = [
            ChatState(name="Chat 1", index=0, status=ChatStatus.PENDING),
            ChatState(name="Chat 2", index=1, status=ChatStatus.IN_PROGRESS),
        ]

        panel.update_from_chats(chats)
        assert len(panel._items) == 2

    def test_update_item(self):
        """Test updating a specific item."""
        panel = QueuePanel()

        items = [
            QueueItemDisplay(name="Chat 1", status=ChatStatus.PENDING),
        ]
        panel.set_items(items)

        panel.update_item("Chat 1", status=ChatStatus.COMPLETED)

        assert panel._items[0].status == ChatStatus.COMPLETED

    def test_scroll(self):
        """Test scrolling functionality."""
        panel = QueuePanel(max_visible=2)

        items = [
            QueueItemDisplay(name=f"Chat {i}", status=ChatStatus.PENDING)
            for i in range(5)
        ]
        panel.set_items(items)

        assert panel._scroll_offset == 0

        panel.scroll_down()
        assert panel._scroll_offset == 1

        panel.scroll_up()
        assert panel._scroll_offset == 0

    def test_render(self):
        """Test rendering queue panel."""
        from rich.panel import Panel

        queue_panel = QueuePanel()
        queue_panel.set_items([
            QueueItemDisplay(name="Chat 1", status=ChatStatus.PENDING),
        ])

        result = queue_panel.render()
        assert isinstance(result, Panel)


class TestCompactQueuePanel:
    """Tests for CompactQueuePanel."""

    def test_render_compact(self):
        """Test rendering compact queue."""
        from rich.panel import Panel

        panel = CompactQueuePanel()
        panel.set_items([
            QueueItemDisplay(name="Chat 1", status=ChatStatus.COMPLETED),
            QueueItemDisplay(name="Chat 2", status=ChatStatus.FAILED),
        ])

        result = panel.render()
        assert isinstance(result, Panel)


# =============================================================================
# StatusBar Tests
# =============================================================================


class TestStatusBar:
    """Tests for StatusBar component."""

    def test_create_status_bar(self):
        """Test creating status bar."""
        bar = StatusBar()
        assert len(bar._bindings) > 0

    def test_set_status(self):
        """Test setting status message."""
        bar = StatusBar()
        bar.set_status("Exporting", "green")

        assert bar._status == "Exporting"
        assert bar._status_style == "green"

    def test_set_device_status(self):
        """Test setting device status."""
        bar = StatusBar()

        bar.set_device_status("Connected", connected=True)
        assert bar._device_style == "green"

        bar.set_device_status("Disconnected", connected=False)
        assert bar._device_style == "red"

    def test_set_paused(self):
        """Test setting paused state."""
        bar = StatusBar()
        bar.set_paused(True)

        assert bar._paused is True

    def test_enable_binding(self):
        """Test enabling/disabling bindings."""
        bar = StatusBar()

        bar.enable_binding("Space", enabled=False)

        for binding in bar._bindings:
            if binding.key == "Space":
                assert binding.enabled is False
                break

    def test_render(self):
        """Test rendering status bar."""
        from rich.panel import Panel

        bar = StatusBar()
        result = bar.render()

        assert isinstance(result, Panel)

    def test_render_compact(self):
        """Test rendering compact status bar."""
        from rich.text import Text

        bar = StatusBar()
        result = bar.render_compact()

        assert isinstance(result, Text)


class TestMinimalStatusBar:
    """Tests for MinimalStatusBar."""

    def test_set_message(self):
        """Test setting messages."""
        bar = MinimalStatusBar()

        bar.info("Info message")
        assert "Info message" in bar._message

        bar.success("Success message")
        assert "Success message" in bar._message

        bar.warning("Warning message")
        assert "Warning message" in bar._message

        bar.error("Error message")
        assert "Error message" in bar._message


# =============================================================================
# WelcomeScreen Tests
# =============================================================================


class TestWelcomeScreen:
    """Tests for WelcomeScreen."""

    def test_create_welcome_screen(self):
        """Test creating welcome screen."""
        screen = WelcomeScreen()
        assert len(screen._options) == 5

    def test_navigation(self):
        """Test option navigation."""
        screen = WelcomeScreen()

        assert screen.selected_option == 0

        screen.select_next()
        assert screen.selected_option == 1

        screen.select_prev()
        assert screen.selected_option == 0

    def test_wrap_around(self):
        """Test navigation wrap-around."""
        screen = WelcomeScreen()

        screen.select_prev()  # Should wrap to last
        assert screen.selected_option == 4

    def test_get_selected_action(self):
        """Test getting selected action."""
        screen = WelcomeScreen()

        assert screen.get_selected_action() == "wizard"

        screen.select_next()
        assert screen.get_selected_action() == "quick"

    def test_render(self):
        """Test rendering welcome screen."""
        from rich.panel import Panel

        screen = WelcomeScreen()
        result = screen.render()

        assert isinstance(result, Panel)


# =============================================================================
# DeviceConnectScreen Tests
# =============================================================================


class TestDeviceConnectScreen:
    """Tests for DeviceConnectScreen."""

    def test_create_screen(self):
        """Test creating device connect screen."""
        screen = DeviceConnectScreen()
        assert screen.state == ConnectionState.IDLE

    def test_set_state(self):
        """Test setting connection state."""
        screen = DeviceConnectScreen()

        screen.set_state(ConnectionState.SCANNING)
        assert screen.state == ConnectionState.SCANNING

    def test_toggle_method(self):
        """Test toggling connection method."""
        screen = DeviceConnectScreen()

        assert screen._selected_method == 0  # USB

        screen.toggle_method()
        assert screen._selected_method == 1  # Wireless

    def test_set_devices(self):
        """Test setting discovered devices."""
        screen = DeviceConnectScreen()

        devices = [
            DeviceInfo(
                device_id="device1",
                name="Phone 1",
                model="Pixel",
                android_version="12",
                connection_type="usb",
            ),
        ]

        screen.set_devices(devices)
        assert len(screen._devices) == 1

    def test_device_selection(self):
        """Test device selection navigation."""
        screen = DeviceConnectScreen()

        devices = [
            DeviceInfo("d1", "Phone 1", "Pixel", "12", "usb"),
            DeviceInfo("d2", "Phone 2", "Samsung", "13", "usb"),
        ]
        screen.set_devices(devices)

        screen.select_next_device()
        assert screen._selected_device == 1

        screen.select_prev_device()
        assert screen._selected_device == 0

    def test_get_selected_device(self):
        """Test getting selected device."""
        screen = DeviceConnectScreen()

        # No devices
        assert screen.get_selected_device() is None

        # With devices
        device = DeviceInfo("d1", "Phone 1", "Pixel", "12", "usb")
        screen.set_devices([device])

        selected = screen.get_selected_device()
        assert selected == device

    def test_set_error(self):
        """Test setting error message."""
        screen = DeviceConnectScreen()

        screen.set_error("Connection failed")

        assert screen._error_message == "Connection failed"
        assert screen.state == ConnectionState.FAILED

    def test_render(self):
        """Test rendering device connect screen."""
        from rich.panel import Panel

        screen = DeviceConnectScreen()
        result = screen.render()

        assert isinstance(result, Panel)


# =============================================================================
# ChatSelectionScreen Tests
# =============================================================================


class TestChatSelectionScreen:
    """Tests for ChatSelectionScreen."""

    def test_create_screen(self):
        """Test creating chat selection screen."""
        screen = ChatSelectionScreen()
        assert screen.selection_count == 0

    def test_set_chats(self):
        """Test setting available chats."""
        screen = ChatSelectionScreen()

        chats = [
            ChatInfo(name="Chat 1"),
            ChatInfo(name="Chat 2", is_group=True),
        ]
        screen.set_chats(chats)

        assert len(screen.chats) == 2

    def test_navigation(self):
        """Test cursor navigation."""
        screen = ChatSelectionScreen()

        chats = [ChatInfo(name=f"Chat {i}") for i in range(5)]
        screen.set_chats(chats)

        screen.move_down()
        assert screen._cursor == 1

        screen.move_up()
        assert screen._cursor == 0

    def test_toggle_selection(self):
        """Test toggling chat selection."""
        screen = ChatSelectionScreen()

        chats = [ChatInfo(name="Chat 1")]
        screen.set_chats(chats)

        screen.toggle_selection()
        assert "Chat 1" in screen.selected_chats

        screen.toggle_selection()
        assert "Chat 1" not in screen.selected_chats

    def test_cannot_select_community(self):
        """Test that community chats cannot be selected."""
        screen = ChatSelectionScreen()

        chats = [ChatInfo(name="Community", is_community=True)]
        screen.set_chats(chats)

        screen.toggle_selection()
        assert screen.selection_count == 0

    def test_select_all(self):
        """Test selecting all chats."""
        screen = ChatSelectionScreen()

        chats = [
            ChatInfo(name="Chat 1"),
            ChatInfo(name="Chat 2"),
            ChatInfo(name="Community", is_community=True),
        ]
        screen.set_chats(chats)

        screen.select_all()
        assert screen.selection_count == 2  # Excludes community

    def test_select_none(self):
        """Test deselecting all chats."""
        screen = ChatSelectionScreen()

        chats = [ChatInfo(name="Chat 1")]
        screen.set_chats(chats)

        screen.toggle_selection()
        assert screen.selection_count == 1

        screen.select_none()
        assert screen.selection_count == 0

    def test_filter(self):
        """Test filtering chats."""
        screen = ChatSelectionScreen()

        chats = [
            ChatInfo(name="Alice"),
            ChatInfo(name="Bob"),
            ChatInfo(name="Charlie"),
        ]
        screen.set_chats(chats)

        screen.set_filter("ali")

        filtered = screen._filtered_chats()
        assert len(filtered) == 1
        assert filtered[0].name == "Alice"

    def test_render(self):
        """Test rendering chat selection screen."""
        from rich.panel import Panel

        screen = ChatSelectionScreen()
        result = screen.render()

        assert isinstance(result, Panel)


# =============================================================================
# ExportProgressScreen Tests
# =============================================================================


class TestExportProgressScreen:
    """Tests for ExportProgressScreen."""

    def test_create_screen(self):
        """Test creating export progress screen."""
        screen = ExportProgressScreen()
        assert not screen.paused

    def test_start(self):
        """Test starting progress tracking."""
        screen = ExportProgressScreen()

        chats = [
            ChatState(name="Chat 1", index=0),
            ChatState(name="Chat 2", index=1),
        ]
        screen.start(2, chats)

        # Should be tracking

    def test_start_chat(self):
        """Test marking chat as started."""
        screen = ExportProgressScreen()
        screen.start_chat("Test Chat")

        assert screen._current_chat == "Test Chat"

    def test_complete_chat(self):
        """Test completing a chat."""
        screen = ExportProgressScreen()
        screen.start_chat("Test Chat")
        screen.complete_chat("Test Chat")

        # Step panel should show completed

    def test_pause_resume(self):
        """Test pause and resume."""
        screen = ExportProgressScreen()

        screen.pause()
        assert screen.paused

        screen.resume()
        assert not screen.paused

    def test_toggle_pause(self):
        """Test toggle pause."""
        screen = ExportProgressScreen()

        screen.toggle_pause()
        assert screen.paused

        screen.toggle_pause()
        assert not screen.paused

    def test_render(self):
        """Test rendering progress screen."""
        from rich.panel import Panel

        screen = ExportProgressScreen()
        result = screen.render()

        assert isinstance(result, Panel)

    def test_compact_mode(self):
        """Test compact mode rendering."""
        from rich.panel import Panel

        screen = ExportProgressScreen(compact_mode=True)
        result = screen.render()

        assert isinstance(result, Panel)


# =============================================================================
# SummaryScreen Tests
# =============================================================================


class TestSummaryScreen:
    """Tests for SummaryScreen."""

    def test_create_screen(self):
        """Test creating summary screen."""
        screen = SummaryScreen()
        assert screen.completed_count == 0

    def test_set_results(self):
        """Test setting export results."""
        screen = SummaryScreen()

        results = [
            ExportResult(name="Chat 1", status=ChatStatus.COMPLETED),
            ExportResult(name="Chat 2", status=ChatStatus.FAILED, error="Error"),
            ExportResult(name="Chat 3", status=ChatStatus.SKIPPED, error="Skipped"),
        ]
        screen.set_results(results)

        assert screen.completed_count == 1
        assert screen.failed_count == 1
        assert screen.skipped_count == 1

    def test_tabs(self):
        """Test tab navigation."""
        screen = SummaryScreen()

        assert screen._selected_tab == 0

        screen.next_tab()
        assert screen._selected_tab == 1

        screen.prev_tab()
        assert screen._selected_tab == 0

    def test_toggle_details(self):
        """Test toggling details view."""
        screen = SummaryScreen()

        assert screen._show_details is True

        screen.toggle_details()
        assert screen._show_details is False

    def test_render(self):
        """Test rendering summary screen."""
        from rich.panel import Panel

        screen = SummaryScreen()
        screen.set_results([
            ExportResult(name="Chat 1", status=ChatStatus.COMPLETED),
        ])

        result = screen.render()
        assert isinstance(result, Panel)


# =============================================================================
# Wizard Tests
# =============================================================================


class TestExportWizard:
    """Tests for ExportWizard."""

    def test_create_wizard(self):
        """Test creating wizard."""
        wizard = ExportWizard()
        assert wizard.current_step == WizardStep.WELCOME

    def test_navigation(self):
        """Test step navigation."""
        wizard = ExportWizard()

        wizard.next_step()
        assert wizard.current_step == WizardStep.DEVICE_CONNECT

        wizard.prev_step()
        assert wizard.current_step == WizardStep.WELCOME

    def test_go_to_step(self):
        """Test direct step navigation."""
        wizard = ExportWizard()

        wizard.go_to_step(WizardStep.CHAT_SELECTION)
        assert wizard.current_step == WizardStep.CHAT_SELECTION

    def test_cancel(self):
        """Test cancelling wizard."""
        wizard = ExportWizard()

        wizard.cancel()
        assert wizard.state.is_running is False

    def test_get_current_screen(self):
        """Test getting current screen."""
        wizard = ExportWizard()

        screen = wizard.get_current_screen()
        assert isinstance(screen, WelcomeScreen)

        wizard.go_to_step(WizardStep.DEVICE_CONNECT)
        screen = wizard.get_current_screen()
        assert isinstance(screen, DeviceConnectScreen)

    def test_render_current(self):
        """Test rendering current screen."""
        from rich.panel import Panel

        wizard = ExportWizard()
        result = wizard.render_current()

        assert isinstance(result, Panel)


class TestWizardController:
    """Tests for WizardController."""

    def test_create_controller(self):
        """Test creating controller."""
        wizard = ExportWizard()
        controller = WizardController(wizard)

        assert controller is not None

    def test_handle_quit(self):
        """Test handling quit key."""
        wizard = ExportWizard()
        controller = WizardController(wizard)

        result = controller.handle_key("q")

        assert result is True
        assert wizard.state.is_running is False

    def test_welcome_navigation(self):
        """Test welcome screen navigation."""
        wizard = ExportWizard()
        controller = WizardController(wizard)

        # Down key
        controller.handle_key("down")
        assert wizard._welcome.selected_option == 1

        # Up key
        controller.handle_key("up")
        assert wizard._welcome.selected_option == 0

    def test_welcome_enter(self):
        """Test enter on welcome screen."""
        wizard = ExportWizard()
        controller = WizardController(wizard)

        # Enter selects wizard
        controller.handle_key("enter")
        assert wizard.current_step == WizardStep.DEVICE_CONNECT


# =============================================================================
# WhatsAppExportTUI Tests
# =============================================================================


class TestWhatsAppExportTUI:
    """Tests for WhatsAppExportTUI."""

    def test_create_tui(self):
        """Test creating TUI application."""
        tui = WhatsAppExportTUI()
        assert tui is not None

    def test_render(self):
        """Test rendering TUI."""
        from rich.panel import Panel

        tui = WhatsAppExportTUI()
        result = tui.render()

        assert isinstance(result, Panel)

    def test_update_progress(self):
        """Test updating progress."""
        from whatsapp_chat_autoexport.state.models import ExportProgress

        tui = WhatsAppExportTUI()

        progress = ExportProgress(
            current_chat="Test Chat",
            chats_completed=1,
            chats_total=5,
        )

        tui.update_progress(progress)

    def test_chat_lifecycle(self):
        """Test chat lifecycle methods."""
        tui = WhatsAppExportTUI()

        tui.start_chat("Test Chat")
        tui.complete_chat("Test Chat")

        tui.start_chat("Chat 2")
        tui.fail_chat("Chat 2", "Error")

        tui.skip_chat("Chat 3", "Skipped")

    def test_pause_resume(self):
        """Test pause and resume."""
        tui = WhatsAppExportTUI()

        tui.pause()
        tui.resume()
