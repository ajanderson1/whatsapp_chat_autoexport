"""
WhatsApp Driver module for WhatsApp Chat Auto-Export.

Manages WhatsApp connection and navigation via Appium and UiAutomator2.
"""

import subprocess
import os
import time
from time import sleep
from typing import Optional, Tuple, List
from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By

from ..utils.logger import Logger


# Helper functions for device connection

def validate_pairing_code(code: str) -> bool:
    """
    Validate that pairing code is exactly 6 digits.

    Args:
        code: Pairing code to validate

    Returns:
        True if valid (exactly 6 digits), False otherwise
    """
    return code.isdigit() and len(code) == 6


def prompt_for_pairing_code() -> str:
    """
    Prompt user for 6-digit pairing code with validation.
    Keeps prompting until valid code is entered.

    Returns:
        Valid 6-digit pairing code
    """
    while True:
        code = input("Enter 6-digit pairing code: ").strip()
        if validate_pairing_code(code):
            return code
        print("❌ Error: Pairing code must be exactly 6 digits. Please try again.")


def prompt_for_connect_port(default: str = "5555") -> str:
    """
    Prompt user for ADB connect port with default suggestion.

    Args:
        default: Default port to suggest (usually 5555)

    Returns:
        Connect port (user input or default)
    """
    response = input(f"Enter connect port [default: {default}]: ").strip()
    return response if response else default


def check_existing_devices(logger: Logger) -> List[str]:
    """
    Check for already connected ADB devices.

    Args:
        logger: Logger instance for debug output

    Returns:
        List of device IDs currently connected
    """
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.debug_msg(f"adb devices failed: {result.stderr}")
            return []

        # Parse output - lines like "192.168.1.100:5555    device"
        devices = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header line
            if 'device' in line and 'offline' not in line and 'unauthorized' not in line:
                device_id = line.split()[0]
                devices.append(device_id)

        logger.debug_msg(f"Found {len(devices)} connected device(s): {devices}")
        return devices

    except Exception as e:
        logger.debug_msg(f"Error checking devices: {e}")
        return []


def prompt_device_selection(devices: List[str], logger: Logger) -> Optional[str]:
    """
    Prompt user to select a device from list.

    Args:
        devices: List of device IDs
        logger: Logger instance

    Returns:
        Selected device ID, or None if user wants to connect new device
    """
    print("\nMultiple devices found:")
    for i, device in enumerate(devices, 1):
        print(f"  {i}. {device}")
    print(f"  {len(devices) + 1}. Connect new wireless device")

    while True:
        try:
            response = input(f"\nSelect device (1-{len(devices) + 1}): ").strip()
            selection = int(response)

            if 1 <= selection <= len(devices):
                selected_device = devices[selection - 1]
                logger.success(f"Selected device: {selected_device}")
                return selected_device
            elif selection == len(devices) + 1:
                logger.info("Will connect new wireless device...")
                return None
            else:
                print(f"❌ Please enter a number between 1 and {len(devices) + 1}")
        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n❌ Cancelled by user")
            return None


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """
    Generic yes/no prompt with default value.

    Args:
        question: Question to ask user
        default: Default value if user just presses Enter

    Returns:
        True for yes, False for no
    """
    default_str = "Y/n" if default else "y/N"
    while True:
        response = input(f"{question} ({default_str}): ").strip().lower()

        if not response:
            return default

        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("❌ Please answer 'y' or 'n'")


def parse_ip_from_address(address: str) -> str:
    """
    Extract IP address from "IP:PORT" format.

    Args:
        address: Address in "IP:PORT" format (e.g., "192.168.1.100:5555")

    Returns:
        Just the IP part (e.g., "192.168.1.100")
    """
    return address.split(':')[0] if ':' in address else address


def wireless_adb_pair(pairing_address: str, pairing_code: str, logger: Logger) -> bool:
    """
    Pair with wireless ADB device.

    Args:
        pairing_address: Pairing address in "IP:PORT" format
        pairing_code: 6-digit pairing code
        logger: Logger instance

    Returns:
        True if pairing successful, False otherwise
    """
    logger.info(f"Pairing with device at {pairing_address}...")
    try:
        result = subprocess.run(
            ["adb", "pair", pairing_address, pairing_code],
            capture_output=True,
            text=True,
            timeout=30
        )

        logger.debug_msg(f"Pairing output: {result.stdout}")

        if result.returncode != 0:
            logger.error(f"Pairing failed: {result.stderr}")
            return False

        if "Successfully paired" not in result.stdout and "success" not in result.stdout.lower():
            logger.warning(f"Unexpected pairing output: {result.stdout}")
            # Continue anyway as sometimes it still works

        logger.success("Pairing successful!")
        return True

    except subprocess.TimeoutExpired:
        logger.error("Pairing timed out after 30 seconds")
        return False
    except Exception as e:
        logger.error(f"Error during pairing: {e}")
        return False


def wireless_adb_connect(pairing_address: str, connect_port: str, logger: Logger) -> Tuple[bool, Optional[str]]:
    """
    Connect to wireless ADB device (after pairing).

    Args:
        pairing_address: Original pairing address (to extract IP)
        connect_port: Port to use for connection (usually 5555)
        logger: Logger instance

    Returns:
        Tuple of (success: bool, device_id: Optional[str])
        - success: True if successfully connected, False otherwise
        - device_id: Device ID if successful, None otherwise
    """
    ip = parse_ip_from_address(pairing_address)
    connect_address = f"{ip}:{connect_port}"

    logger.info(f"Connecting to device at {connect_address}...")
    try:
        result = subprocess.run(
            ["adb", "connect", connect_address],
            capture_output=True,
            text=True,
            timeout=10
        )

        logger.debug_msg(f"Connect output: {result.stdout}")

        if result.returncode != 0:
            logger.error(f"Connection failed: {result.stderr}")
            return False, None

        if "connected" not in result.stdout.lower() and "already connected" not in result.stdout.lower():
            logger.error(f"Unexpected connection output: {result.stdout}")
            return False, None

        logger.success(f"Connected to {connect_address}!")

    except subprocess.TimeoutExpired:
        logger.error("Connection timed out after 10 seconds")
        return False, None
    except Exception as e:
        logger.error(f"Error during connection: {e}")
        return False, None

    # Verify the device appears in adb devices
    sleep(1)  # Give ADB a moment to register

    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True
        )

        logger.debug_msg(f"Verification output: {result.stdout}")

        # Check if our device is in the list
        if connect_address in result.stdout and "device" in result.stdout:
            logger.success(f"Device {connect_address} verified in device list!")
            return True, connect_address
        else:
            logger.error(f"Device {connect_address} not found in device list")
            logger.error(f"Current devices:\n{result.stdout}")
            return False, None

    except Exception as e:
        logger.error(f"Error verifying connection: {e}")
        return False, None


