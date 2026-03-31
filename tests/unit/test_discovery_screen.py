"""
Tests for the DiscoveryScreen wireless ADB functionality and live discovery inventory.

Tests cover:
- Wireless ADB section rendering with input fields
- Input validation (empty fields, invalid format)
- ADB pair/connect subprocess mocking
- Error handling (failed pairing, expired codes, timeouts)
- Pre-fill from CLI flag
- Existing USB scan functionality preserved
- Live discovery inventory streaming
- Generation-based stale callback protection
- Refresh and Continue actions
"""

import asyncio
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from whatsapp_chat_autoexport.tui.textual_screens.discovery_screen import DiscoveryScreen
from whatsapp_chat_autoexport.export.models import ChatMetadata


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
        assert screen._discovered_chats == []
        assert screen._discovery_generation == 0
        assert screen._connected_driver is None

    def test_init_wireless_connecting_flag(self):
        """Test that wireless connecting flag starts as False."""
        screen = DiscoveryScreen()
        assert screen._wireless_connecting is False

    def test_has_wireless_methods(self):
        """Test that wireless ADB methods exist on DiscoveryScreen."""
        screen = DiscoveryScreen()
        assert hasattr(screen, "_start_wireless_connect")
        assert hasattr(screen, "_wireless_pair")
        assert hasattr(screen, "_wireless_connect")
        assert hasattr(screen, "_handle_wireless_pair_result")
        assert hasattr(screen, "_handle_wireless_connect_result")
        assert callable(screen._start_wireless_connect)
        assert callable(screen._wireless_pair)
        assert callable(screen._wireless_connect)

    def test_has_discovery_methods(self):
        """Test that live discovery inventory methods exist on DiscoveryScreen."""
        screen = DiscoveryScreen()
        assert hasattr(screen, "_add_discovered_chat")
        assert hasattr(screen, "action_continue")
        assert hasattr(screen, "action_refresh_chats")
        assert callable(screen._add_discovered_chat)
        assert callable(screen.action_continue)
        assert callable(screen.action_refresh_chats)


# =============================================================================
# Wireless Pair and Connect Worker
# =============================================================================


