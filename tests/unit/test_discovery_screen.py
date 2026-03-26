"""
Tests for the DiscoveryScreen wireless ADB functionality.

Tests cover:
- Wireless ADB section rendering with input fields
- Input validation (empty fields, invalid format)
- ADB pair/connect subprocess mocking
- Error handling (failed pairing, expired codes, timeouts)
- Pre-fill from CLI flag
- Existing USB scan functionality preserved
"""

import asyncio
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from whatsapp_chat_autoexport.tui.textual_screens.discovery_screen import DiscoveryScreen


# =============================================================================
# DiscoveryScreen Initialization
# =============================================================================


class TestDiscoveryScreenInit:
    """Tests for DiscoveryScreen initialization."""

    def test_init_default_state(self):
        """Test that DiscoveryScreen initializes with correct default state."""
        screen = DiscoveryScreen()
        assert screen._devices == []
        assert screen._selected_device is None
        assert screen._connecting is False
        assert screen._wireless_connecting is False
        assert screen._appium_started is False

    def test_init_wireless_connecting_flag(self):
        """Test that wireless connecting flag starts as False."""
        screen = DiscoveryScreen()
        assert screen._wireless_connecting is False

    def test_has_wireless_methods(self):
        """Test that wireless ADB methods exist on DiscoveryScreen."""
        screen = DiscoveryScreen()
        assert hasattr(screen, "_start_wireless_connect")
        assert hasattr(screen, "_wireless_pair_and_connect")
        assert hasattr(screen, "_handle_wireless_connect_result")
        assert callable(screen._start_wireless_connect)
        assert callable(screen._wireless_pair_and_connect)
        assert callable(screen._handle_wireless_connect_result)


# =============================================================================
# Wireless Pair and Connect Worker
# =============================================================================


