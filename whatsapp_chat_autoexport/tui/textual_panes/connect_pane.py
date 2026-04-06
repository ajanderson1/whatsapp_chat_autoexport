"""
ConnectPane -- device connection pane for the Connect tab.

Extracted from DiscoveryScreen.  Handles USB device scanning, wireless ADB
pairing/connection, Appium startup, and WhatsApp driver initialisation.

On successful connection the pane posts a ``ConnectPane.Connected`` message
so that MainScreen can advance the workflow.
"""

import asyncio
import hashlib
import re
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, Button, ListView, ListItem, Label, Input, Rule
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from ..textual_widgets.activity_log import ActivityLog
from ...export.appium_manager import AppiumManager


class ConnectPane(Container):
    """
    Device-connection pane that lives inside the Connect TabPane.

    Responsibilities:
    - Scan for USB devices via ``adb devices``
    - Wireless ADB pair + connect (two-step flow)
    - Start Appium server
    - Create a WhatsAppDriver and connect to the device
    - Emit ``ConnectPane.Connected`` when the driver is ready
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class Connected(Message):
        """Emitted when device connection succeeds."""

        def __init__(self, driver) -> None:
            super().__init__()
            self.driver = driver

    # ------------------------------------------------------------------
    # Bindings  (active when this pane has focus)
    # ------------------------------------------------------------------

    BINDINGS = [
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("enter", "connect_device", "Connect", show=True),
        Binding("d", "use_dry_run", "Dry Run", show=False),
    ]

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._devices: List[dict] = []
        self._selected_device: Optional[str] = None
        self._connecting = False
        self._updating_device_list = False
        self._last_scan_had_devices: Optional[bool] = None
        self._wireless_connecting = False
        self._wireless_pairing_ip: Optional[str] = None

        # Appium server management
        self._appium_started = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Device Discovery[/bold]\n\n"
            "Scanning for connected Android devices...",
            id="instructions",
            classes="instructions",
        )
        yield Static(
            "[yellow]Searching...[/yellow]",
            id="device-status",
        )
        yield ListView(id="device-list")
        with Horizontal(id="action-buttons"):
            yield Button("Refresh", id="btn-refresh", variant="default")
            yield Button("Connect", id="btn-connect", variant="primary", disabled=True)

        # Wireless ADB section
        yield Rule(line_style="heavy")
        yield Static(
            "[bold]Wireless ADB Connection[/bold]",
            classes="wireless-title",
        )
        yield Static(
            "Pair with a device over WiFi. On your phone: "
            "Settings > Developer Options > Wireless Debugging > Pair device.",
            classes="wireless-hint",
        )
        with Vertical(id="wireless-section"):
            yield Static("IP:Port (from pairing dialog):", classes="field-label")
            yield Input(
                placeholder="192.168.1.100:37453",
                id="wireless-ip-port",
            )
            yield Static("Pairing Code:", classes="field-label")
            yield Input(
                placeholder="123456",
                id="wireless-pairing-code",
            )
            with Horizontal(id="wireless-buttons"):
                yield Button(
                    "Connect Wirelessly",
                    id="btn-wireless-connect",
                    variant="primary",
                )
            yield Static("", id="wireless-status")
            # Connect port section -- hidden until pairing succeeds
            with Vertical(id="wireless-connect-section", classes="hidden"):
                yield Static(
                    "Connect Port (from main Wireless Debugging screen "
                    "-- NOT the pairing dialog):",
                    classes="field-label",
                )
                yield Input(
                    placeholder="e.g. 39765",
                    id="wireless-connect-port",
                )
                yield Button(
                    "Connect",
                    id="btn-wireless-finish-connect",
                    variant="success",
                )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        """Start device scanning when mounted."""
        activity = self.screen.query_one(ActivityLog)
        activity.log_info("WhatsApp Exporter starting...")
        activity.log("Scanning for Android devices...")

        self.run_worker(self._scan_devices(), name="scan_devices")

        # Pre-fill wireless ADB fields if CLI flag was passed
        wireless_adb = getattr(self.app, "wireless_adb", None)
        if wireless_adb:
            ip_port_input = self.query_one("#wireless-ip-port", Input)
            if isinstance(wireless_adb, str) and wireless_adb not in ("True", "true"):
                ip_port_input.value = wireless_adb

    # ------------------------------------------------------------------
    # Workers: device scanning
    # ------------------------------------------------------------------

    async def _scan_devices(self) -> List[dict]:
        """Scan for connected Android devices via ``adb devices -l``."""
        import subprocess

        devices = []
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
                close_fds=True,
            )
            lines = result.stdout.strip().split("\n")[1:]
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]
                    model = "Unknown"
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split(":")[1]
                            break
                    devices.append({"id": device_id, "status": status, "model": model})
        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return devices

    # ------------------------------------------------------------------
    # Worker state dispatch
    # ------------------------------------------------------------------

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:  # noqa: C901
        """Route worker completions to the appropriate handler."""
        worker = event.worker
        state = worker.state
        is_finished = state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)
        is_failed = state == WorkerState.ERROR

        if worker.name == "scan_devices":
            if is_finished:
                if is_failed:
                    self._handle_worker_error("scan_devices", getattr(worker, "error", None))
                elif worker.result is None:
                    self._handle_worker_error("scan_devices", "No result returned")
                else:
                    self.call_later(self._safe_update_device_list, worker.result)

        elif worker.name == "start_appium":
            if is_finished:
                if is_failed:
                    self._connecting = False
                    self._handle_worker_error("start_appium", getattr(worker, "error", None))
                elif worker.result is None:
                    self._connecting = False
                    self._handle_worker_error("start_appium", "No result returned")
                else:
                    result = worker.result
                    if result.get("success"):
                        activity = self.screen.query_one(ActivityLog)
                        activity.log_success("Appium server started")
                    self._handle_connection_result(result)

        elif worker.name == "connect_device":
            if is_finished:
                if is_failed:
                    self._connecting = False
                    self._handle_worker_error("connect_device", getattr(worker, "error", None))
                elif worker.result is None:
                    self._connecting = False
                    self._handle_worker_error("connect_device", "No result returned")
                else:
                    self._handle_connection_result(worker.result)

        elif worker.name == "wireless_connect":
            if is_finished:
                if is_failed:
                    self._wireless_connecting = False
                    self._handle_worker_error("wireless_connect", getattr(worker, "error", None))
                    try:
                        self.query_one("#btn-wireless-connect", Button).disabled = False
                    except Exception:
                        pass
                elif worker.result is None:
                    self._wireless_connecting = False
                    self._handle_worker_error("wireless_connect", "No result returned")
                    try:
                        self.query_one("#btn-wireless-connect", Button).disabled = False
                    except Exception:
                        pass
                else:
                    self._handle_wireless_pair_result(worker.result)

        elif worker.name == "wireless_finish_connect":
            if is_finished:
                if is_failed:
                    self._wireless_connecting = False
                    self._handle_worker_error(
                        "wireless_finish_connect", getattr(worker, "error", None)
                    )
                    try:
                        self.query_one("#btn-wireless-finish-connect", Button).disabled = False
                    except Exception:
                        pass
                elif worker.result is None:
                    self._wireless_connecting = False
                    self._handle_worker_error("wireless_finish_connect", "No result returned")
                    try:
                        self.query_one("#btn-wireless-finish-connect", Button).disabled = False
                    except Exception:
                        pass
                else:
                    self._handle_wireless_connect_result(worker.result)

        elif worker.name == "update_device_list":
            if is_finished:
                self._updating_device_list = False
                if is_failed:
                    self._handle_worker_error(
                        "update_device_list", getattr(worker, "error", None)
                    )

    # ------------------------------------------------------------------
    # Helpers: error handling
    # ------------------------------------------------------------------

    def _handle_worker_error(self, worker_name: str, error: Exception | str | None) -> None:
        """Centralised worker error handling."""
        activity = self.screen.query_one(ActivityLog)
        error_msg = str(error) if error else "Unknown error"
        activity.log_error(f"Worker '{worker_name}' failed: {error_msg}")

        status = self.query_one("#device-status", Static)
        if worker_name == "scan_devices":
            status.update(f"[red]Device scan failed: {error_msg}[/red]")
        elif worker_name == "start_appium":
            status.update(f"[red]Appium startup failed: {error_msg}[/red]")
            self.query_one("#btn-refresh", Button).disabled = False
            self.query_one("#btn-connect", Button).disabled = False
        elif worker_name == "connect_device":
            status.update(f"[red]Connection failed: {error_msg}[/red]")
            self.query_one("#btn-refresh", Button).disabled = False
            self.query_one("#btn-connect", Button).disabled = False
        elif worker_name == "wireless_connect":
            try:
                ws = self.query_one("#wireless-status", Static)
                ws.update(f"[red]{error_msg}[/red]")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Device list update
    # ------------------------------------------------------------------

    def _safe_update_device_list(self, devices: List[dict]) -> None:
        if self._updating_device_list:
            return
        self._updating_device_list = True
        self.run_worker(
            self._update_device_list(devices), name="update_device_list", exclusive=True
        )

    def _sanitize_device_id(self, device_id: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]", "_", device_id)
        if len(sanitized) > 40:
            id_hash = hashlib.md5(device_id.encode()).hexdigest()[:8]
            sanitized = f"{sanitized[:30]}_{id_hash}"
        return sanitized

    async def _update_device_list(self, devices: List[dict]) -> None:
        """Update the device list display safely (async)."""
        try:
            if devices is None:
                devices = []

            self._devices = devices
            activity = self.screen.query_one(ActivityLog)
            status = self.query_one("#device-status", Static)
            listview = self.query_one("#device-list", ListView)

            await listview.remove_children()

            if not devices:
                status.update(
                    "[yellow]No devices found. Connect your phone via USB "
                    "and enable USB debugging.[/yellow]"
                )
                if self._last_scan_had_devices is not False:
                    activity.log_warning("No devices found")
                self._last_scan_had_devices = False
                return

            self._last_scan_had_devices = True
            status.update(f"[green]Found {len(devices)} device(s)[/green]")
            activity.log_success(f"Found {len(devices)} device(s)")

            items = []
            seen_ids: set[str] = set()

            for idx, device in enumerate(devices):
                device_id = device.get("id") if isinstance(device, dict) else None
                if not device_id or not isinstance(device_id, str):
                    device_id = f"unknown-{idx}"

                model = (
                    device.get("model", "Unknown Device")
                    if isinstance(device, dict)
                    else "Unknown Device"
                )
                dev_status = (
                    device.get("status", "unknown") if isinstance(device, dict) else "unknown"
                )

                sanitized_id = self._sanitize_device_id(device_id)
                base_widget_id = f"device-{sanitized_id}"
                unique_widget_id = base_widget_id
                counter = 1
                while unique_widget_id in seen_ids:
                    unique_widget_id = f"{base_widget_id}-{counter}"
                    counter += 1
                seen_ids.add(unique_widget_id)

                if dev_status == "device":
                    style = "green"
                    status_text = "Ready"
                elif dev_status == "unauthorized":
                    style = "yellow"
                    status_text = "Unauthorized - accept prompt on phone"
                else:
                    style = "red"
                    status_text = dev_status

                label = f"[{style}]{model}[/{style}] ({device_id}) - {status_text}"
                items.append(ListItem(Label(label), id=unique_widget_id, name=device_id))

            if items:
                await listview.mount(*items)
                listview.index = 0
                self._selected_device = devices[0]["id"]
                connect_btn = self.query_one("#btn-connect", Button)
                connect_btn.disabled = False
                activity.log("Press Enter to connect or select a different device")
        finally:
            self._updating_device_list = False

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle device selection -- Enter key on ListView triggers this."""
        if event.item and hasattr(event.item, "name"):
            self._selected_device = event.item.name
            self.action_connect_device()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh_devices(self) -> None:
        """Refresh the device list."""
        activity = self.screen.query_one(ActivityLog)
        activity.log("Refreshing device list...")

        status = self.query_one("#device-status", Static)
        status.update("[yellow]Scanning...[/yellow]")

        self._last_scan_had_devices = None
        self.run_worker(self._scan_devices(), name="scan_devices")

    def action_connect_device(self) -> None:
        """Connect to the selected device."""
        if self._connecting:
            return

        if not self._selected_device:
            listview = self.query_one("#device-list", ListView)
            if listview.index is not None and self._devices:
                idx = listview.index
                if 0 <= idx < len(self._devices):
                    self._selected_device = self._devices[idx]["id"]

        if not self._selected_device:
            return

        self._connecting = True
        activity = self.screen.query_one(ActivityLog)
        status = self.query_one("#device-status", Static)

        refresh_btn = self.query_one("#btn-refresh", Button)
        connect_btn = self.query_one("#btn-connect", Button)
        refresh_btn.disabled = True
        connect_btn.disabled = True

        device_info = next(
            (d for d in self._devices if d["id"] == self._selected_device), None
        )
        device_name = (
            device_info.get("model", self._selected_device) if device_info else self._selected_device
        )

        if not self._appium_started:
            activity.log_info("Starting Appium server...")
            activity.log_info(f"Connecting to {device_name}...")
            status.update(f"[yellow]Starting Appium server for {device_name}...[/yellow]")
            self.run_worker(
                self._start_appium_and_connect(self._selected_device),
                name="start_appium",
            )
        else:
            activity.log_info(f"Connecting to {device_name}...")
            status.update(f"[yellow]Connecting to {device_name}...[/yellow]")
            self.run_worker(
                self._connect_to_device(self._selected_device),
                name="connect_device",
            )

    def action_use_dry_run(self) -> None:
        """Use dry run mode with a mock driver (emits Connected with None)."""
        activity = self.screen.query_one(ActivityLog)
        activity.log_warning("Using DRY RUN mode with mock data")

        status = self.query_one("#device-status", Static)
        status.update("[yellow]DRY RUN MODE - Using mock data[/yellow]")

        activity.log_success("Dry-run connected")

        # Emit Connected with no real driver
        self.post_message(self.Connected(driver=None))

    # ------------------------------------------------------------------
    # Workers: Appium + device connection
    # ------------------------------------------------------------------

    async def _start_appium_and_connect(self, device_id: str) -> dict:
        """Start Appium server then connect to *device_id*."""
        try:
            from ...utils.logger import Logger

            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode)

            appium_manager = AppiumManager(logger)
            started = await asyncio.to_thread(appium_manager.start_appium)

            if not started:
                return {"success": False, "error": "Failed to start Appium server"}

            self.app._appium_manager = appium_manager
            self._appium_started = True

            return await self._connect_to_device(device_id)
        except Exception as e:
            return {"success": False, "error": f"Appium startup failed: {str(e)}"}

    async def _connect_to_device(self, device_id: str) -> dict:
        """Create a WhatsAppDriver and connect to *device_id*."""
        try:
            from ...export.whatsapp_driver import WhatsAppDriver
            from ...utils.logger import Logger

            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode)

            driver = WhatsAppDriver(logger=logger, device_id=device_id)
            await asyncio.to_thread(driver.connect)

            return {"success": True, "driver": driver}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_connection_result(self, result: dict) -> None:
        """Handle connection attempt result and emit Connected on success."""
        self._connecting = False
        activity = self.screen.query_one(ActivityLog)
        status = self.query_one("#device-status", Static)
        refresh_btn = self.query_one("#btn-refresh", Button)
        connect_btn = self.query_one("#btn-connect", Button)

        if result.get("success"):
            driver = result["driver"]
            activity.log_success("Connected to device")
            status.update("[green]Connected![/green]")

            # Emit Connected so MainScreen can advance the workflow
            self.post_message(self.Connected(driver=driver))
        else:
            error = result.get("error", "Unknown error")
            activity.log_error(f"Connection failed: {error}")
            status.update(f"[red]Connection failed: {error}[/red]")
            refresh_btn.disabled = False
            connect_btn.disabled = False

    # ------------------------------------------------------------------
    # Workers: wireless ADB
    # ------------------------------------------------------------------

    def _start_wireless_connect(self) -> None:
        """Initiate wireless ADB pairing."""
        if self._wireless_connecting or self._connecting:
            return

        ip_port_input = self.query_one("#wireless-ip-port", Input)
        pairing_code_input = self.query_one("#wireless-pairing-code", Input)
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.screen.query_one(ActivityLog)

        ip_port = ip_port_input.value.strip()
        pairing_code = pairing_code_input.value.strip()

        if not ip_port:
            wireless_status.update("[red]Enter the IP:Port from the pairing dialog[/red]")
            return
        if not pairing_code:
            wireless_status.update("[red]Enter the 6-digit pairing code[/red]")
            return
        if ":" not in ip_port:
            wireless_status.update(
                "[red]Invalid format. Use IP:PORT (e.g. 192.168.1.100:37453)[/red]"
            )
            return

        self._wireless_connecting = True
        self._wireless_pairing_ip = ip_port.split(":")[0]
        wireless_status.update("[yellow]Pairing...[/yellow]")
        activity.log_info(f"Wireless ADB: pairing with {ip_port}...")

        btn = self.query_one("#btn-wireless-connect", Button)
        btn.disabled = True

        self.run_worker(self._wireless_pair(ip_port, pairing_code), name="wireless_connect")

    async def _wireless_pair(self, ip_port: str, pairing_code: str) -> dict:
        """Pair with a device via wireless ADB (step 1)."""
        import subprocess

        try:
            pair_result = await asyncio.to_thread(
                subprocess.run,
                ["adb", "pair", ip_port, pairing_code],
                capture_output=True,
                text=True,
                timeout=15,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Pairing timed out. The code may have expired."}
        except FileNotFoundError:
            return {
                "success": False,
                "error": "adb not found. Install Android SDK platform-tools.",
            }
        except Exception as e:
            return {"success": False, "error": f"Pairing failed: {str(e)}"}

        pair_output = (pair_result.stdout + pair_result.stderr).strip()
        if (
            pair_result.returncode != 0
            or "Failed" in pair_output
            or "error" in pair_output.lower()
        ):
            return {
                "success": False,
                "error": f"Pairing failed: {pair_output}",
                "hint": "Pairing codes expire after a few minutes. Get a fresh code and try again.",
            }

        return {"success": True, "paired": True}

    async def _wireless_connect(self, ip: str, connect_port: str) -> dict:
        """Connect to a paired wireless ADB device (step 2)."""
        import subprocess

        connect_addr = f"{ip}:{connect_port}"
        try:
            connect_result = await asyncio.to_thread(
                subprocess.run,
                ["adb", "connect", connect_addr],
                capture_output=True,
                text=True,
                timeout=15,
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Connection to {connect_addr} timed out."}
        except Exception as e:
            return {"success": False, "error": f"Connection failed: {str(e)}"}

        connect_output = (connect_result.stdout + connect_result.stderr).strip()
        if "connected" in connect_output.lower() or "already connected" in connect_output.lower():
            return {
                "success": True,
                "device_id": connect_addr,
                "message": f"Connected to {connect_addr}",
            }

        return {"success": False, "error": f"Connection failed: {connect_output}"}

    def _handle_wireless_pair_result(self, result: dict) -> None:
        """Handle the result of wireless pairing (step 1)."""
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.screen.query_one(ActivityLog)

        if result.get("paired"):
            wireless_status.update(
                "[green]Paired![/green] Now enter the connect port from the main "
                "Wireless Debugging screen (not the pairing dialog)."
            )
            activity.log_success("Pairing successful")
            activity.log_info(
                "Enter the port shown on the main Wireless Debugging screen, then press Connect."
            )

            connect_section = self.query_one("#wireless-connect-section")
            connect_section.remove_class("hidden")

            connect_port_input = self.query_one("#wireless-connect-port", Input)
            connect_port_input.focus()

            self.query_one("#btn-wireless-connect", Button).disabled = False
        else:
            self._wireless_connecting = False
            error = result.get("error", "Unknown error")
            hint = result.get("hint", "")
            msg = f"[red]{error}[/red]"
            if hint:
                msg += f"\n[yellow]{hint}[/yellow]"
            wireless_status.update(msg)
            activity.log_error(f"Wireless ADB pairing failed: {error}")
            if hint:
                activity.log_warning(hint)
            self.query_one("#btn-wireless-connect", Button).disabled = False

    def _start_wireless_finish_connect(self) -> None:
        """Initiate the connect step after pairing succeeded."""
        connect_port_input = self.query_one("#wireless-connect-port", Input)
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.screen.query_one(ActivityLog)

        connect_port = connect_port_input.value.strip()
        if not connect_port:
            wireless_status.update(
                "[red]Enter the port from the main Wireless Debugging screen[/red]"
            )
            return
        if not connect_port.isdigit():
            wireless_status.update("[red]Port must be a number[/red]")
            return

        ip = getattr(self, "_wireless_pairing_ip", None)
        if not ip:
            wireless_status.update("[red]No pairing IP found. Please pair again.[/red]")
            return

        wireless_status.update(f"[yellow]Connecting to {ip}:{connect_port}...[/yellow]")
        activity.log_info(f"Wireless ADB: connecting to {ip}:{connect_port}...")

        btn = self.query_one("#btn-wireless-finish-connect", Button)
        btn.disabled = True

        self.run_worker(self._wireless_connect(ip, connect_port), name="wireless_finish_connect")

    def _handle_wireless_connect_result(self, result: dict) -> None:
        """Handle the result of wireless connection (step 2)."""
        self._wireless_connecting = False
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.screen.query_one(ActivityLog)

        if result.get("success"):
            device_id = result["device_id"]
            wireless_status.update(f"[green]Connected to {device_id}[/green]")
            activity.log_success(f"Wireless ADB connected: {device_id}")

            # Set selected device and proceed with Appium + WhatsApp connection
            self._selected_device = device_id
            self._connecting = True

            # Disable all connection buttons
            self.query_one("#btn-refresh", Button).disabled = True
            self.query_one("#btn-connect", Button).disabled = True
            self.query_one("#btn-wireless-connect", Button).disabled = True
            try:
                self.query_one("#btn-wireless-finish-connect", Button).disabled = True
            except Exception:
                pass

            status = self.query_one("#device-status", Static)

            if not self._appium_started:
                activity.log_info("Starting Appium server...")
                status.update(f"[yellow]Starting Appium server for {device_id}...[/yellow]")
                self.run_worker(
                    self._start_appium_and_connect(device_id), name="start_appium"
                )
            else:
                activity.log_info(f"Connecting to {device_id}...")
                status.update(f"[yellow]Connecting to {device_id}...[/yellow]")
                self.run_worker(
                    self._connect_to_device(device_id), name="connect_device"
                )
        else:
            error = result.get("error", "Unknown error")
            wireless_status.update(f"[red]{error}[/red]")
            activity.log_error(f"Wireless ADB connect failed: {error}")
            try:
                self.query_one("#btn-wireless-finish-connect", Button).disabled = False
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Button dispatch
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses within this pane."""
        if event.button.id == "btn-refresh":
            self.action_refresh_devices()
        elif event.button.id == "btn-connect":
            self.action_connect_device()
        elif event.button.id == "btn-wireless-connect":
            self._start_wireless_connect()
        elif event.button.id == "btn-wireless-finish-connect":
            self._start_wireless_finish_connect()