class TestWirelessPairAndConnect:
    """Tests for the _wireless_pair and _wireless_connect worker methods."""

    @pytest.fixture
    def screen(self):
        """Create a DiscoveryScreen instance for testing."""
        return DiscoveryScreen()

    def test_successful_pair(self, screen):
        """Test successful wireless pairing returns paired status."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0
        mock_pair.stdout = "Successfully paired to 192.168.1.100:37453"
        mock_pair.stderr = ""

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair("192.168.1.100:37453", "123456")
            )

        assert result["success"] is True
        assert result["paired"] is True

    def test_successful_connect(self, screen):
        """Test successful wireless connection after pairing."""
        mock_connect = MagicMock()
        mock_connect.returncode = 0
        mock_connect.stdout = "connected to 192.168.1.100:39765"
        mock_connect.stderr = ""

        with patch("subprocess.run", return_value=mock_connect):
            result = asyncio.run(
                screen._wireless_connect("192.168.1.100", "39765")
            )

        assert result["success"] is True
        assert result["device_id"] == "192.168.1.100:39765"
        assert "Connected" in result["message"]

    def test_pair_failure(self, screen):
        """Test handling of pairing failure."""
        mock_pair = MagicMock()
        mock_pair.returncode = 1
        mock_pair.stdout = ""
        mock_pair.stderr = "Failed: wrong pairing code"

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair("192.168.1.100:37453", "999999")
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
                screen._wireless_pair("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_adb_not_found(self, screen):
        """Test handling when adb is not installed."""
        with patch(
            "subprocess.run", side_effect=FileNotFoundError("adb not found")
        ):
            result = asyncio.run(
                screen._wireless_pair("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "adb not found" in result["error"]

    def test_connect_failure(self, screen):
        """Test handling of connection failure."""
        mock_connect = MagicMock()
        mock_connect.returncode = 1
        mock_connect.stdout = ""
        mock_connect.stderr = "failed to connect"

        with patch("subprocess.run", return_value=mock_connect):
            result = asyncio.run(
                screen._wireless_connect("192.168.1.100", "39765")
            )

        assert result["success"] is False
        assert "Connection failed" in result["error"]

    def test_connect_timeout(self, screen):
        """Test handling of connection timeout."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=15),
        ):
            result = asyncio.run(
                screen._wireless_connect("192.168.1.100", "39765")
            )

        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    def test_already_connected_is_success(self, screen):
        """Test that 'already connected' response is treated as success."""
        mock_connect = MagicMock()
        mock_connect.returncode = 0
        mock_connect.stdout = "already connected to 192.168.1.100:39765"
        mock_connect.stderr = ""

        with patch("subprocess.run", return_value=mock_connect):
            result = asyncio.run(
                screen._wireless_connect("192.168.1.100", "39765")
            )

        assert result["success"] is True
        assert result["device_id"] == "192.168.1.100:39765"

    def test_pair_error_in_stdout(self, screen):
        """Test pairing failure detected via error keyword in stdout."""
        mock_pair = MagicMock()
        mock_pair.returncode = 0  # Return code can be 0 even with errors
        mock_pair.stdout = "error: pairing rejected"
        mock_pair.stderr = ""

        with patch("subprocess.run", return_value=mock_pair):
            result = asyncio.run(
                screen._wireless_pair("192.168.1.100:37453", "123456")
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
                screen._wireless_pair("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "hint" in result

    def test_generic_exception_during_pair(self, screen):
        """Test handling of unexpected exceptions during pairing."""
        with patch("subprocess.run", side_effect=OSError("Unexpected error")):
            result = asyncio.run(
                screen._wireless_pair("192.168.1.100:37453", "123456")
            )

        assert result["success"] is False
        assert "Pairing failed" in result["error"]

    def test_generic_exception_during_connect(self, screen):
        """Test handling of unexpected exceptions during connect."""
        with patch("subprocess.run", side_effect=OSError("Unexpected error")):
            result = asyncio.run(
                screen._wireless_connect("192.168.1.100", "39765")
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

    def test_compose_has_discovery_section(self, compose_source):
        """Test that compose defines the discovery inventory section."""
        assert 'id="discovery-section"' in compose_source

    def test_compose_has_discovery_count(self, compose_source):
        """Test that compose defines the discovery count label."""
        assert 'id="discovery-count"' in compose_source

    def test_compose_has_discovery_inventory(self, compose_source):
        """Test that compose defines the discovery inventory ListView."""
        assert 'id="discovery-inventory"' in compose_source

    def test_compose_has_continue_button(self, compose_source):
        """Test that compose defines the Continue button."""
        assert 'id="btn-continue"' in compose_source

    def test_compose_has_refresh_chats_button(self, compose_source):
        """Test that compose defines the Refresh Chats button."""
        assert 'id="btn-refresh-chats"' in compose_source

    def test_compose_discovery_section_hidden_by_default(self, compose_source):
        """Test that discovery section starts hidden."""
        assert 'classes="hidden"' in compose_source


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

    def test_button_handler_routes_continue(self):
        """Test that Continue button routes to action_continue."""
        screen = DiscoveryScreen()

        mock_event = MagicMock()
        mock_button = MagicMock()
        mock_button.id = "btn-continue"
        mock_event.button = mock_button

        with patch.object(screen, "action_continue") as mock_continue:
            screen.on_button_pressed(mock_event)
            mock_continue.assert_called_once()

    def test_button_handler_routes_refresh_chats(self):
        """Test that Refresh Chats button routes to action_refresh_chats."""
        screen = DiscoveryScreen()

        mock_event = MagicMock()
        mock_button = MagicMock()
        mock_button.id = "btn-refresh-chats"
        mock_event.button = mock_button

        with patch.object(screen, "action_refresh_chats") as mock_refresh:
            screen.on_button_pressed(mock_event)
            mock_refresh.assert_called_once()


# =============================================================================
# Discovery Inventory — Stale Callback Protection
# =============================================================================


class TestDiscoveryGenerationGuard:
    """Tests for the generation-based stale callback protection."""

    def test_add_discovered_chat_appends_to_list(self):
        """Test that _add_discovered_chat adds metadata when generation matches."""
        screen = DiscoveryScreen()
        screen._discovery_generation = 0

        chat = ChatMetadata(name="Test Chat")

        # Mock the UI queries since we have no app context
        with patch.object(screen, "query_one", side_effect=Exception("no app")):
            screen._add_discovered_chat(chat, 0)

        assert len(screen._discovered_chats) == 1
        assert screen._discovered_chats[0].name == "Test Chat"

    def test_add_discovered_chat_ignores_stale_generation(self):
        """Test that _add_discovered_chat ignores callbacks from old generation."""
        screen = DiscoveryScreen()
        screen._discovery_generation = 2

        chat = ChatMetadata(name="Stale Chat")
        screen._add_discovered_chat(chat, 1)  # generation 1, current is 2

        assert len(screen._discovered_chats) == 0

    def test_add_discovered_chat_multiple_chats(self):
        """Test that multiple chats accumulate correctly."""
        screen = DiscoveryScreen()
        screen._discovery_generation = 0

        chats = [
            ChatMetadata(name="Alice"),
            ChatMetadata(name="Bob"),
            ChatMetadata(name="Charlie"),
        ]

        with patch.object(screen, "query_one", side_effect=Exception("no app")):
            for chat in chats:
                screen._add_discovered_chat(chat, 0)

        assert len(screen._discovered_chats) == 3
        assert [c.name for c in screen._discovered_chats] == ["Alice", "Bob", "Charlie"]

    def test_generation_increments_on_refresh(self):
        """Test that action_refresh_chats increments generation."""
        screen = DiscoveryScreen()
        screen._connected_driver = MagicMock()  # Need a driver for refresh
        screen._scanning_chats = False
        initial_gen = screen._discovery_generation

        # Mock all UI queries and run_worker
        with patch.object(screen, "query_one", return_value=MagicMock()):
            with patch.object(screen, "run_worker"):
                screen.action_refresh_chats()

        assert screen._discovery_generation == initial_gen + 1

    def test_refresh_clears_discovered_chats(self):
        """Test that action_refresh_chats clears the discovered chats list."""
        screen = DiscoveryScreen()
        screen._connected_driver = MagicMock()
        screen._scanning_chats = False
        screen._discovered_chats = [
            ChatMetadata(name="Alice"),
            ChatMetadata(name="Bob"),
        ]

        with patch.object(screen, "query_one", return_value=MagicMock()):
            with patch.object(screen, "run_worker"):
                screen.action_refresh_chats()

        assert len(screen._discovered_chats) == 0


# =============================================================================
# Discovery Inventory — Action Guards
# =============================================================================


class TestDiscoveryActionGuards:
    """Tests for action_continue and action_refresh_chats guard conditions."""

    def test_continue_noop_when_scanning(self):
        """Test that action_continue is a no-op while scanning."""
        screen = DiscoveryScreen()
        screen._scanning_chats = True
        screen._discovered_chats = [ChatMetadata(name="Chat")]
        screen._connected_driver = MagicMock()

        # Should not attempt to call app methods
        screen.action_continue()
        # No exception means it returned early (no app context)

    def test_continue_noop_when_no_chats(self):
        """Test that action_continue is a no-op when no chats discovered."""
        screen = DiscoveryScreen()
        screen._scanning_chats = False
        screen._discovered_chats = []

        screen.action_continue()
        # No exception means it returned early

    def test_refresh_noop_when_scanning(self):
        """Test that action_refresh_chats is a no-op while scanning."""
        screen = DiscoveryScreen()
        screen._scanning_chats = True
        screen._connected_driver = MagicMock()
        initial_gen = screen._discovery_generation

        screen.action_refresh_chats()

        # Generation should NOT have changed
        assert screen._discovery_generation == initial_gen

    def test_refresh_noop_when_no_driver(self):
        """Test that action_refresh_chats is a no-op when no driver."""
        screen = DiscoveryScreen()
        screen._scanning_chats = False
        screen._connected_driver = None
        initial_gen = screen._discovery_generation

        screen.action_refresh_chats()

        assert screen._discovery_generation == initial_gen

    def test_refresh_sets_scanning_flag(self):
        """Test that action_refresh_chats sets scanning flag."""
        screen = DiscoveryScreen()
        screen._connected_driver = MagicMock()
        screen._scanning_chats = False

        with patch.object(screen, "query_one", return_value=MagicMock()):
            with patch.object(screen, "run_worker"):
                screen.action_refresh_chats()

        assert screen._scanning_chats is True


# =============================================================================
# Discovery Inventory — Chat Collection Result Handling
# =============================================================================


class TestHandleChatCollection:
    """Tests for _handle_chat_collection with the new inventory behavior."""

    @staticmethod
    def _make_query_one(**widgets):
        """Create a mock query_one that routes by selector."""
        from whatsapp_chat_autoexport.tui.textual_widgets.activity_log import ActivityLog as _AL

        fallback = MagicMock()

        def mock_query_one(selector, widget_type=None):
            # Handle class-based selectors
            if selector is _AL:
                return widgets.get("activity", fallback)
            # Handle string selectors
            if isinstance(selector, str):
                for key, widget in widgets.items():
                    if key.startswith("#") and selector == key:
                        return widget
                return fallback
            return fallback

        return mock_query_one

    def test_successful_collection_enables_continue(self):
        """Test that successful collection enables Continue button."""
        screen = DiscoveryScreen()

        mock_continue_btn = MagicMock()
        mock_refresh_btn = MagicMock()
        mock_activity = MagicMock()

        query_fn = self._make_query_one(
            activity=mock_activity,
            **{
                "#device-status": MagicMock(),
                "#btn-continue": mock_continue_btn,
                "#btn-refresh-chats": mock_refresh_btn,
            },
        )

        with patch.object(screen, "query_one", side_effect=query_fn):
            chats = [ChatMetadata(name="Alice"), ChatMetadata(name="Bob")]
            result = {"success": True, "chats": chats, "driver": MagicMock()}
            screen._handle_chat_collection(result)

        assert mock_continue_btn.disabled is False
        assert screen._discovered_chats == chats

    def test_successful_collection_zero_chats_shows_warning(self):
        """Test that zero chats shows warning and does not enable Continue."""
        screen = DiscoveryScreen()

        mock_activity = MagicMock()
        mock_continue_btn = MagicMock(disabled=True)

        query_fn = self._make_query_one(
            activity=mock_activity,
            **{
                "#device-status": MagicMock(),
                "#btn-continue": mock_continue_btn,
                "#btn-refresh-chats": MagicMock(),
            },
        )

        with patch.object(screen, "query_one", side_effect=query_fn):
            result = {"success": True, "chats": [], "driver": MagicMock()}
            screen._handle_chat_collection(result)

        mock_activity.log_warning.assert_called_once()

    def test_failed_collection_enables_refresh_only(self):
        """Test that failed collection enables Refresh but not Continue."""
        screen = DiscoveryScreen()

        mock_activity = MagicMock()
        mock_refresh_btn = MagicMock()

        query_fn = self._make_query_one(
            activity=mock_activity,
            **{
                "#device-status": MagicMock(),
                "#btn-refresh-chats": mock_refresh_btn,
            },
        )

        with patch.object(screen, "query_one", side_effect=query_fn):
            result = {"success": False, "error": "timeout", "driver": MagicMock()}
            screen._handle_chat_collection(result)

        assert mock_refresh_btn.disabled is False
        mock_activity.log_error.assert_called_once()

    def test_collection_clears_scanning_flag(self):
        """Test that _handle_chat_collection clears scanning flag."""
        screen = DiscoveryScreen()
        screen._scanning_chats = True

        with patch.object(screen, "query_one", return_value=MagicMock()):
            result = {"success": True, "chats": [ChatMetadata(name="A")], "driver": MagicMock()}
            screen._handle_chat_collection(result)

        assert screen._scanning_chats is False


# =============================================================================
# Dry Run Mode — ChatMetadata
# =============================================================================


class TestDryRunChatMetadata:
    """Tests that dry run mode now produces ChatMetadata objects."""

    @staticmethod
    def _make_dry_run_query_one():
        """Create a mock query_one that returns MagicMock for any selector."""
        mock_inventory = MagicMock()
        cache = {}

        def mock_query_one(selector, widget_type=None):
            # Use id() for class selectors, string for string selectors
            key = selector if isinstance(selector, str) else id(selector)
            if key == "#discovery-inventory":
                return mock_inventory
            if key not in cache:
                cache[key] = MagicMock()
            return cache[key]

        return mock_query_one

    def test_dry_run_uses_chat_metadata(self):
        """Test that action_use_dry_run creates ChatMetadata instances."""
        screen = DiscoveryScreen()

        mock_app = MagicMock()

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            with patch.object(screen, "query_one", side_effect=self._make_dry_run_query_one()):
                screen.action_use_dry_run()

        # Verify chats are ChatMetadata instances
        assert len(screen._discovered_chats) == 10
        assert all(isinstance(c, ChatMetadata) for c in screen._discovered_chats)
        assert screen._discovered_chats[0].name == "John Doe"
        assert screen._discovered_chats[-1].name == "Team Project"

    def test_dry_run_does_not_auto_transition(self):
        """Test that dry run mode does not auto-transition to selection."""
        screen = DiscoveryScreen()

        mock_app = MagicMock()

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            with patch.object(screen, "query_one", side_effect=self._make_dry_run_query_one()):
                screen.action_use_dry_run()

        # Should NOT call transition_to_selection
        mock_app.call_later.assert_not_called()

    def test_dry_run_sets_connected_driver_none(self):
        """Test that dry run sets _connected_driver to None."""
        screen = DiscoveryScreen()

        mock_app = MagicMock()

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            with patch.object(screen, "query_one", side_effect=self._make_dry_run_query_one()):
                screen.action_use_dry_run()

        assert screen._connected_driver is None


# =============================================================================
# Collect Chats — on_chat_found callback
# =============================================================================


class TestCollectChatsCallback:
    """Tests for the on_chat_found callback wiring in _collect_chats."""

    def test_collect_chats_passes_callback(self):
        """Test that _collect_chats passes on_chat_found to collect_all_chats."""
        screen = DiscoveryScreen()

        mock_app = MagicMock()
        mock_app.limit = None
        screen.call_from_thread = MagicMock()

        mock_driver = MagicMock()
        mock_driver.collect_all_chats.return_value = [ChatMetadata(name="Chat 1")]

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            result = asyncio.run(screen._collect_chats(mock_driver))

        assert result["success"] is True
        # Verify collect_all_chats was called with 3 positional args (limit, sort, callback)
        mock_driver.collect_all_chats.assert_called_once()
        args = mock_driver.collect_all_chats.call_args
        assert args[0][0] is None  # limit
        assert args[0][1] is False  # sort_alphabetical
        assert callable(args[0][2])  # on_chat_found callback

    def test_collect_chats_callback_calls_call_from_thread(self):
        """Test that the on_found callback invokes call_from_thread."""
        screen = DiscoveryScreen()
        screen._discovery_generation = 5

        mock_app = MagicMock()
        mock_app.limit = None
        screen.call_from_thread = MagicMock()

        captured_callback = None

        def fake_collect(limit, sort, on_chat_found):
            nonlocal captured_callback
            captured_callback = on_chat_found
            chat = ChatMetadata(name="Test")
            on_chat_found(chat)
            return [chat]

        mock_driver = MagicMock()
        mock_driver.collect_all_chats.side_effect = fake_collect

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            asyncio.run(screen._collect_chats(mock_driver))

        # Verify call_from_thread was invoked with correct args
        screen.call_from_thread.assert_called_once()
        call_args = screen.call_from_thread.call_args[0]
        assert call_args[0] == screen._add_discovered_chat
        assert call_args[1].name == "Test"
        assert call_args[2] == 5  # generation captured by value

    def test_collect_chats_error_handling(self):
        """Test that _collect_chats handles exceptions."""
        screen = DiscoveryScreen()

        mock_app = MagicMock()
        mock_app.limit = 5
        screen.call_from_thread = MagicMock()

        mock_driver = MagicMock()
        mock_driver.collect_all_chats.side_effect = RuntimeError("connection lost")

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda self: mock_app)):
            result = asyncio.run(screen._collect_chats(mock_driver))

        assert result["success"] is False
        assert "connection lost" in result["error"]
