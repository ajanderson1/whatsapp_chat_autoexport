"""
Device connection screen for TUI.

Handles device discovery and connection setup.
"""

from typing import Optional, List
from enum import Enum, auto
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.spinner import Spinner


class ConnectionState(Enum):
    """Connection state enumeration."""

    IDLE = auto()
    SCANNING = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    FAILED = auto()


@dataclass
class DeviceInfo:
    """Information about a discovered device."""

    device_id: str
    name: str
    model: str
    android_version: str
    connection_type: str  # "usb" or "wireless"


class DeviceConnectScreen:
    """
    Device connection screen.

    Shows:
    - Connection method selection (USB/Wireless)
    - Device discovery
    - Connection status
    - Pairing instructions for wireless
    """

    def __init__(self):
        """Initialize the device connect screen."""
        self._state = ConnectionState.IDLE
        self._devices: List[DeviceInfo] = []
        self._selected_device: int = 0
        self._selected_method: int = 0  # 0=USB, 1=Wireless
        self._error_message: Optional[str] = None
        self._wireless_ip: str = ""
        self._wireless_port: str = ""
        self._pairing_code: str = ""
        self._input_field: int = 0  # 0=IP, 1=Port, 2=Code

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    def set_state(self, state: ConnectionState) -> None:
        """Set the connection state."""
        self._state = state

    def set_devices(self, devices: List[DeviceInfo]) -> None:
        """Set discovered devices."""
        self._devices = devices

    def set_error(self, message: str) -> None:
        """Set error message."""
        self._error_message = message
        self._state = ConnectionState.FAILED

    def clear_error(self) -> None:
        """Clear error message."""
        self._error_message = None

    def select_usb(self) -> None:
        """Select USB connection method."""
        self._selected_method = 0

    def select_wireless(self) -> None:
        """Select wireless connection method."""
        self._selected_method = 1

    def toggle_method(self) -> None:
        """Toggle between USB and wireless."""
        self._selected_method = 1 - self._selected_method

    def select_next_device(self) -> None:
        """Select next device in list."""
        if self._devices:
            self._selected_device = (self._selected_device + 1) % len(self._devices)

    def select_prev_device(self) -> None:
        """Select previous device in list."""
        if self._devices:
            self._selected_device = (self._selected_device - 1) % len(self._devices)

    def get_selected_device(self) -> Optional[DeviceInfo]:
        """Get the currently selected device."""
        if self._devices and 0 <= self._selected_device < len(self._devices):
            return self._devices[self._selected_device]
        return None

    def set_wireless_config(self, ip: str, port: str, code: str) -> None:
        """Set wireless connection configuration."""
        self._wireless_ip = ip
        self._wireless_port = port
        self._pairing_code = code

    def next_input_field(self) -> None:
        """Move to next input field."""
        self._input_field = (self._input_field + 1) % 3

    def prev_input_field(self) -> None:
        """Move to previous input field."""
        self._input_field = (self._input_field - 1) % 3

    def render(self) -> Panel:
        """
        Render the device connect screen.

        Returns:
            Rich Panel containing connection display
        """
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

        # Connection method tabs
        method_row = self._render_method_tabs()
        table.add_row(Align.center(method_row))
        table.add_row("")

        # Content based on method and state
        if self._selected_method == 0:
            content = self._render_usb_content()
        else:
            content = self._render_wireless_content()

        table.add_row(content)

        # Error message if any
        if self._error_message:
            table.add_row("")
            error_text = Text(f"✗ {self._error_message}", style="bold red")
            table.add_row(Align.center(error_text))

        # Navigation hints
        table.add_row("")
        hints = self._render_hints()
        table.add_row(Align.center(hints))

        return Panel(
            table,
            title="[bold white]Connect Device[/]",
            border_style="cyan",
            padding=(1, 2),
        )

    def _render_method_tabs(self) -> Text:
        """Render connection method tabs."""
        text = Text()

        # USB tab
        if self._selected_method == 0:
            text.append(" 📱 USB ", style="bold white on blue")
        else:
            text.append(" 📱 USB ", style="dim")

        text.append("  ", style="dim")

        # Wireless tab
        if self._selected_method == 1:
            text.append(" 📶 Wireless ", style="bold white on blue")
        else:
            text.append(" 📶 Wireless ", style="dim")

        return text

    def _render_usb_content(self) -> Table:
        """Render USB connection content."""
        content = Table.grid(expand=True)
        content.add_column(ratio=1)

        if self._state == ConnectionState.SCANNING:
            # Scanning for devices
            spinner_text = Text()
            spinner_text.append("Scanning for USB devices", style="yellow")
            spinner_text.append("...", style="dim")
            content.add_row(Align.center(spinner_text))

        elif self._state == ConnectionState.CONNECTING:
            # Connecting
            connect_text = Text("Connecting to device...", style="yellow")
            content.add_row(Align.center(connect_text))

        elif self._state == ConnectionState.CONNECTED:
            # Connected
            device = self.get_selected_device()
            if device:
                connected_text = Text()
                connected_text.append("✓ Connected to ", style="green")
                connected_text.append(device.name, style="bold green")
                content.add_row(Align.center(connected_text))

        elif self._devices:
            # Show device list
            content.add_row(Text("Select a device:", style="bold"))
            content.add_row("")

            for i, device in enumerate(self._devices):
                if i == self._selected_device:
                    marker = "▸"
                    style = "bold cyan"
                else:
                    marker = " "
                    style = "white"

                device_text = Text()
                device_text.append(f"{marker} ", style=style)
                device_text.append(device.name, style=style)
                device_text.append(f" ({device.model})", style="dim")
                content.add_row(device_text)

        else:
            # No devices found
            no_device = Text()
            no_device.append("No USB devices found\n\n", style="yellow")
            no_device.append("Make sure:\n", style="dim")
            no_device.append("• Device is connected via USB\n", style="dim")
            no_device.append("• USB debugging is enabled\n", style="dim")
            no_device.append("• Device is unlocked", style="dim")
            content.add_row(Align.center(no_device))

        return content

    def _render_wireless_content(self) -> Table:
        """Render wireless connection content."""
        content = Table.grid(expand=True)
        content.add_column(ratio=1)

        if self._state == ConnectionState.CONNECTING:
            connect_text = Text("Connecting to device...", style="yellow")
            content.add_row(Align.center(connect_text))

        elif self._state == ConnectionState.CONNECTED:
            device = self.get_selected_device()
            if device:
                connected_text = Text()
                connected_text.append("✓ Connected to ", style="green")
                connected_text.append(device.name, style="bold green")
                content.add_row(Align.center(connected_text))

        else:
            # Instructions
            instructions = Text()
            instructions.append("Wireless ADB Setup\n\n", style="bold")
            instructions.append("1. On your phone: Settings → Developer Options → Wireless Debugging\n", style="dim")
            instructions.append("2. Tap 'Pair device with pairing code'\n", style="dim")
            instructions.append("3. Enter the IP, port, and pairing code below\n\n", style="dim")
            content.add_row(instructions)

            # Input fields
            fields = Table.grid()
            fields.add_column(width=15)
            fields.add_column(width=30)

            # IP field
            ip_style = "bold cyan" if self._input_field == 0 else "white"
            ip_value = self._wireless_ip or "_____________"
            fields.add_row(
                Text("IP Address:", style="dim"),
                Text(ip_value, style=ip_style),
            )

            # Port field
            port_style = "bold cyan" if self._input_field == 1 else "white"
            port_value = self._wireless_port or "_____"
            fields.add_row(
                Text("Port:", style="dim"),
                Text(port_value, style=port_style),
            )

            # Pairing code field
            code_style = "bold cyan" if self._input_field == 2 else "white"
            code_value = self._pairing_code or "______"
            fields.add_row(
                Text("Pairing Code:", style="dim"),
                Text(code_value, style=code_style),
            )

            content.add_row(Align.center(fields))

        return content

    def _render_hints(self) -> Text:
        """Render navigation hints."""
        hints = Text()

        hints.append("[Tab]", style="bold cyan")
        hints.append(" Switch method  ", style="dim")

        if self._selected_method == 0:
            # USB hints
            hints.append("[↑/↓]", style="bold cyan")
            hints.append(" Select device  ", style="dim")
            hints.append("[R]", style="bold cyan")
            hints.append(" Rescan  ", style="dim")
        else:
            # Wireless hints
            hints.append("[Tab]", style="bold cyan")
            hints.append(" Next field  ", style="dim")

        hints.append("[Enter]", style="bold cyan")
        hints.append(" Connect  ", style="dim")
        hints.append("[Esc]", style="bold cyan")
        hints.append(" Back", style="dim")

        return hints

    def __rich__(self) -> RenderableType:
        """Rich protocol for rendering."""
        return self.render()