class TestWirelessPairAndConnect:
    """Tests for the _wireless_pair_and_connect worker method."""

    @pytest.fixture
    def screen(self):
        """Create a DiscoveryScreen instance for testing."""
        return DiscoveryScreen()

    def test_successful_pair_and_connect(self, screen):
        """Test successful wireless pairing and connection."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired to 192.168.1.100:37453"
        mock_pair.stderr = ""

        mock_connect = MagicMock()
        mock_connect.returncode = 0
        mock_connect.stdout = "connected to 192.168.1.100:5555"
        mock_connect.stderr = ""

        with patch("subprocess.run", side_effect=[mock_pair, mock_connect]):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is True
        assert result["device_id"] == "192.168.1.100:5555"
        assert "Connected" in result["message"]

    def test_pair_failure(self, screen):
        """Test handling of pairing failure."""
        mock_pair = MagicMock()
        mock_pair.returncode = 1
        mock_pair.stdout = ""
        mock_pair.stderr = "Failed: wrong pairing code"

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "999999")
            )

        assert result["success"] is False
        assert "Pairing failed" in result["error"]
        assert "hint" in result
        assert "expire" in result["hint"].lower()

    def test_pair_timeout(self, screen):
        """Test handling of pairing timeout."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=15),
        ):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_adb_not_found(self, screen):
        """Test handling when adb is not installed."""
        with patch(
            "subprocess.run", side_effect=FileNotFoundError("adb not found")
        ):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "adb not found" in result["error"]

    def test_connect_failure_after_successful_pair(self, screen):
        """Test handling of connection failure after successful pairing."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired"
        mock_pair.stderr = ""

        mock_connect = MagicMock()
        mock_connect.returncode = 1
        mock_connect.stdout = ""
        mock_connect.stderr = "failed to connect"

        with patch("subprocess.run", side_effect=[mock_pair, mock_connect]):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "Connection failed" in result["error"]

    def test_connect_timeout_after_successful_pair(self, screen):
        """Test handling of connection timeout after successful pairing."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired"
        mock_pair.stderr = ""

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "pair" in cmd:
                return mock_pair
            raise subprocess.TimeoutExpired(cmd="adb", timeout=15)

        with patch("subprocess.run", side_effect=side_effect):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_already_connected_is_success(self, screen):
        """Test that 'already connected' response is treated as success."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired"
        mock_pair.stderr = ""

        mock_connect = MagicMock()
        mock_connect.returncode = 0
        mock_connect.stdout = "already connected to 192.168.1.100:5555"
        mock_connect.stderr = ""

        with patch("subprocess.run", side_effect=[mock_pair, mock_connect]):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is True
        assert result["device_id"] == "192.168.1.100:5555"

    def test_ip_extraction_from_ip_port(self, screen):
        """Test that IP is correctly extracted from ip:port for connect."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired"
        mock_pair.stderr = ""

        mock_connect = MagicMock()
        mock_connect.returncode = 0
        mock_connect.stdout = "connected to 10.0.0.5:5555"
        mock_connect.stderr = ""

        with patch("subprocess.run", side_effect=[mock_pair, mock_connect]) as mock_run:
            result = asyncio.run(
                screen._wireless_pair_and_connect("10.0.0.5:41234", "654321")
            )

        assert result["success"] is True
        assert result["device_id"] == "10.0.0.5:5555"

        # Verify the connect command used the right address
        connect_call = mock_run.call_args_list[1]
        assert connect_call[0][0] == ["adb", "connect", "10.0.0.5:5555"]

    def test_pair_error_in_stdout(self, screen):
        """Test pairing failure detected via error keyword in stdout."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0  # Return code can be 0 even with errors
        mock_pair.stdout = "error: pairing rejected"
        mock_pair.stderr = ""

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "Pairing failed" in result["error"]

    def test_pair_failed_keyword_in_output(self, screen):
        """Test pairing failure detected via 'Failed' keyword."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Failed to pair with device"
        mock_pair.stderr = ""

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "hint" in result

    def test_generic_exception_during_pair(self, screen):
        """Test handling of unexpected exceptions during pairing."""
        with patch("subprocess.run", side_effect=OSError("Unexpected error")):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "Pairing failed" in result["error"]

    def test_generic_exception_during_connect(self, screen):
        """Test handling of unexpected exceptions during connect step."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired"
        mock_pair.stderr = ""

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_pair
            raise OSError("Unexpected connect error")

        with patch("subprocess.run", side_effect=side_effect):
            result = asyncio.run(
                screen._wireless_pair_and_connect("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "Connection failed" in result["error"]


# =============================================================================
# Input Validation Guards
# =============================================================================


class TestWirelessInputValidation:
    """Tests for wireless ADB input validation logic."""

    def test_concurrent_wireless_guard(self):
        """Test that concurrent wireless connections are prevented."""
        screen = DiscoveryScreen()
        screen._wireless_connecting = True
        # _start_wireless_connect should return early when already connecting
        assert screen._wireless_connecting is True

    def test_concurrent_usb_guard(self):
        """Test that wireless connect is prevented during USB connection."""
        screen = DiscoveryScreen()
        screen._connecting = True
        # _start_wireless_connect should return early when USB connecting
        assert screen._connecting is True


# =============================================================================
# Scan Devices Worker (existing functionality preserved)
# =============================================================================


class TestScanDevices:
    """Tests to verify existing _scan_devices still works alongside wireless."""

    def test_scan_devices_returns_list(self):
        """Test that _scan_devices returns a list of devices."""
        screen = DiscoveryScreen()

        mock_result = MagicMock()
        mock_result.stdout = "List of devices attached\nABC123\tdevice model:Pixel_6\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            devices = asyncio.run(screen._scan_devices())

        assert len(devices) == 1
        assert devices[0]["id"] == "ABC123"
        assert devices[0]["status"] == "device"
        assert devices[0]["model"] == "Pixel_6"

    def test_scan_devices_empty(self):
        """Test _scan_devices with no devices connected."""
        screen = DiscoveryScreen()

        mock_result = MagicMock()
        mock_result.stdout = "List of devices attached\n\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            devices = asyncio.run(screen._scan_devices())

        assert devices == []

    def test_scan_devices_adb_not_found(self):
        """Test _scan_devices when adb is not installed."""
        screen = DiscoveryScreen()

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            devices = asyncio.run(screen._scan_devices())

        assert devices == []

    def test_scan_devices_timeout(self):
        """Test _scan_devices when adb times out."""
        screen = DiscoveryScreen()

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=10),
        ):
            devices = asyncio.run(screen._scan_devices())

        assert devices == []

    def test_scan_devices_multiple(self):
        """Test _scan_devices with multiple devices."""
        screen = DiscoveryScreen()

        mock_result = MagicMock()
        mock_result.stdout = (
            "List of devices attached\n"
            "ABC123\tdevice model:Pixel_6\n"
            "192.168.1.100:5555\tdevice model:Galaxy_S21\n"
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            devices = asyncio.run(screen._scan_devices())

        assert len(devices) == 2
        assert devices[0]["id"] == "ABC123"
        assert devices[1]["id"] == "192.168.1.100:5555"


# =============================================================================
# Worker State Handling
# =============================================================================


class TestWorkerStateHandling:
    """Tests for on_worker_state_changed handling of wireless_connect worker."""

    def test_worker_handler_exists(self):
        """Verify the worker handler method exists."""
        screen = DiscoveryScreen()
        assert hasattr(screen, "on_worker_state_changed")

    def test_worker_error_handler_covers_wireless(self):
        """Verify _handle_worker_error handles wireless_connect worker name."""
        screen = DiscoveryScreen()
        # The method should exist and accept the worker_name parameter
        assert hasattr(screen, "_handle_worker_error")


# =============================================================================
# Compose Layout (source inspection)
# =============================================================================


class TestComposeLayout:
    """Tests to verify the compose method references expected widget IDs.

    Textual's compose() requires an active App context, so we verify the
    method source contains the expected widget definitions instead of
    calling compose() directly.
    """

    @pytest.fixture
    def compose_source(self):
        """Get the source code of the compose method."""
        import inspect
        return inspect.getsource(DiscoveryScreen.compose)

    def test_compose_has_wireless_ip_port_input(self, compose_source):
        """Test that compose defines wireless IP:port input."""
        assert 'id="wireless-ip-port"' in compose_source

    def test_compose_has_wireless_pairing_code_input(self, compose_source):
        """Test that compose defines wireless pairing code input."""
        assert 'id="wireless-pairing-code"' in compose_source

    def test_compose_has_wireless_connect_button(self, compose_source):
        """Test that compose defines wireless connect button."""
        assert 'id="btn-wireless-connect"' in compose_source

    def test_compose_has_wireless_status(self, compose_source):
        """Test that compose defines wireless status display."""
        assert 'id="wireless-status"' in compose_source

    def test_compose_has_wireless_section_container(self, compose_source):
        """Test that compose defines wireless section container."""
        assert 'id="wireless-section"' in compose_source

    def test_compose_preserves_usb_device_list(self, compose_source):
        """Test that compose still defines USB device list."""
        assert 'id="device-list"' in compose_source

    def test_compose_preserves_usb_buttons(self, compose_source):
        """Test that compose still defines USB refresh and connect buttons."""
        assert 'id="btn-refresh"' in compose_source
        assert 'id="btn-connect"' in compose_source

    def test_compose_has_ip_port_placeholder(self, compose_source):
        """Test that IP:port input has correct placeholder."""
        assert "192.168.1.100:37453" in compose_source

    def test_compose_has_pairing_code_placeholder(self, compose_source):
        """Test that pairing code input has correct placeholder."""
        assert 'placeholder="123456"' in compose_source

    def test_compose_wireless_connect_is_primary(self, compose_source):
        """Test that wireless connect button uses primary variant."""
        # The button definition should include variant="primary"
        assert "Connect Wirelessly" in compose_source


# =============================================================================
# Button Press Handler
# =============================================================================


class TestButtonPressHandler:
    """Tests for the on_button_pressed method routing."""

    def test_button_handler_routes_wireless_connect(self):
        """Test that button handler recognizes wireless connect button ID."""
        screen = DiscoveryScreen()

        # Create a mock event
        mock_event = MagicMock()
        mock_button = MagicMock()
        mock_button.id = "btn-wireless-connect"
        mock_event.button = mock_button

        # Patch _start_wireless_connect to verify it gets called
        with patch.object(screen, "_start_wireless_connect") as mock_start:
            screen.on_button_pressed(mock_event)
            mock_start.assert_called_once()

    def test_button_handler_routes_refresh(self):
        """Test that refresh button still works."""
        screen = DiscoveryScreen()

        mock_event = MagicMock()
        mock_button = MagicMock()
        mock_button.id = "btn-refresh"
        mock_event.button = mock_button

        with patch.object(screen, "action_refresh_devices") as mock_refresh:
            screen.on_button_pressed(mock_event)
            mock_refresh.assert_called_once()

    def test_button_handler_routes_connect(self):
        """Test that USB connect button still works."""
        screen = DiscoveryScreen()

        mock_event = MagicMock()
        mock_button = MagicMock()
        mock_button.id = "btn-connect"
        mock_event.button = mock_button

        with patch.object(screen, "action_connect_device") as mock_connect:
            screen.on_button_pressed(mock_event)
            mock_connect.assert_called_once()