# Main WhatsAppDriver class

class WhatsAppDriver:
    """Manages WhatsApp connection and navigation."""

    def __init__(self, logger: Logger, wireless_adb: Optional[List[str]] = None):
        self.logger = logger
        self.driver: Optional[webdriver.Remote] = None
        self.default_wait_timeout = 10  # Default timeout for explicit waits
        self.wireless_adb = wireless_adb
        self.device_id: Optional[str] = None  # Store selected device ID for device-specific commands
        self.is_wireless = wireless_adb is not None  # Track if using wireless ADB

    def keep_device_awake(self) -> None:
        """
        Prevent device from sleeping during export by using ADB to keep screen on.
        This helps prevent session loss during long-running exports.
        """
        try:
            adb_cmd = ["adb"]
            if self.device_id:
                adb_cmd.extend(["-s", self.device_id])
            
            # Enable "stay_on_while_plugged_in" setting (keeps screen on while USB connected)
            adb_cmd_stay_on = adb_cmd + ["shell", "settings", "put", "global", "stay_on_while_plugged_in", "7"]
            result = subprocess.run(adb_cmd_stay_on, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.success("✓ Device configured to stay awake while connected")
            else:
                self.logger.warning("Could not configure device to stay awake (may require manual settings)")
                
        except Exception as e:
            self.logger.debug_msg(f"Could not keep device awake: {e}")

    def is_session_active(self) -> bool:
        """
        Check if the Appium session is still active.
        
        Returns:
            True if session is active, False otherwise
        """
        try:
            if self.driver is None:
                return False
            # Try to get current package - if this works, session is active
            _ = self.driver.current_package
            return True
        except Exception as e:
            self.logger.debug_msg(f"Session check failed: {e}")
            return False

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to WhatsApp if session was lost.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        self.logger.warning("Session lost - attempting to reconnect...")
        
        # First, check if ADB connection is still alive
        adb_connected, adb_error = self.check_adb_connection()
        if not adb_connected:
            self.logger.error(f"Cannot reconnect: {adb_error}")
            self.logger.error("Please check your device connection and try again")
            return False
        
        self.logger.success("✓ ADB connection is still active")
        
        # Close any existing session
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        # Wait a moment before reconnecting
        sleep(2)
        
        # Attempt to reconnect
        return self.connect()

    def check_adb_connection(self) -> tuple[bool, str]:
        """
        Check if ADB connection to device is still alive.
        This is particularly important for wireless ADB which can drop unexpectedly.
        
        Returns:
            Tuple of (connected: bool, error_msg: str)
            - connected: True if ADB connection is active
            - error_msg: Description of issue if not connected
        """
        if not self.device_id:
            # If no device_id set yet, can't check specific device
            return True, ""
        
        try:
            result = subprocess.run(
                ["adb", "-s", self.device_id, "get-state"],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0 and "device" in result.stdout:
                return True, ""
            else:
                error_msg = f"ADB connection lost (state: {result.stdout.strip()})"
                if self.is_wireless:
                    error_msg += " - Wireless ADB disconnected"
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "ADB command timed out"
            if self.is_wireless:
                error_msg += " - Wireless ADB may be unresponsive"
            return False, error_msg
        except Exception as e:
            error_msg = f"ADB check failed: {e}"
            return False, error_msg

    def safe_driver_call(self, operation_name: str, func: callable, max_retries: int = 3):
        """
        Execute a driver operation with automatic retry and session recovery.
        
        Args:
            operation_name: Name of the operation (for logging)
            func: Callable that performs the driver operation
            max_retries: Maximum number of retry attempts (default: 3)
        
        Returns:
            Result of func() if successful
        
        Raises:
            Exception: Re-raises the exception if all retries exhausted
        """
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a session termination error
                is_session_error = any(keyword in error_msg for keyword in [
                    "session is either terminated",
                    "nosuchdrivererror",
                    "invalidsessionid",
                    "session",
                    "terminated",
                    "not started"
                ])
                
                if is_session_error:
                    self.logger.warning(
                        f"{operation_name} failed (attempt {attempt+1}/{max_retries}): "
                        f"Session appears lost"
                    )
                    
                    if attempt < max_retries - 1:
                        # Attempt reconnection
                        self.logger.info("Attempting session recovery...")
                        if self.reconnect():
                            self.logger.success("Session recovered successfully, retrying operation...")
                            sleep(1)  # Brief pause before retry
                            continue
                        else:
                            self.logger.error("Session recovery failed")
                            raise
                    else:
                        # Out of retries
                        raise
                else:
                    # Non-session error - re-raise immediately (don't waste retries)
                    raise
        
        # Should not reach here, but just in case
        raise Exception(f"{operation_name} failed after {max_retries} attempts")

    def _wait_for_element(self, locator_type: str, locator_value: str, timeout: Optional[int] = None,
                         expected_condition: str = "presence") -> Optional[object]:
        """
        Wait for an element to be present or visible using explicit wait.

        Args:
            locator_type: Type of locator ('id', 'xpath', 'class_name', etc.)
            locator_value: Value of the locator
            timeout: Timeout in seconds (defaults to self.default_wait_timeout)
            expected_condition: 'presence' or 'visible' (default: 'presence')

        Returns:
            WebElement if found, None if timeout
        """
        if not self.driver:
            return None

        timeout = timeout or self.default_wait_timeout
        wait = WebDriverWait(self.driver, timeout)

        # Create locator tuple
        if locator_type == "id":
            # For Appium Android, resource IDs need to be accessed via xpath with resource-id attribute
            locator = (By.XPATH, f"//*[@resource-id='{locator_value}']")
        elif locator_type == "xpath":
            locator = (By.XPATH, locator_value)
        elif locator_type == "class_name":
            locator = (By.CLASS_NAME, locator_value)
        elif locator_type == "accessibility_id":
            # For accessibility_id, Appium uses content-desc attribute
            locator = (By.XPATH, f"//*[@content-desc='{locator_value}']")
        else:
            self.logger.debug_msg(f"Unsupported locator type: {locator_type}")
            return None

        try:
            if expected_condition == "visible":
                return wait.until(EC.visibility_of_element_located(locator))
            else:  # presence
                return wait.until(EC.presence_of_element_located(locator))
        except TimeoutException:
            self.logger.debug_msg(f"Timeout waiting for element: {locator_type}={locator_value}")
            return None

    def _wait_for_activity(self, expected_activity: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for a specific activity to become current.

        Args:
            expected_activity: Activity name to wait for (can be substring)
            timeout: Timeout in seconds (defaults to self.default_wait_timeout)

        Returns:
            True if activity found, False if timeout
        """
        if not self.driver:
            return False

        timeout = timeout or self.default_wait_timeout
        end_time = time.time() + timeout

        while time.time() < end_time:
            try:
                current_activity = self.driver.current_activity
                if expected_activity in current_activity:
                    return True
                sleep(0.2)  # Brief check interval
            except Exception:
                sleep(0.2)

        return False

    def check_device_connection(self) -> bool:
        """
        Check if Android device is connected with robust device selection and wireless ADB support.

        Workflow:
        1. Check for existing connected devices
        2. Handle existing device selection/confirmation
        3. Optionally set up wireless ADB connection with pairing
        4. Verify final connection

        Returns:
            True if device is connected and ready, False otherwise
        """
        self.logger.info("Checking device connection...")

        # Step 1: Check for existing devices
        existing_devices = check_existing_devices(self.logger)

        # Step 2: Handle existing devices
        if existing_devices:
            if len(existing_devices) == 1:
                # Single device found
                device = existing_devices[0]
                self.logger.info(f"Device already connected: {device}")

                # Check if user wants to use this device or connect wireless
                if self.wireless_adb:
                    # Wireless flag provided but device already exists
                    if prompt_yes_no(f"Device {device} already connected. Still connect wireless device?", default=False):
                        self.logger.info("Will proceed with wireless ADB setup...")
                        # Continue to wireless setup below
                    else:
                        # Use existing device
                        self.device_id = device
                        self.logger.success(f"Using device: {device}")
                        return True
                else:
                    # No wireless flag, ask if user wants to use existing device
                    if prompt_yes_no(f"Use device {device}?", default=True):
                        self.device_id = device
                        self.logger.success(f"Using device: {device}")
                        return True
                    else:
                        self.logger.error("No device selected")
                        return False

            else:
                # Multiple devices found
                self.logger.info(f"Found {len(existing_devices)} devices")

                # Let user select device or connect new wireless device
                selected_device = prompt_device_selection(existing_devices, self.logger)

                if selected_device is not None:
                    # User selected existing device
                    self.device_id = selected_device
                    self.logger.success(f"Using device: {selected_device}")
                    return True
                else:
                    # User wants to connect new wireless device
                    if self.wireless_adb is None:
                        # No wireless flag provided, ensure empty list so Step 3 will prompt
                        self.wireless_adb = []
                    # Continue to wireless setup below (Step 3 will handle prompting)

        else:
            # No existing devices
            if self.wireless_adb is None:
                self.logger.error("No device found. Connect via USB or use --wireless-adb flag")
                return False
            # else: continue to wireless setup

        # Step 3: Wireless ADB setup (if we reach here)
        if self.wireless_adb is not None:
            # Parse wireless_adb arguments to get pairing details (NOT connect port yet)
            if len(self.wireless_adb) == 0:
                # No arguments provided, prompt for pairing details only
                self.logger.info("Wireless ADB mode - please provide pairing details...")
                pairing_address = input("Enter pairing address (IP:PORT): ").strip()
                pairing_code = prompt_for_pairing_code()

            elif len(self.wireless_adb) == 1:
                # Only pairing address provided
                pairing_address = self.wireless_adb[0]
                self.logger.info(f"Using pairing address: {pairing_address}")
                pairing_code = prompt_for_pairing_code()

            elif len(self.wireless_adb) == 2:
                # Both pairing address and code provided
                pairing_address = self.wireless_adb[0]
                pairing_code = self.wireless_adb[1]
                self.logger.info(f"Using pairing address: {pairing_address}")

                # Validate pairing code
                if not validate_pairing_code(pairing_code):
                    self.logger.error(f"Invalid pairing code: {pairing_code} (must be 6 digits)")
                    pairing_code = prompt_for_pairing_code()

            else:
                self.logger.error(f"Invalid number of wireless-adb arguments: {len(self.wireless_adb)}")
                return False

            # Step 4: Attempt pairing and connection with retry logic
            while True:
                # First, attempt pairing
                pairing_success = wireless_adb_pair(pairing_address, pairing_code, self.logger)

                if not pairing_success:
                    # Pairing failed - ask if user wants to retry
                    if prompt_yes_no("Pairing failed. Retry?", default=True):
                        # Re-prompt for pairing details
                        self.logger.info("Please re-enter pairing details...")
                        pairing_address = input("Enter pairing address (IP:PORT): ").strip()
                        pairing_code = prompt_for_pairing_code()
                        # Loop will retry pairing
                        continue
                    else:
                        self.logger.error("Wireless ADB pairing cancelled by user")
                        return False

                # Pairing successful! Now prompt for connect port
                connect_port = prompt_for_connect_port()

                # Attempt connection
                connect_success, device_id = wireless_adb_connect(pairing_address, connect_port, self.logger)

                if connect_success:
                    self.device_id = device_id
                    self.logger.success(f"Successfully connected to wireless device: {device_id}")
                    return True
                else:
                    # Connection failed - ask if user wants to retry
                    if prompt_yes_no("Connection failed. Retry?", default=True):
                        # Re-prompt for all details (pairing might need to be redone)
                        self.logger.info("Please re-enter wireless ADB details...")
                        pairing_address = input("Enter pairing address (IP:PORT): ").strip()
                        pairing_code = prompt_for_pairing_code()
                        # Loop will retry from pairing step
                    else:
                        self.logger.error("Wireless ADB connection cancelled by user")
                        return False

        # Should not reach here, but just in case
        self.logger.error("Device connection failed")
        return False

    def connect(self) -> bool:
        """Connect to WhatsApp via Appium."""
        self.logger.info("Stopping WhatsApp (this does NOT delete any data)...")
        adb_cmd = ["adb"]
        if self.device_id:
            adb_cmd.extend(["-s", self.device_id])
        adb_cmd.extend(["shell", "am", "force-stop", "com.whatsapp"])
        subprocess.run(adb_cmd, capture_output=True)
        sleep(0.5)  # Brief delay for app to stop (system command, not UI)
        self.logger.success("WhatsApp stopped")

        # Keep device awake to prevent session loss during long exports
        self.keep_device_awake()

        self.logger.info("Setting up WebDriver options...")
        
        # Adjust timeouts based on connection type
        if self.is_wireless:
            # Wireless ADB needs longer timeouts due to network latency
            adb_exec_timeout = 120000  # 2 minutes
            self.logger.info("📡 Using wireless ADB - increased timeouts for stability")
        else:
            # USB connection is more stable, shorter timeouts are fine
            adb_exec_timeout = 60000  # 1 minute
            self.logger.info("🔌 Using USB connection")
        
        options = UiAutomator2Options()
        capabilities = {
            "platformName": "Android",
            "deviceName": "Pixel_10_Pro",
            "automationName": "UiAutomator2",
            "appPackage": "com.whatsapp",
            "appActivity": "com.whatsapp.Main",
            "noReset": True,
            "fullReset": False,
            # Session timeout settings to prevent session loss during long runs
            "newCommandTimeout": 3600,  # 1 hour - time to wait for new command before ending session
            "uiautomator2ServerLaunchTimeout": 60000,  # 60 seconds for server launch
            "uiautomator2ServerInstallTimeout": 60000,  # 60 seconds for server install
            "adbExecTimeout": adb_exec_timeout,  # Varies based on connection type
        }

        # If specific device selected, tell Appium which device to use
        if self.device_id:
            capabilities["udid"] = self.device_id
            self.logger.debug_msg(f"Using device UDID: {self.device_id}")

        options.load_capabilities(capabilities)

        self.logger.info("Connecting to Appium server...")
        try:
            self.driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
            self.logger.success("Driver connected successfully!")

            # Wait for driver to stabilize and auto-launch WhatsApp (from capabilities)
            self.logger.info("Waiting for WhatsApp to auto-launch from driver capabilities...")
            sleep(5 if self.is_wireless else 3)  # Longer wait for wireless ADB

            # Check what's currently open
            try:
                current_pkg = self.driver.current_package
                self.logger.debug_msg(f"Current package after driver connect: {current_pkg}")
            except:
                current_pkg = None

            # If WhatsApp is already running (auto-launched by capabilities), great!
            # If not, we need to clear overlays and launch it manually
            if current_pkg != "com.whatsapp":
                self.logger.info(f"WhatsApp not auto-launched (current: {current_pkg})")
                self.logger.info("Pressing home button to clear overlays and start fresh...")

                try:
                    self.driver.press_keycode(3)  # HOME button
                    sleep(1)
                except Exception as e:
                    self.logger.debug_msg(f"Home button press failed: {e}")

                # Launch WhatsApp using ADB (most reliable method)
                self.logger.info("Launching WhatsApp via ADB...")
                adb_cmd = ["adb"]
                if self.device_id:
                    adb_cmd.extend(["-s", self.device_id])
                adb_cmd.extend(["shell", "am", "start", "-n", "com.whatsapp/.Main"])
                result = subprocess.run(adb_cmd, capture_output=True, text=True)
                self.logger.debug_msg(f"ADB launch: {result.stdout.strip() if result.stdout else 'success'}")

                sleep(5 if self.is_wireless else 3)  # Wait for app to launch
            else:
                self.logger.success("WhatsApp auto-launched successfully")
                sleep(2)  # Brief additional stabilization time

            # CRITICAL: Use robust verification instead of simple package check
            # This prevents accidentally interacting with system UI
            return self.verify_whatsapp_is_open()

        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False

    def navigate_to_main(self) -> bool:
        """Navigate to main chats screen."""
        self.logger.info("Checking WhatsApp state...")
        try:
            current_package = self.driver.current_package
            current_activity = self.driver.current_activity
            self.logger.debug_msg(f"Current package: {current_package}")
            self.logger.debug_msg(f"Current activity: {current_activity}")

            if current_package != "com.whatsapp":
                self.logger.error(f"WhatsApp package not detected. Current: {current_package}")

                # Check if this might be due to locked phone
                is_locked, reason = self.check_if_phone_locked()
                if is_locked:
                    self.logger.error("This may be because the phone is locked.")
                    self.logger.error(f"Lock detection: {reason}")

                return False

            self.logger.success("WhatsApp package detected!")

            # If we're in a conversation, navigate back
            if ".Conversation" in current_activity or "Conversation" in current_activity:
                self.logger.info("Currently in conversation view. Navigating to main chats list...")
                self.driver.press_keycode(4)  # Back button

                # Wait for navigation away from conversation
                if self._wait_for_activity("Home", timeout=5) or self._wait_for_activity("home", timeout=5):
                    new_activity = self.driver.current_activity
                    self.logger.debug_msg(f"After back press, activity: {new_activity}")

                    # Check if still in conversation (might need another back press)
                    if ".Conversation" in new_activity or "Conversation" in new_activity:
                        self.logger.debug_msg("Still in conversation, pressing back again...")
                        self.driver.press_keycode(4)
                        sleep(0.5)  # Brief UI animation delay
                else:
                    sleep(0.5)  # Brief delay if wait didn't detect change
            else:
                self.logger.success("Already on main chats screen!")

            return True
        except Exception as e:
            self.logger.error(f"Error checking package/activity: {e}")

            # Check if this error might be due to phone being locked
            try:
                is_locked, reason = self.check_if_phone_locked()
                if is_locked:
                    self.logger.error("=" * 70)
                    self.logger.error("🔒 PHONE MAY BE LOCKED")
                    self.logger.error("=" * 70)
                    self.logger.error(f"Lock detection: {reason}")
                    self.logger.error("Please unlock your phone and ensure WhatsApp is accessible.")
                    self.logger.error("=" * 70)
            except:
                # If lock check itself fails, just continue with original error
                pass

            return False

    def check_if_phone_locked(self) -> tuple[bool, str]:
        """
        Check if the phone appears to be locked.

        Returns:
            Tuple of (is_locked: bool, reason: str)
            - is_locked: True if phone appears locked, False otherwise
            - reason: Description of why we think it's locked
        """
        try:
            # Check 1: Try to get current activity
            try:
                current_activity = self.driver.current_activity
                self.logger.debug_msg(f"Lock check - Current activity: {current_activity}")

                # Common lock screen activity indicators
                lock_indicators = [
                    "Keyguard",
                    "LockScreen",
                    "lockscreen",
                    "KeyguardView",
                    "StatusBar"  # Sometimes appears when locked
                ]

                for indicator in lock_indicators:
                    if indicator in current_activity:
                        return (True, f"Lock screen activity detected: {current_activity}")

            except Exception as e:
                self.logger.debug_msg(f"Lock check - Unable to get activity: {e}")
                # If we can't get activity at all, might be locked
                return (True, f"Unable to access device activity (common when locked): {e}")

            # Check 2: Try to get current package
            try:
                current_package = self.driver.current_package
                self.logger.debug_msg(f"Lock check - Current package: {current_package}")

                # If we're not in WhatsApp and in system UI, likely locked
                if current_package != "com.whatsapp" and "systemui" in current_package.lower():
                    return (True, f"System UI detected instead of WhatsApp: {current_package}")

            except Exception as e:
                self.logger.debug_msg(f"Lock check - Unable to get package: {e}")
                # Inability to get package can indicate lock screen
                return (True, f"Unable to access app package (common when locked): {e}")

            # Check 3: Try to find any UI element (locked screens typically won't have app elements)
            try:
                # Look for WhatsApp-specific elements
                elements = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
                self.logger.debug_msg(f"Lock check - Found {len(elements)} chat elements")

                # If we can access WhatsApp elements, phone is likely unlocked
                if len(elements) > 0:
                    return (False, "WhatsApp UI elements accessible")

            except Exception as e:
                self.logger.debug_msg(f"Lock check - Unable to find elements: {e}")

            # Check 4: Check for lock screen UI elements (if Appium can see them)
            try:
                # Some common lock screen element IDs
                lock_elements = self.driver.find_elements("id", "com.android.systemui:id/lock_icon")
                if len(lock_elements) > 0:
                    return (True, "Lock icon UI element found")
            except:
                pass  # This is expected to fail if not on lock screen

            # If we got here without clear indicators, phone is likely unlocked
            # (we could access activity and package without errors)
            return (False, "No lock indicators detected")

        except Exception as e:
            self.logger.debug_msg(f"Lock check - Unexpected error: {e}")
            # If we hit unexpected errors, might be locked
            return (True, f"Unable to check phone state (may be locked): {e}")

    def detect_phone_lock_state(self) -> bool:
        """
        Detect if phone is locked and provide user-friendly error message.

        Returns:
            True if phone is unlocked and ready, False if locked
        """
        self.logger.info("Checking if phone is unlocked...")

        is_locked, reason = self.check_if_phone_locked()

        if is_locked:
            self.logger.error("=" * 70)
            self.logger.error("🔒 PHONE APPEARS TO BE LOCKED")
            self.logger.error("=" * 70)
            self.logger.error(f"Detection reason: {reason}")
            self.logger.error("")
            self.logger.error("Please:")
            self.logger.error("  1. Unlock your phone")
            self.logger.error("  2. Ensure WhatsApp is accessible")
            self.logger.error("  3. Try running the script again")
            self.logger.error("")
            self.logger.error("The phone must remain unlocked throughout the export process.")
            self.logger.error("=" * 70)
            return False
        else:
            self.logger.success(f"Phone is unlocked and ready ({reason})")
            return True

    def verify_whatsapp_is_open(self) -> bool:
        """
        CRITICAL: Verify WhatsApp is actually open and accessible before proceeding.
        This prevents the script from accidentally interacting with system settings
        or other non-WhatsApp UI elements.

        Returns:
            True if WhatsApp is confirmed open and accessible, False otherwise
        """
        self.logger.info("=" * 70)
        self.logger.info("🔍 CRITICAL: Verifying WhatsApp is open and accessible")
        self.logger.info("=" * 70)

        try:
            # Check 1: Current package MUST be WhatsApp
            # Use retry wrapper to handle transient session issues
            current_package = self.safe_driver_call(
                "Get current package",
                lambda: self.driver.current_package,
                max_retries=3
            )
            self.logger.info(f"Current package: {current_package}")

            if current_package != "com.whatsapp":
                self.logger.error("=" * 70)
                self.logger.error("❌ CRITICAL FAILURE: Not in WhatsApp!")
                self.logger.error("=" * 70)
                self.logger.error(f"Current package: {current_package}")
                self.logger.error("Expected: com.whatsapp")
                self.logger.error("")
                self.logger.error("This could mean:")
                self.logger.error("  - Phone is locked")
                self.logger.error("  - WhatsApp failed to launch")
                self.logger.error("  - In system settings or another app")
                self.logger.error("")
                self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
                self.logger.error("=" * 70)
                return False

            self.logger.success("✓ Package confirmed: com.whatsapp")

            # Check 2: Current activity MUST be a WhatsApp activity
            current_activity = self.driver.current_activity
            self.logger.info(f"Current activity: {current_activity}")

            # List of activities that are NOT safe WhatsApp screens
            unsafe_activities = ["Keyguard", "LockScreen", "lockscreen", "StatusBar", "systemui", "Settings"]
            for unsafe in unsafe_activities:
                if unsafe in current_activity:
                    self.logger.error("=" * 70)
                    self.logger.error(f"❌ CRITICAL FAILURE: Unsafe activity detected!")
                    self.logger.error("=" * 70)
                    self.logger.error(f"Current activity: {current_activity}")
                    self.logger.error(f"Unsafe indicator: {unsafe}")
                    self.logger.error("")
                    self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
                    self.logger.error("=" * 70)
                    return False

            self.logger.success(f"✓ Activity confirmed safe: {current_activity}")

            # Check 3: Verify we can see WhatsApp UI elements
            self.logger.info("Checking for WhatsApp UI elements...")

            # Try to find common WhatsApp elements
            whatsapp_elements_found = False

            # Look for chat list elements
            try:
                chat_elements = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
                if len(chat_elements) > 0:
                    self.logger.success(f"✓ Found {len(chat_elements)} chat elements")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No chat elements found: {e}")

            # Look for toolbar (present on most WhatsApp screens)
            try:
                toolbar = self.driver.find_elements("id", "com.whatsapp:id/toolbar")
                if len(toolbar) > 0:
                    self.logger.success("✓ Found WhatsApp toolbar")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No toolbar found: {e}")

            # Look for action bar (another common element)
            try:
                action_bar = self.driver.find_elements("id", "com.whatsapp:id/action_bar")
                if len(action_bar) > 0:
                    self.logger.success("✓ Found WhatsApp action bar")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No action bar found: {e}")

            # Look for menu button
            try:
                menu_button = self.driver.find_elements("id", "com.whatsapp:id/menuitem_search")
                if len(menu_button) > 0:
                    self.logger.success("✓ Found WhatsApp menu button")
                    whatsapp_elements_found = True
            except Exception as e:
                self.logger.debug_msg(f"No menu button found: {e}")

            if not whatsapp_elements_found:
                self.logger.error("=" * 70)
                self.logger.error("❌ CRITICAL FAILURE: No WhatsApp UI elements found!")
                self.logger.error("=" * 70)
                self.logger.error("Package is com.whatsapp but UI is not accessible.")
                self.logger.error("")
                self.logger.error("This could mean:")
                self.logger.error("  - Phone is locked but showing WhatsApp in background")
                self.logger.error("  - WhatsApp is loading but not ready")
                self.logger.error("  - Dialog or overlay is blocking WhatsApp UI")
                self.logger.error("")
                self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
                self.logger.error("=" * 70)
                return False

            self.logger.success("✓ WhatsApp UI elements accessible")

            # Check 4: Final lock screen check
            is_locked, lock_reason = self.check_if_phone_locked()
            if is_locked:
                self.logger.error("=" * 70)
                self.logger.error("❌ CRITICAL FAILURE: Phone appears locked!")
                self.logger.error("=" * 70)
                self.logger.error(f"Detection reason: {lock_reason}")
                self.logger.error("")
                self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
                self.logger.error("=" * 70)
                return False

            self.logger.success("✓ Phone is unlocked")

            # All checks passed
            self.logger.info("=" * 70)
            self.logger.success("✅ VERIFICATION PASSED: WhatsApp is open and accessible")
            self.logger.info("=" * 70)
            return True

        except Exception as e:
            self.logger.error("=" * 70)
            self.logger.error("❌ CRITICAL FAILURE: Exception during verification!")
            self.logger.error("=" * 70)
            self.logger.error(f"Error: {e}")
            self.logger.error("")
            self.logger.error("⚠️  STOPPING to prevent accidental system UI interaction!")
            self.logger.error("=" * 70)
            return False

    def check_status(self):
        """Quick status check - shows package, activity, and visible chat count."""
        try:
            pkg = self.driver.current_package
            act = self.driver.current_activity
            self.logger.info(f"📱 Current Package: {pkg}")
            self.logger.info(f"📍 Current Activity: {act}")

            try:
                chats = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
                self.logger.info(f"💬 Visible Chats: {len(chats)}")
            except:
                self.logger.info("💬 Visible Chats: Unable to count (may not be on main screen)")

            if ".home" in act.lower() or "HomeActivity" in act:
                self.logger.success("On main chats screen")
            elif ".Conversation" in act or "Conversation" in act:
                self.logger.info("📝 In a conversation view")
            else:
                self.logger.warning("Unknown screen")
        except Exception as e:
            self.logger.error(f"Error checking status: {e}")

    def get_page_source(self, filename: str = "debug_page_source.xml"):
        """Dump current page source to XML file for inspection."""
        try:
            page_source = self.driver.page_source
            with open(filename, "w", encoding="utf-8") as f:
                f.write(page_source)
            self.logger.success(f"Page source saved to: {filename}")
            self.logger.debug_msg(f"Length: {len(page_source)} characters")
        except Exception as e:
            self.logger.error(f"Error saving page source: {e}")

    def list_visible_chats(self) -> List[str]:
        """List all currently visible chats on screen."""
        try:
            chats = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
            visible_chats = []
            self.logger.info(f"\n📋 Found {len(chats)} visible chats:")
            for i, chat in enumerate(chats, 1):
                try:
                    if chat.is_displayed():
                        name = chat.text.strip()
                        if name:
                            visible_chats.append(name)
                            self.logger.debug_msg(f"{i:2d}. {name}")
                except Exception as e:
                    self.logger.debug_msg(f"{i:2d}. [Error reading chat: {e}]")
            return visible_chats
        except Exception as e:
            self.logger.error(f"Error listing chats: {e}")
            return []

    def collect_all_chats(self, limit: Optional[int] = None, sort_alphabetical: bool = True) -> List[str]:
        """Scroll through entire chat list to collect all chats.

        Args:
            limit: Optional limit on number of chats to collect. If set, stops after collecting this many.
            sort_alphabetical: If True, sort chats alphabetically. If False, keep original order.
        """
        if limit:
            self.logger.info(f"Collecting chats (limited to {limit} for testing)...")
        else:
            self.logger.info("Collecting all chats by scrolling...")

        # Use dict.fromkeys() to preserve order and handle duplicates efficiently
        all_chats_dict = {}  # Preserves insertion order (Python 3.7+)
        previous_count = 0
        no_new_chats_count = 0
        scroll_attempts = 0
        max_scrolls = 50  # Safety limit
        current_time = time.time()

        # Scroll to top first - optimized to detect when at top
        self.logger.debug_msg("Scrolling to top...")
        previous_top_chat = None
        for i in range(5):
            try:
                self.driver.swipe(500, 800, 500, 1800, duration=300)  # Scroll up
                sleep(0.05)  # Reduced from 0.2 - minimal delay for UI update

                # Check if we're at the top (no movement means we're already there)
                current_top_chat = self._get_top_chat_name()
                if current_top_chat == previous_top_chat and previous_top_chat is not None:
                    self.logger.debug_msg("Reached top early - stopping scroll")
                    break
                previous_top_chat = current_top_chat
            except:
                break
        sleep(0.1)  # Reduced from 0.5 - brief settle time

        while scroll_attempts < max_scrolls:
            try:
                chats = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
                current_count = len(all_chats_dict)

                # Sort chats by Y position (top to bottom) to get visual order
                chats_with_position = []
                for chat in chats:
                    try:
                        if chat.is_displayed():
                            chat_name = chat.text.strip()
                            if chat_name:
                                location = chat.location
                                y_pos = location['y']
                                chats_with_position.append((y_pos, chat_name))
                    except:
                        continue

                # Sort by Y position (top to bottom)
                chats_with_position.sort(key=lambda x: x[0])

                # Add chats in visual order (top to bottom), skipping duplicates
                for y_pos, chat_name in chats_with_position:
                    if chat_name not in all_chats_dict:
                        all_chats_dict[chat_name] = y_pos  # Store position for reference
                        # Stop early if we've reached the limit
                        if limit and len(all_chats_dict) >= limit:
                            break

                # Check if we've reached the limit
                if limit and len(all_chats_dict) >= limit:
                    self.logger.debug_msg(f"Reached limit of {limit} chats. Stopping collection.")
                    break

                new_count = len(all_chats_dict)
                new_chats_this_round = new_count - current_count

                if new_chats_this_round > 0:
                    self.logger.debug_msg(f"Scroll {scroll_attempts + 1}: Found {new_chats_this_round} new chats (Total: {new_count})")
                    no_new_chats_count = 0
                else:
                    no_new_chats_count += 1
                    if no_new_chats_count >= 3:
                        self.logger.debug_msg(f"No new chats found after {no_new_chats_count} scrolls. Reached end.")
                        break

                # Scroll down
                self.driver.swipe(500, 1500, 500, 500, duration=300)
                sleep(0.5)
                scroll_attempts += 1
            except Exception as e:
                self.logger.error(f"Error during scroll {scroll_attempts + 1}: {e}")
                break

        # Scroll back to top after collection (ensures we start from known position)
        self.logger.debug_msg("Scrolling back to top after collection...")
        previous_top_chat = None
        for i in range(5):
            try:
                self.driver.swipe(500, 800, 500, 1800, duration=300)  # Scroll up
                sleep(0.05)  # Reduced from 0.2 - minimal delay for UI update

                # Check if we're at the top (no movement means we're already there)
                current_top_chat = self._get_top_chat_name()
                if current_top_chat == previous_top_chat and previous_top_chat is not None:
                    self.logger.debug_msg("Reached top early - stopping scroll")
                    break
                previous_top_chat = current_top_chat
            except:
                break
        sleep(0.1)  # Reduced from 0.5 - brief settle time

        # Convert dict keys to list (preserves insertion order)
        chat_list = list(all_chats_dict.keys())
        if sort_alphabetical:
            chat_list = sorted(chat_list)
        if limit:
            chat_list = chat_list[:limit]  # Ensure we don't exceed limit
            self.logger.success(f"Finished scrolling! Found {len(chat_list)} chats (limited to {limit} for testing)")
        else:
            self.logger.success(f"Finished scrolling! Found {len(chat_list)} total chats")
        return chat_list

    def click_chat(self, chat_name: str) -> bool:
        """Click into a specific chat by name. Uses smart scrolling to find chats that aren't visible."""
        self.logger.debug_msg(f"Clicking into chat '{chat_name}'...")
        try:
            # First, try to find the chat in current view
            target_chat = self._find_chat_in_view(chat_name)

            # If not found, use smart scrolling to locate it
            if not target_chat:
                self.logger.debug_msg(f"Chat '{chat_name}' not visible in current view, scrolling to find it...")
                target_chat = self._find_chat_with_scrolling(chat_name)

            if not target_chat:
                self.logger.error(f"Could not find chat '{chat_name}' after scrolling")
                return False

            # Try clicking parent row first
            try:
                parent_row = target_chat.find_element("xpath", "..")
                parent_row.click()
                self.logger.debug_msg("Clicked parent row")
            except Exception as parent_err:
                # Fallback: coordinate click
                location = target_chat.location
                size = target_chat.size
                center_x = location['x'] + size['width'] // 2
                center_y = location['y'] + size['height'] // 2
                self.logger.debug_msg(f"Using coordinate click at ({center_x}, {center_y})")
                self.driver.tap([(center_x, center_y)], duration=100)

            # Wait for navigation to conversation
            if self._wait_for_activity("Conversation", timeout=5):
                new_activity = self.driver.current_activity
                self.logger.debug_msg(f"After click, activity: {new_activity}")

                if ".Conversation" not in new_activity and "Conversation" not in new_activity:
                    self.logger.warning(f"Expected conversation view, got: {new_activity}")
            else:
                sleep(0.5)  # Brief fallback delay

            return True
        except Exception as e:
            self.logger.error(f"Error clicking into chat: {e}")
            return False

    def _find_chat_in_view(self, chat_name: str):
        """Find a chat element in the current viewport. Returns the element or None."""
        try:
            chats = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
            for chat in chats:
                try:
                    if chat.is_displayed() and chat.text.strip() == chat_name:
                        return chat
                except:
                    continue
        except Exception as e:
            self.logger.debug_msg(f"Error finding chat in view: {e}")
        return None

    def _get_top_chat_name(self) -> Optional[str]:
        """Get the name of the chat at the top of the visible list. Returns None if none found."""
        try:
            chats = self.driver.find_elements("id", "com.whatsapp:id/conversations_row_contact_name")
            chats_with_position = []
            for chat in chats:
                try:
                    if chat.is_displayed():
                        chat_name = chat.text.strip()
                        if chat_name:
                            location = chat.location
                            chats_with_position.append((location['y'], chat_name))
                except:
                    continue

            if chats_with_position:
                # Sort by Y position and get the top one
                chats_with_position.sort(key=lambda x: x[0])
                return chats_with_position[0][1]
        except Exception as e:
            self.logger.debug_msg(f"Error getting top chat: {e}")
        return None

    def _is_at_top(self, previous_top_chat: Optional[str]) -> bool:
        """Check if we're at the top of the list by comparing top chat before/after scroll."""
        current_top_chat = self._get_top_chat_name()
        if previous_top_chat and current_top_chat:
            return previous_top_chat == current_top_chat
        return False

    def _find_chat_with_scrolling(self, chat_name: str, max_scrolls: int = 240):
        """
        Scroll through the chat list to find a specific chat.
        First tries scrolling down once (since next chat is likely just below).
        If that fails, tries scrolling up first (since we're likely scrolled down), then down if needed.
        Detects when at top/bottom to prevent infinite scrolling.
        Returns the chat element or None.
        """
        self.logger.debug_msg(f"Searching for '{chat_name}' by scrolling...")

        # Optimization: Try scrolling down once first (next chat is likely just below)
        try:
            self.logger.debug_msg(f"Trying quick scroll down to find chat...")
            self.driver.swipe(500, 1500, 500, 500, duration=300)
            sleep(0.2)  # Brief pause to let UI update after scroll

            # Check if chat is now visible
            target_chat = self._find_chat_in_view(chat_name)
            if target_chat:
                self.logger.debug_msg(f"Found chat '{chat_name}' after quick scroll down")
                return target_chat
        except Exception as e:
            self.logger.debug_msg(f"Error during quick scroll down: {e}")

        # If quick scroll down didn't work, use full scroll strategy: try up first, then down
        scroll_directions = [
            ("up", lambda: self.driver.swipe(500, 800, 500, 1800, duration=300)),
            ("down", lambda: self.driver.swipe(500, 1500, 500, 500, duration=300))
        ]

        adaptive_max_scrolls = max_scrolls

        for direction_name, scroll_func in scroll_directions:
            self.logger.debug_msg(f"Scrolling {direction_name} to find chat...")

            # Get initial top chat for comparison
            previous_top_chat = self._get_top_chat_name()
            consecutive_no_change = 0
            max_no_change = 2  # Stop if we haven't moved after 2 scrolls

            # Scroll up/down to find the chat
            for scroll_attempt in range(adaptive_max_scrolls // 2):
                try:
                    # Check if chat is now visible
                    target_chat = self._find_chat_in_view(chat_name)
                    if target_chat:
                        self.logger.debug_msg(f"Found chat '{chat_name}' after scrolling {direction_name}")
                        return target_chat

                    # Check if we're stuck at top/bottom
                    current_top_chat = self._get_top_chat_name()
                    if previous_top_chat and current_top_chat == previous_top_chat:
                        consecutive_no_change += 1
                        if consecutive_no_change >= max_no_change:
                            self.logger.debug_msg(f"Reached {'top' if direction_name == 'up' else 'bottom'} of list, stopping {direction_name} scroll")
                            break
                    else:
                        consecutive_no_change = 0
                        previous_top_chat = current_top_chat

                    # Scroll in this direction
                    scroll_func()
                    sleep(0.2)  # Brief pause to let UI update after scroll

                except Exception as e:
                    self.logger.debug_msg(f"Error during scroll {direction_name}: {e}")
                    break

        # Final check after all scrolling
        result = self._find_chat_in_view(chat_name)
        return result

    def navigate_back_to_main(self):
        """Navigate back to main screen."""
        self.logger.debug_msg("Navigating back to main screen...")
        try:
            for i in range(3):
                current_activity = self.driver.current_activity
                if ".home" in current_activity.lower() or "HomeActivity" in current_activity:
                    break
                self.driver.press_keycode(4)

                # Wait for navigation to home or timeout
                if self._wait_for_activity("Home", timeout=2) or self._wait_for_activity("home", timeout=2):
                    break
                sleep(0.3)  # Brief delay between back presses

            sleep(0.5)  # Brief UI settle delay
        except Exception as e:
            self.logger.error(f"Error navigating back: {e}")

    def quit(self):
        """Close the driver session."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Driver session closed")
            except Exception as e:
                # Suppress "session already closed" errors - these are harmless
                error_msg = str(e)
                if "session is either terminated or not started" in error_msg.lower() or \
                   "invalidsessionid" in error_msg.lower():
                    self.logger.debug_msg("Driver session already closed")
                else:
                    # Log other errors that might be more serious
                    self.logger.debug_msg(f"Error closing driver: {e}")
        self.driver = None
