"""
Discovery screen for device connection and chat scanning.

This is the first screen in the pipeline:
1. Scan for available Android devices
2. Connect to selected device
3. Launch WhatsApp and collect chat list
4. Transition to Selection screen
"""

import asyncio
import hashlib
import re
from typing import List, Optional

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, Button, ListView, ListItem, Label, Input, Rule
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.worker import Worker, WorkerState, get_current_worker

from ..textual_widgets.pipeline_header import PipelineHeader
from ..textual_widgets.activity_log import ActivityLog
from ..textual_app import PipelineStage

# Import AppiumManager for server lifecycle management
from ...export.appium_manager import AppiumManager
from ...export.models import ChatMetadata


class DiscoveryScreen(Screen):
    """
    Discovery screen for connecting to device and scanning chats.

    Flow:
    1. Scan for devices (automatic on mount)
    2. User selects device
    3. Connect and collect chats
    4. Transition to Selection screen
    """

    BINDINGS = [
        Binding("r", "refresh_devices", "Refresh", show=True),
        Binding("enter", "connect_device", "Connect", show=True),
        Binding("d", "use_dry_run", "Dry Run", show=False),
        Binding("c", "continue", "Continue", show=False),
        Binding("f", "refresh_chats", "Re-scan Chats", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        """Initialize the discovery screen."""
        super().__init__(**kwargs)
        self._devices: List[dict] = []
        self._selected_device: Optional[str] = None
        self._connecting = False
        self._scanning_chats = False
        self._updating_device_list = False  # Guard against concurrent list updates
        self._last_scan_had_devices: Optional[bool] = None  # Dedup "No devices found" warnings
        self._wireless_connecting = False  # Guard against concurrent wireless connect

        # Appium server management (managed at app level for persistence)
        self._appium_started = False

        # Discovery inventory state
        self._discovered_chats: List[ChatMetadata] = []
        self._discovery_generation: int = 0
        self._connected_driver = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield PipelineHeader()
        with Container(classes="content"):
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

            # Discovery inventory section (hidden until connected)
            with Vertical(id="discovery-section", classes="hidden"):
                yield Rule(line_style="heavy")
                yield Static(
                    "[bold]Discovered Chats[/bold]",
                    classes="discovery-title",
                )
                yield Static(
                    "Discovered 0 chats",
                    id="discovery-count",
                )
                yield ListView(id="discovery-inventory")
                with Horizontal(id="discovery-buttons"):
                    yield Button(
                        "Refresh Chats",
                        id="btn-refresh-chats",
                        variant="default",
                        disabled=True,
                    )
                    yield Button(
                        "Continue",
                        id="btn-continue",
                        variant="primary",
                        disabled=True,
                    )

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
                yield Static(
                    "",
                    id="wireless-status",
                )
        yield ActivityLog(id="activity-log")

    async def on_mount(self) -> None:
        """Start device scanning when mounted."""
        # Set the pipeline header stage
        header = self.query_one(PipelineHeader)
        header.set_stage(PipelineStage.CONNECT)

        # Log startup
        activity = self.query_one(ActivityLog)
        activity.log_info("WhatsApp Exporter starting...")
        activity.log("Scanning for Android devices...")

        # Start device scan
        self.run_worker(self._scan_devices(), name="scan_devices")

        # Pre-fill wireless ADB fields if CLI flag was passed
        wireless_adb = getattr(self.app, "wireless_adb", None)
        if wireless_adb:
            ip_port_input = self.query_one("#wireless-ip-port", Input)
            if isinstance(wireless_adb, str) and wireless_adb not in ("True", "true"):
                ip_port_input.value = wireless_adb

    async def _scan_devices(self) -> List[dict]:
        """
        Scan for connected Android devices.

        Returns:
            List of device dictionaries with id, status, and model
        """
        import subprocess

        devices = []

        try:
            # Run adb devices
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
                close_fds=True,  # Prevent fd inheritance issues in threaded contexts
            )

            lines = result.stdout.strip().split("\n")[1:]  # Skip header

            for line in lines:
                if not line.strip():
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    # Extract model if available
                    model = "Unknown"
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split(":")[1]
                            break

                    devices.append({
                        "id": device_id,
                        "status": status,
                        "model": model,
                    })

        except subprocess.TimeoutExpired:
            pass
        except FileNotFoundError:
            # ADB not installed
            pass
        except Exception:
            pass

        return devices

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes with proper error handling."""
        worker = event.worker
        state = worker.state

        # Check if worker is in a terminal state
        is_finished = state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)
        is_failed = state == WorkerState.ERROR

        if worker.name == "scan_devices":
            if is_finished:
                if is_failed:
                    self._handle_worker_error("scan_devices", getattr(worker, 'error', None))
                elif worker.result is None:
                    self._handle_worker_error("scan_devices", "No result returned")
                else:
                    # Schedule async update safely
                    self.call_later(self._safe_update_device_list, worker.result)
        elif worker.name == "start_appium":
            if is_finished:
                if is_failed:
                    self._connecting = False
                    self._handle_worker_error("start_appium", getattr(worker, 'error', None))
                elif worker.result is None:
                    self._connecting = False
                    self._handle_worker_error("start_appium", "No result returned")
                else:
                    result = worker.result
                    # Log Appium startup success if we got here
                    if result.get("success"):
                        activity = self.query_one(ActivityLog)
                        activity.log_success("Appium server started")
                    self._handle_connection_result(result)
        elif worker.name == "connect_device":
            if is_finished:
                if is_failed:
                    self._connecting = False
                    self._handle_worker_error("connect_device", getattr(worker, 'error', None))
                elif worker.result is None:
                    self._connecting = False
                    self._handle_worker_error("connect_device", "No result returned")
                else:
                    result = worker.result
                    self._handle_connection_result(result)
        elif worker.name == "collect_chats":
            if is_finished:
                if is_failed:
                    self._scanning_chats = False
                    self._handle_worker_error("collect_chats", getattr(worker, 'error', None))
                elif worker.result is None:
                    self._scanning_chats = False
                    self._handle_worker_error("collect_chats", "No result returned")
                else:
                    chats = worker.result
                    self._handle_chat_collection(chats)
        elif worker.name == "wireless_connect":
            if is_finished:
                if is_failed:
                    self._wireless_connecting = False
                    self._handle_worker_error("wireless_connect", getattr(worker, 'error', None))
                    # Re-enable wireless button on error
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
                    self._handle_wireless_connect_result(worker.result)
        elif worker.name == "update_device_list":
            # Async update worker finished
            if is_finished:
                self._updating_device_list = False
                if is_failed:
                    self._handle_worker_error("update_device_list", getattr(worker, 'error', None))

    def _handle_worker_error(self, worker_name: str, error: Exception | str | None) -> None:
        """Centralized worker error handling."""
        activity = self.query_one(ActivityLog)
        error_msg = str(error) if error else "Unknown error"
        activity.log_error(f"Worker '{worker_name}' failed: {error_msg}")

        # Update status based on which worker failed
        status = self.query_one("#device-status", Static)
        if worker_name == "scan_devices":
            status.update(f"[red]Device scan failed: {error_msg}[/red]")
        elif worker_name == "start_appium":
            status.update(f"[red]Appium startup failed: {error_msg}[/red]")
            # Re-enable buttons for retry
            self.query_one("#btn-refresh", Button).disabled = False
            self.query_one("#btn-connect", Button).disabled = False
        elif worker_name == "connect_device":
            status.update(f"[red]Connection failed: {error_msg}[/red]")
            # Re-enable buttons for retry
            self.query_one("#btn-refresh", Button).disabled = False
            self.query_one("#btn-connect", Button).disabled = False
        elif worker_name == "wireless_connect":
            try:
                ws = self.query_one("#wireless-status", Static)
                ws.update(f"[red]{error_msg}[/red]")
            except Exception:
                pass
        elif worker_name == "collect_chats":
            status.update(f"[red]Chat collection failed: {error_msg}[/red]")

    def _safe_update_device_list(self, devices: List[dict]) -> None:
        """Schedule the async device list update safely."""
        # Guard against concurrent updates
        if self._updating_device_list:
            return
        self._updating_device_list = True
        self.run_worker(self._update_device_list(devices), name="update_device_list", exclusive=True)

    def _sanitize_device_id(self, device_id: str) -> str:
        """Sanitize device ID for use as widget ID."""
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', device_id)
        # If ID is too long, use hash suffix for uniqueness
        if len(sanitized) > 40:
            id_hash = hashlib.md5(device_id.encode()).hexdigest()[:8]
            sanitized = f"{sanitized[:30]}_{id_hash}"
        return sanitized

    async def _update_device_list(self, devices: List[dict]) -> None:
        """Update the device list display safely (async)."""
        try:
            # Handle None or invalid devices
            if devices is None:
                devices = []

            self._devices = devices
            activity = self.query_one(ActivityLog)
            status = self.query_one("#device-status", Static)
            listview = self.query_one("#device-list", ListView)

            # Await removal of existing children to ensure DOM is updated
            await listview.remove_children()

            if not devices:
                status.update("[yellow]No devices found. Connect your phone via USB and enable USB debugging.[/yellow]")
                # Only log warning on first occurrence or when transitioning from found → not-found
                if self._last_scan_had_devices is not False:
                    activity.log_warning("No devices found")
                self._last_scan_had_devices = False
                return

            self._last_scan_had_devices = True
            status.update(f"[green]Found {len(devices)} device(s)[/green]")
            activity.log_success(f"Found {len(devices)} device(s)")

            # Build all items first with unique IDs, then mount together
            items = []
            seen_ids = set()

            for idx, device in enumerate(devices):
                # Defensive access with defaults (Fix 6: Input validation)
                device_id = device.get("id") if isinstance(device, dict) else None
                if not device_id or not isinstance(device_id, str):
                    device_id = f"unknown-{idx}"

                model = device.get("model", "Unknown Device") if isinstance(device, dict) else "Unknown Device"
                dev_status = device.get("status", "unknown") if isinstance(device, dict) else "unknown"

                # Generate unique widget ID (Fix 5: ID collision prevention)
                sanitized_id = self._sanitize_device_id(device_id)
                base_widget_id = f"device-{sanitized_id}"
                unique_widget_id = base_widget_id
                counter = 1
                while unique_widget_id in seen_ids:
                    unique_widget_id = f"{base_widget_id}-{counter}"
                    counter += 1
                seen_ids.add(unique_widget_id)

                # Format status display
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

            # Mount all items at once (more efficient than individual appends)
            if items:
                await listview.mount(*items)
                # Auto-select first device for immediate Enter key connection
                listview.index = 0
                self._selected_device = devices[0]["id"]
                connect_btn = self.query_one("#btn-connect", Button)
                connect_btn.disabled = False
                activity.log("Press Enter to connect or select a different device")
        finally:
            self._updating_device_list = False

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle device selection - Enter key on ListView triggers this."""
        if event.item and hasattr(event.item, "name"):
            self._selected_device = event.item.name
            # Immediately trigger connection when Enter is pressed on a device
            self.action_connect_device()

    def action_refresh_devices(self) -> None:
        """Refresh the device list."""
        activity = self.query_one(ActivityLog)
        activity.log("Refreshing device list...")

        status = self.query_one("#device-status", Static)
        status.update("[yellow]Scanning...[/yellow]")

        # Reset dedup flag so a fresh scan can log "No devices found" again
        self._last_scan_had_devices = None

        self.run_worker(self._scan_devices(), name="scan_devices")

    def action_connect_device(self) -> None:
        """Connect to the selected device."""
        if self._connecting:
            return

        # If no device explicitly selected, use the highlighted item from ListView
        if not self._selected_device:
            listview = self.query_one("#device-list", ListView)
            if listview.index is not None and self._devices:
                idx = listview.index
                if 0 <= idx < len(self._devices):
                    self._selected_device = self._devices[idx]["id"]

        if not self._selected_device:
            return

        self._connecting = True
        activity = self.query_one(ActivityLog)
        status = self.query_one("#device-status", Static)

        # Disable both buttons during connection
        refresh_btn = self.query_one("#btn-refresh", Button)
        connect_btn = self.query_one("#btn-connect", Button)
        refresh_btn.disabled = True
        connect_btn.disabled = True

        # Get device info for friendly name
        device_info = next((d for d in self._devices if d["id"] == self._selected_device), None)
        device_name = device_info.get("model", self._selected_device) if device_info else self._selected_device

        # Start Appium if not already running
        if not self._appium_started:
            activity.log_info("Starting Appium server...")
            activity.log_info(f"🔌 Connecting to {device_name}...")
            status.update(f"[yellow]Starting Appium server for {device_name}...[/yellow]")

            self.run_worker(
                self._start_appium_and_connect(self._selected_device),
                name="start_appium",
            )
        else:
            # Appium already running, connect directly
            activity.log_info(f"🔌 Connecting to {device_name}...")
            status.update(f"[yellow]Connecting to {device_name}...[/yellow]")

            self.run_worker(
                self._connect_to_device(self._selected_device),
                name="connect_device",
            )

    async def _start_appium_and_connect(self, device_id: str) -> dict:
        """
        Start Appium server and then connect to device.

        Args:
            device_id: The device ID to connect to

        Returns:
            Dictionary with success status and driver or error
        """
        try:
            from ...utils.logger import Logger

            # Create logger for AppiumManager
            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode)

            # Create and start AppiumManager
            appium_manager = AppiumManager(logger)

            # Start Appium (runs in thread to avoid blocking)
            started = await asyncio.to_thread(appium_manager.start_appium)

            if not started:
                return {"success": False, "error": "Failed to start Appium server"}

            # Store reference in app for cleanup on quit
            self.app._appium_manager = appium_manager
            self._appium_started = True

            # Now connect to device
            return await self._connect_to_device(device_id)

        except Exception as e:
            return {"success": False, "error": f"Appium startup failed: {str(e)}"}

    async def _connect_to_device(self, device_id: str) -> dict:
        """
        Connect to a device and initialize WhatsApp driver.

        Args:
            device_id: The device ID to connect to

        Returns:
            Dictionary with success status and driver or error
        """
        try:
            from ...export.whatsapp_driver import WhatsAppDriver
            from ...utils.logger import Logger

            # Create logger with debug mode from app settings
            debug_mode = getattr(self.app, "debug_mode", False)
            logger = Logger(debug=debug_mode)

            # Create and connect driver
            driver = WhatsAppDriver(
                logger=logger,
                device_id=device_id,
            )

            # Connect to WhatsApp
            await asyncio.to_thread(driver.connect)

            return {"success": True, "driver": driver}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_connection_result(self, result: dict) -> None:
        """Handle connection attempt result."""
        self._connecting = False
        activity = self.query_one(ActivityLog)
        status = self.query_one("#device-status", Static)
        refresh_btn = self.query_one("#btn-refresh", Button)
        connect_btn = self.query_one("#btn-connect", Button)

        if result.get("success"):
            driver = result["driver"]
            self._connected_driver = driver

            # Clear stage transition messaging
            activity.log_success("✓ Connected to device")
            activity.log("")  # Visual separator
            activity.log_info("📋 Stage: Discovering chats...")
            activity.log("Scanning WhatsApp for available chats...")

            status.update("[green]Connected! Discovering chats...[/green]")

            # Switch to DISCOVERY stage when chat scanning starts
            header = self.query_one(PipelineHeader)
            header.set_stage(PipelineStage.DISCOVER)

            # Show the discovery section
            discovery_section = self.query_one("#discovery-section")
            discovery_section.remove_class("hidden")

            # Start chat collection
            self._scanning_chats = True
            self.run_worker(
                self._collect_chats(driver),
                name="collect_chats",
            )
        else:
            error = result.get("error", "Unknown error")
            activity.log_error(f"Connection failed: {error}")
            status.update(f"[red]Connection failed: {error}[/red]")

            # Re-enable buttons on failure for retry
            refresh_btn.disabled = False
            connect_btn.disabled = False

    async def _collect_chats(self, driver) -> dict:
        """
        Collect chat list from WhatsApp.

        Args:
            driver: Connected WhatsApp driver

        Returns:
            Dictionary with chats list and driver
        """
        try:
            # Get limit from app settings
            limit = getattr(self.app, "limit", None)

            # Capture generation by value to detect stale callbacks
            gen = self._discovery_generation

            def on_found(metadata: ChatMetadata) -> None:
                self.call_from_thread(self._add_discovered_chat, metadata, gen)

            # Collect chats (with optional limit and live callback)
            chats = await asyncio.to_thread(
                driver.collect_all_chats, limit, False, on_found
            )
            return {"success": True, "chats": chats, "driver": driver}

        except Exception as e:
            return {"success": False, "error": str(e), "driver": driver}

    def _handle_chat_collection(self, result: dict) -> None:
        """Handle chat collection result."""
        self._scanning_chats = False
        activity = self.query_one(ActivityLog)
        status = self.query_one("#device-status", Static)

        driver = result.get("driver")

        # Always enable refresh button after collection
        try:
            self.query_one("#btn-refresh-chats", Button).disabled = False
        except Exception:
            pass

        if result.get("success"):
            chats = result["chats"]

            # Sync the authoritative list from the driver result
            self._discovered_chats = list(chats)

            activity.log_success(f"Found {len(chats)} chats")

            if len(chats) == 0:
                status.update("[yellow]No chats found. Try Refresh Chats to re-scan.[/yellow]")
                activity.log_warning("No chats found in WhatsApp")
            else:
                status.update(
                    f"[green]Found {len(chats)} chats. "
                    f"Press Continue to proceed to selection.[/green]"
                )
                # Enable Continue button
                try:
                    self.query_one("#btn-continue", Button).disabled = False
                except Exception:
                    pass
        else:
            error = result.get("error", "Unknown error")
            activity.log_error(f"Chat collection failed: {error}")
            status.update(f"[red]Failed to collect chats: {error}[/red]")

    def action_use_dry_run(self) -> None:
        """Use dry run mode with mock data."""
        activity = self.query_one(ActivityLog)
        activity.log_warning("Using DRY RUN mode with mock data")

        # Mock chats for testing using ChatMetadata
        mock_names = [
            "John Doe",
            "Family Group",
            "Work Chat",
            "Best Friend",
            "Mom",
            "Gym Buddies",
            "Book Club",
            "Neighbors",
            "College Friends",
            "Team Project",
        ]
        mock_chats = [ChatMetadata(name=name) for name in mock_names]

        status = self.query_one("#device-status", Static)
        status.update("[yellow]DRY RUN MODE - Using mock data[/yellow]")

        # Set DISCOVERY stage (skip CONNECT in dry run)
        header = self.query_one(PipelineHeader)
        header.set_stage(PipelineStage.DISCOVER)

        # Populate the discovery inventory
        self._discovered_chats = mock_chats
        self._connected_driver = None  # No driver in dry run

        # Show discovery section and populate inventory
        discovery_section = self.query_one("#discovery-section")
        discovery_section.remove_class("hidden")

        count_label = self.query_one("#discovery-count", Static)
        count_label.update(f"Discovered {len(mock_chats)} chats")

        inventory = self.query_one("#discovery-inventory", ListView)
        for chat in mock_chats:
            inventory.append(ListItem(Label(str(chat))))

        activity.log_success(f"Found {len(mock_chats)} chats (dry run)")

        # Enable Continue and Refresh buttons
        self.query_one("#btn-continue", Button).disabled = False
        self.query_one("#btn-refresh-chats", Button).disabled = False

    def _add_discovered_chat(self, metadata: ChatMetadata, generation: int) -> None:
        """Add a newly discovered chat to the inventory (called from thread via call_from_thread)."""
        # Ignore stale callbacks from a previous generation
        if generation != self._discovery_generation:
            return

        self._discovered_chats.append(metadata)

        # Update UI
        try:
            inventory = self.query_one("#discovery-inventory", ListView)
            inventory.append(ListItem(Label(str(metadata))))

            count_label = self.query_one("#discovery-count", Static)
            count_label.update(f"Discovered {len(self._discovered_chats)} chats")
        except Exception:
            pass

    def action_continue(self) -> None:
        """Transition to selection screen with discovered chats."""
        if self._scanning_chats:
            return
        if not self._discovered_chats:
            return

        self.app.call_later(
            self.app.transition_to_selection,
            self._connected_driver,
            self._discovered_chats,
        )

    def action_refresh_chats(self) -> None:
        """Clear inventory and re-run chat discovery."""
        # Guard: no-op if scanning or no driver
        if self._scanning_chats:
            return
        if self._connected_driver is None:
            return

        # Increment generation to invalidate in-flight callbacks
        self._discovery_generation += 1

        # Clear existing inventory
        self._discovered_chats.clear()
        try:
            inventory = self.query_one("#discovery-inventory", ListView)
            inventory.clear()

            count_label = self.query_one("#discovery-count", Static)
            count_label.update("Discovered 0 chats")

            # Disable buttons during scan
            self.query_one("#btn-continue", Button).disabled = True
            self.query_one("#btn-refresh-chats", Button).disabled = True
        except Exception:
            pass

        activity = self.query_one(ActivityLog)
        activity.log_info("Re-scanning WhatsApp for chats...")

        status = self.query_one("#device-status", Static)
        status.update("[yellow]Re-scanning chats...[/yellow]")

        # Re-run discovery with exclusive=True to cancel any prior worker
        self._scanning_chats = True
        self.run_worker(
            self._collect_chats(self._connected_driver),
            name="collect_chats",
            exclusive=True,
        )

    def _start_wireless_connect(self) -> None:
        """Initiate wireless ADB pairing and connection."""
        if self._wireless_connecting or self._connecting:
            return

        ip_port_input = self.query_one("#wireless-ip-port", Input)
        pairing_code_input = self.query_one("#wireless-pairing-code", Input)
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.query_one(ActivityLog)

        ip_port = ip_port_input.value.strip()
        pairing_code = pairing_code_input.value.strip()

        if not ip_port:
            wireless_status.update("[red]Enter the IP:Port from the pairing dialog[/red]")
            return

        if not pairing_code:
            wireless_status.update("[red]Enter the 6-digit pairing code[/red]")
            return

        # Validate IP:port format
        if ":" not in ip_port:
            wireless_status.update("[red]Invalid format. Use IP:PORT (e.g. 192.168.1.100:37453)[/red]")
            return

        self._wireless_connecting = True
        wireless_status.update("[yellow]Pairing...[/yellow]")
        activity.log_info(f"Wireless ADB: pairing with {ip_port}...")

        # Disable connect button during operation
        btn = self.query_one("#btn-wireless-connect", Button)
        btn.disabled = True

        self.run_worker(
            self._wireless_pair_and_connect(ip_port, pairing_code),
            name="wireless_connect",
        )

    async def _wireless_pair_and_connect(self, ip_port: str, pairing_code: str) -> dict:
        """
        Pair and connect to a device via wireless ADB.

        Steps:
        1. adb pair <ip:port> <code>
        2. adb connect <ip>:5555

        Args:
            ip_port: IP:port string for pairing (e.g. "192.168.1.100:37453")
            pairing_code: 6-digit pairing code

        Returns:
            Dictionary with success status and device_id or error
        """
        import subprocess

        # Step 1: Pair
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
            return {"success": False, "error": "adb not found. Install Android SDK platform-tools."}
        except Exception as e:
            return {"success": False, "error": f"Pairing failed: {str(e)}"}

        # Check pair result
        pair_output = (pair_result.stdout + pair_result.stderr).strip()
        if pair_result.returncode != 0 or "Failed" in pair_output or "error" in pair_output.lower():
            return {
                "success": False,
                "error": f"Pairing failed: {pair_output}",
                "hint": "Pairing codes expire after a few minutes. Get a fresh code and try again.",
            }

        # Step 2: Extract IP and connect on standard port 5555
        ip = ip_port.split(":")[0]
        connect_addr = f"{ip}:5555"

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
            return {"success": False, "error": "Connection timed out after pairing succeeded."}
        except Exception as e:
            return {"success": False, "error": f"Connection failed after pairing: {str(e)}"}

        connect_output = (connect_result.stdout + connect_result.stderr).strip()
        if "connected" not in connect_output.lower() and "already connected" not in connect_output.lower():
            return {
                "success": False,
                "error": f"Connection failed: {connect_output}",
            }

        return {
            "success": True,
            "device_id": connect_addr,
            "message": f"Connected to {connect_addr}",
        }

    def _handle_wireless_connect_result(self, result: dict) -> None:
        """Handle the result of wireless pairing and connection."""
        self._wireless_connecting = False
        wireless_status = self.query_one("#wireless-status", Static)
        activity = self.query_one(ActivityLog)
        btn = self.query_one("#btn-wireless-connect", Button)
        btn.disabled = False

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
            btn.disabled = True

            status = self.query_one("#device-status", Static)

            if not self._appium_started:
                activity.log_info("Starting Appium server...")
                status.update(f"[yellow]Starting Appium server for {device_id}...[/yellow]")
                self.run_worker(
                    self._start_appium_and_connect(device_id),
                    name="start_appium",
                )
            else:
                activity.log_info(f"Connecting to {device_id}...")
                status.update(f"[yellow]Connecting to {device_id}...[/yellow]")
                self.run_worker(
                    self._connect_to_device(device_id),
                    name="connect_device",
                )
        else:
            error = result.get("error", "Unknown error")
            hint = result.get("hint", "")
            msg = f"[red]{error}[/red]"
            if hint:
                msg += f"\n[yellow]{hint}[/yellow]"
            wireless_status.update(msg)
            activity.log_error(f"Wireless ADB failed: {error}")
            if hint:
                activity.log_warning(hint)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-refresh":
            self.action_refresh_devices()
        elif event.button.id == "btn-connect":
            self.action_connect_device()
        elif event.button.id == "btn-wireless-connect":
            self._start_wireless_connect()
        elif event.button.id == "btn-continue":
            self.action_continue()
        elif event.button.id == "btn-refresh-chats":
            self.action_refresh_chats()
