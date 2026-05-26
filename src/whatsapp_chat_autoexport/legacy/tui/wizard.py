"""
Export wizard for step-by-step workflow.

Provides an interactive wizard that guides users through the export process.
"""

from typing import Optional, List, Callable, Any
from enum import Enum, auto
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live

from .screens import (
    WelcomeScreen,
    DeviceConnectScreen,
    ChatSelectionScreen,
    ExportProgressScreen,
    SummaryScreen,
)
from .screens.device_connect import DeviceInfo, ConnectionState
from .screens.chat_selection import ChatInfo


class WizardStep(Enum):
    """Steps in the export wizard."""

    WELCOME = auto()
    DEVICE_CONNECT = auto()
    CHAT_SELECTION = auto()
    EXPORT_PROGRESS = auto()
    SUMMARY = auto()


@dataclass
class WizardState:
    """State of the wizard workflow."""

    current_step: WizardStep = WizardStep.WELCOME
    device: Optional[DeviceInfo] = None
    selected_chats: List[str] = field(default_factory=list)
    include_media: bool = True
    output_path: str = ""
    is_running: bool = True
    error: Optional[str] = None


class ExportWizard:
    """
    Interactive export wizard.

    Guides users through:
    1. Welcome/menu
    2. Device connection
    3. Chat selection
    4. Export progress
    5. Summary
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize the wizard.

        Args:
            console: Rich console for output
        """
        self._console = console or Console()
        self._state = WizardState()

        # Initialize screens
        self._welcome = WelcomeScreen()
        self._device_connect = DeviceConnectScreen()
        self._chat_selection = ChatSelectionScreen()
        self._export_progress = ExportProgressScreen()
        self._summary = SummaryScreen()

        # Callbacks
        self._on_device_connect: Optional[Callable[[str], DeviceInfo]] = None
        self._on_scan_devices: Optional[Callable[[], List[DeviceInfo]]] = None
        self._on_collect_chats: Optional[Callable[[], List[ChatInfo]]] = None
        self._on_start_export: Optional[Callable[[List[str], bool], None]] = None
        self._on_cancel: Optional[Callable[[], None]] = None

    @property
    def state(self) -> WizardState:
        """Get current wizard state."""
        return self._state

    @property
    def current_step(self) -> WizardStep:
        """Get current wizard step."""
        return self._state.current_step

    def set_device_connect_callback(
        self,
        callback: Callable[[str], DeviceInfo],
    ) -> None:
        """Set callback for device connection."""
        self._on_device_connect = callback

    def set_scan_devices_callback(
        self,
        callback: Callable[[], List[DeviceInfo]],
    ) -> None:
        """Set callback for device scanning."""
        self._on_scan_devices = callback

    def set_collect_chats_callback(
        self,
        callback: Callable[[], List[ChatInfo]],
    ) -> None:
        """Set callback for chat collection."""
        self._on_collect_chats = callback

    def set_start_export_callback(
        self,
        callback: Callable[[List[str], bool], None],
    ) -> None:
        """Set callback for starting export."""
        self._on_start_export = callback

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for cancellation."""
        self._on_cancel = callback

    def go_to_step(self, step: WizardStep) -> None:
        """
        Navigate to a specific step.

        Args:
            step: Target wizard step
        """
        self._state.current_step = step

    def next_step(self) -> None:
        """Advance to the next step."""
        current = self._state.current_step

        if current == WizardStep.WELCOME:
            self._state.current_step = WizardStep.DEVICE_CONNECT
        elif current == WizardStep.DEVICE_CONNECT:
            self._state.current_step = WizardStep.CHAT_SELECTION
        elif current == WizardStep.CHAT_SELECTION:
            self._state.current_step = WizardStep.EXPORT_PROGRESS
        elif current == WizardStep.EXPORT_PROGRESS:
            self._state.current_step = WizardStep.SUMMARY

    def prev_step(self) -> None:
        """Go back to the previous step."""
        current = self._state.current_step

        if current == WizardStep.DEVICE_CONNECT:
            self._state.current_step = WizardStep.WELCOME
        elif current == WizardStep.CHAT_SELECTION:
            self._state.current_step = WizardStep.DEVICE_CONNECT
        elif current == WizardStep.SUMMARY:
            self._state.current_step = WizardStep.CHAT_SELECTION

    def cancel(self) -> None:
        """Cancel the wizard."""
        self._state.is_running = False
        if self._on_cancel:
            self._on_cancel()

    def get_current_screen(self) -> Any:
        """Get the screen for the current step."""
        step = self._state.current_step

        if step == WizardStep.WELCOME:
            return self._welcome
        elif step == WizardStep.DEVICE_CONNECT:
            return self._device_connect
        elif step == WizardStep.CHAT_SELECTION:
            return self._chat_selection
        elif step == WizardStep.EXPORT_PROGRESS:
            return self._export_progress
        elif step == WizardStep.SUMMARY:
            return self._summary

    def render_current(self) -> Any:
        """Render the current screen."""
        return self.get_current_screen().render()

    # Welcome screen actions
    def handle_welcome_action(self, action: str) -> None:
        """Handle action from welcome screen."""
        if action == "wizard":
            self.next_step()
        elif action == "quick":
            # Quick mode - skip to chat selection after connect
            self._state.include_media = True
            self.next_step()
        elif action == "exit":
            self.cancel()

    # Device connect actions
    def scan_devices(self) -> None:
        """Scan for available devices."""
        self._device_connect.set_state(ConnectionState.SCANNING)

        if self._on_scan_devices:
            devices = self._on_scan_devices()
            self._device_connect.set_devices(devices)
            self._device_connect.set_state(ConnectionState.IDLE)

    def connect_device(self, device_id: str) -> bool:
        """
        Connect to a device.

        Args:
            device_id: Device identifier

        Returns:
            True if connection successful
        """
        self._device_connect.set_state(ConnectionState.CONNECTING)

        if self._on_device_connect:
            try:
                device = self._on_device_connect(device_id)
                self._state.device = device
                self._device_connect.set_state(ConnectionState.CONNECTED)
                return True
            except Exception as e:
                self._device_connect.set_error(str(e))
                return False

        return False

    # Chat selection actions
    def collect_chats(self) -> None:
        """Collect available chats from device."""
        self._chat_selection.set_loading(True)

        if self._on_collect_chats:
            chats = self._on_collect_chats()
            self._chat_selection.set_chats(chats)
            self._chat_selection.set_loading(False)

    def confirm_selection(self) -> None:
        """Confirm chat selection and start export."""
        self._state.selected_chats = self._chat_selection.selected_chats
        self.next_step()

    # Export progress actions
    def start_export(self) -> None:
        """Start the export process."""
        if self._on_start_export:
            self._on_start_export(
                self._state.selected_chats,
                self._state.include_media,
            )

    def pause_export(self) -> None:
        """Pause the export."""
        self._export_progress.pause()

    def resume_export(self) -> None:
        """Resume the export."""
        self._export_progress.resume()

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self._export_progress.toggle_pause()

    # Summary actions
    def retry_failed(self) -> None:
        """Retry failed exports."""
        # Collect failed chat names and restart export for those
        pass

    def finish(self) -> None:
        """Complete the wizard."""
        self._state.is_running = False


class WizardController:
    """
    Controller for wizard input handling.

    Translates keyboard input to wizard actions.
    """

    def __init__(self, wizard: ExportWizard):
        """
        Initialize the controller.

        Args:
            wizard: ExportWizard instance to control
        """
        self._wizard = wizard

    def handle_key(self, key: str) -> bool:
        """
        Handle a key press.

        Args:
            key: Key that was pressed

        Returns:
            True if key was handled
        """
        step = self._wizard.current_step

        # Global keys
        if key.lower() == "q":
            self._wizard.cancel()
            return True

        # Step-specific handling
        if step == WizardStep.WELCOME:
            return self._handle_welcome_key(key)
        elif step == WizardStep.DEVICE_CONNECT:
            return self._handle_device_connect_key(key)
        elif step == WizardStep.CHAT_SELECTION:
            return self._handle_chat_selection_key(key)
        elif step == WizardStep.EXPORT_PROGRESS:
            return self._handle_export_progress_key(key)
        elif step == WizardStep.SUMMARY:
            return self._handle_summary_key(key)

        return False

    def _handle_welcome_key(self, key: str) -> bool:
        """Handle key in welcome screen."""
        screen = self._wizard._welcome

        if key == "up":
            screen.select_prev()
            return True
        elif key == "down":
            screen.select_next()
            return True
        elif key == "enter":
            action = screen.get_selected_action()
            self._wizard.handle_welcome_action(action)
            return True

        return False

    def _handle_device_connect_key(self, key: str) -> bool:
        """Handle key in device connect screen."""
        screen = self._wizard._device_connect

        if key == "tab":
            screen.toggle_method()
            return True
        elif key == "up":
            screen.select_prev_device()
            return True
        elif key == "down":
            screen.select_next_device()
            return True
        elif key.lower() == "r":
            self._wizard.scan_devices()
            return True
        elif key == "enter":
            device = screen.get_selected_device()
            if device:
                if self._wizard.connect_device(device.device_id):
                    self._wizard.next_step()
            return True
        elif key == "escape":
            self._wizard.prev_step()
            return True

        return False

    def _handle_chat_selection_key(self, key: str) -> bool:
        """Handle key in chat selection screen."""
        screen = self._wizard._chat_selection

        if key == "up":
            screen.move_up()
            return True
        elif key == "down":
            screen.move_down()
            return True
        elif key == "pageup":
            screen.page_up()
            return True
        elif key == "pagedown":
            screen.page_down()
            return True
        elif key == "space":
            screen.toggle_selection()
            return True
        elif key.lower() == "a":
            screen.select_all()
            return True
        elif key.lower() == "n":
            screen.select_none()
            return True
        elif key.lower() == "e":
            screen.toggle_show_exported()
            return True
        elif key == "enter":
            if screen.selection_count > 0:
                self._wizard.confirm_selection()
            return True
        elif key == "escape":
            self._wizard.prev_step()
            return True

        return False

    def _handle_export_progress_key(self, key: str) -> bool:
        """Handle key in export progress screen."""
        if key == "space":
            self._wizard.toggle_pause()
            return True
        elif key.lower() == "s":
            # Skip current chat (would need to implement)
            return True

        return False

    def _handle_summary_key(self, key: str) -> bool:
        """Handle key in summary screen."""
        screen = self._wizard._summary

        if key == "left":
            screen.prev_tab()
            return True
        elif key == "right":
            screen.next_tab()
            return True
        elif key.lower() == "d":
            screen.toggle_details()
            return True
        elif key.lower() == "r":
            self._wizard.retry_failed()
            return True
        elif key == "enter":
            self._wizard.finish()
            return True

        return False
