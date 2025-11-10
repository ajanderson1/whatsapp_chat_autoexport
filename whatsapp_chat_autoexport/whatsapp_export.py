#!/usr/bin/env python3
"""
WhatsApp Chat Auto-Export Script

Interactive script to export WhatsApp chats to Google Drive.
Supports both normal and debug modes.
"""

import argparse
import subprocess
import sys
import time
import os
import signal
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Set
from time import sleep

def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Chat Auto-Export - Export chats to Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Interactive mode (default, with media, alphabetical)
  %(prog)s --debug            # Interactive mode with debug output
  %(prog)s --skip-appium      # Skip starting Appium (assume it's running)
  %(prog)s --test             # Test mode: Limit to 10 chats (default)
  %(prog)s --test 5           # Test mode: Limit to 5 chats
  %(prog)s --test 20          # Test mode: Limit to 20 chats
  %(prog)s --with-media       # Export with media (default)
  %(prog)s --without-media    # Export without media
  %(prog)s --sort-order original  # Show chats in original WhatsApp order (default)
  %(prog)s --sort-order alphabetical  # Show chats alphabetically
  %(prog)s --resume /path/to/drive  # Skip chats already exported to Google Drive folder
  %(prog)s --all               # Auto-select all chats after 30 seconds if no input
  %(prog)s --wireless-adb 192.168.1.100:5555  # Connect via wireless ADB

For more information, visit: https://github.com/yourusername/whatsapp_chat_autoexport
        """
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose output)'
    )
    
    parser.add_argument(
        '--skip-appium',
        action='store_true',
        help='Skip starting Appium server (assume it\'s already running)'
    )
    
    parser.add_argument(
        '--test',
        type=int,
        nargs='?',
        const=10,
        default=None,
        metavar='N',
        help='Test mode: Limit to N chats for testing (default: 10 if --test used without number)'
    )
    
    media_group = parser.add_mutually_exclusive_group()
    media_group.add_argument(
        '--with-media',
        action='store_const',
        const=True,
        dest='include_media',
        help='Export chats with media (default)'
    )
    media_group.add_argument(
        '--without-media',
        action='store_const',
        const=False,
        dest='include_media',
        help='Export chats without media'
    )
    
    parser.add_argument(
        '--sort-order',
        choices=['alphabetical', 'original'],
        default='original',
        help='Sort order for chat list: "original" (default, order in WhatsApp) or "alphabetical"'
    )
    
    parser.add_argument(
        '--resume',
        type=str,
        metavar='DIR',
        help='Resume mode: Skip chats that already exist in the specified Google Drive root folder'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Auto-select all chats after 30 seconds if no input is provided'
    )
    
    parser.add_argument(
        '--wireless-adb',
        type=str,
        metavar='IP:PORT',
        help='Connect to device via wireless ADB. Format: IP:PORT (e.g., 192.168.1.100:5555). Device must already be paired via USB first.'
    )
    
    return parser

# Handle --help early so it works even if dependencies aren't installed
if '--help' in sys.argv or '-h' in sys.argv:
    parser = create_parser()
    parser.parse_args()  # This will print help and exit if --help was provided

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Create dummy color classes
    class Fore:
        GREEN = ""
        YELLOW = ""
        RED = ""
        CYAN = ""
        MAGENTA = ""
        RESET = ""
    class Style:
        RESET_ALL = ""
        BRIGHT = ""

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By


class Logger:
    """Simple logger with debug mode support and colored output."""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def _print(self, message: str, color: str = "", emoji: str = ""):
        """Print with color and emoji support."""
        if COLORAMA_AVAILABLE:
            print(f"{color}{emoji}{message}{Style.RESET_ALL}")
        else:
            print(f"{emoji}{message}")
    
    def info(self, message: str, emoji: str = ""):
        """Print info message."""
        self._print(message, Fore.CYAN, emoji)
    
    def success(self, message: str):
        """Print success message."""
        self._print(message, Fore.GREEN, "✅ ")
    
    def warning(self, message: str):
        """Print warning message."""
        self._print(message, Fore.YELLOW, "⚠️ ")
    
    def error(self, message: str):
        """Print error message."""
        self._print(message, Fore.RED, "❌ ")
    
    def debug_msg(self, message: str):
        """Print debug message (only if debug mode enabled)."""
        if self.debug:
            self._print(message, Fore.MAGENTA, "🔍 ")
    
    def step(self, step_num: int, message: str):
        """Print step message."""
        self.info(f"STEP {step_num}: {message}", "🔍 ")


def validate_resume_directory(directory_path: str, logger: Logger) -> Optional[Path]:
    """
    Validate resume directory path with robust validation.
    
    Args:
        directory_path: Directory path string to validate
        logger: Logger instance for output
        
    Returns:
        Path to validated directory, or None if validation fails
    """
    # Handle empty input
    if not directory_path:
        logger.error("Resume directory path is required")
        return None
    
    directory_path = directory_path.strip()
    
    # Expand user home directory (~)
    if directory_path.startswith('~'):
        directory_path = os.path.expanduser(directory_path)
    
    # Remove quotes if present
    directory_path = directory_path.strip('"').strip("'")
    
    # Convert to Path
    try:
        path_obj = Path(directory_path).resolve()
    except Exception as e:
        logger.error(f"Invalid resume directory path format: {e}")
        return None
    
    # Validate directory exists
    if not path_obj.exists():
        logger.error(f"Resume directory does not exist: {path_obj}")
        return None
    
    # Validate it's actually a directory
    if not path_obj.is_dir():
        logger.error(f"Resume path is not a directory: {path_obj}")
        return None
    
    # Validate readable
    if not os.access(path_obj, os.R_OK):
        logger.error(f"Resume directory is not readable: {path_obj}")
        return None
    
    logger.success(f"Resume directory validated: {path_obj}")
    return path_obj


def check_chat_exists(drive_folder: Path, chat_name: str) -> Tuple[bool, List[str]]:
    """
    Check if a chat export already exists in the Google Drive folder.
    
    Args:
        drive_folder: Path to Google Drive root folder
        chat_name: Name of the chat to check
        
    Returns:
        Tuple of (exists: bool, matching_files: List[str])
        - exists: True if chat export found, False otherwise
        - matching_files: List of matching file names found
    """
    matching_files = []
    pattern = f"WhatsApp Chat with {chat_name}"
    
    try:
        # Check for files matching the pattern (with or without .zip extension)
        all_files = [f for f in drive_folder.iterdir() if f.is_file()]
        
        for file_path in all_files:
            file_name = file_path.name
            
            # Check if file matches pattern (exact match)
            if file_name == pattern or file_name == f"{pattern}.zip":
                matching_files.append(file_name)
        
        return len(matching_files) > 0, matching_files
        
    except Exception as e:
        # If we can't check, assume it doesn't exist (safer to re-export)
        return False, []


class AppiumManager:
    """Manages Appium server lifecycle."""
    
    def __init__(self, logger: Logger):
        self.logger = logger
        self.appium_proc: Optional[subprocess.Popen] = None
        self.android_home = os.path.expanduser("~/Library/Android/sdk")
    
    def start_appium(self) -> bool:
        """Start Appium server."""
        self.logger.info("Setting up Android environment...")
        os.environ["ANDROID_HOME"] = self.android_home
        os.environ["ANDROID_SDK_ROOT"] = self.android_home
        self.logger.debug_msg(f"Set ANDROID_HOME to: {self.android_home}")
        
        self.logger.info("Stopping any existing Appium instances...")
        subprocess.run("pkill -f appium || true", shell=True)
        
        self.logger.info("Starting Appium server...")
        appium_env = os.environ.copy()
        try:
            self.appium_proc = subprocess.Popen(
                ["appium", "-a", "127.0.0.1", "-p", "4723"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=appium_env
            )
            time.sleep(5)  # Wait for Appium to start
            
            # Verify it's running
            result = subprocess.run(
                ["curl", "-s", "http://127.0.0.1:4723/wd/hub/status"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.logger.success("Appium server started successfully")
                return True
            else:
                self.logger.error("Could not verify Appium server status")
                return False
        except Exception as e:
            self.logger.error(f"Failed to start Appium: {e}")
            return False
    
    def stop_appium(self):
        """Stop Appium server."""
        if self.appium_proc:
            self.logger.info("Stopping Appium server...")
            self.appium_proc.terminate()
            try:
                self.appium_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.appium_proc.kill()
            self.appium_proc = None
        else:
            # Try to kill any Appium process
            subprocess.run("pkill -f appium || true", shell=True)


class WhatsAppDriver:
    """Manages WhatsApp connection and navigation."""
    
    def __init__(self, logger: Logger, wireless_adb: Optional[str] = None):
        self.logger = logger
        self.driver: Optional[webdriver.Remote] = None
        self.default_wait_timeout = 10  # Default timeout for explicit waits
        self.wireless_adb = wireless_adb
    
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
        """Check if Android device is connected."""
        self.logger.info("Checking device connection...")
        
        # If wireless ADB is specified, connect to it first
        if self.wireless_adb:
            self.logger.info(f"Connecting to wireless ADB at {self.wireless_adb}...")
            try:
                result = subprocess.run(
                    ["adb", "connect", self.wireless_adb],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
                        self.logger.success(f"Connected to wireless ADB at {self.wireless_adb}")
                        self.logger.debug_msg(f"ADB connect output: {result.stdout}")
                    else:
                        self.logger.warning(f"Wireless ADB connection output: {result.stdout}")
                else:
                    self.logger.error(f"Failed to connect to wireless ADB: {result.stderr}")
                    return False
                # Give ADB a moment to register the connection
                sleep(1)
            except Exception as e:
                self.logger.error(f"Error connecting to wireless ADB: {e}")
                return False
        
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True
            )
            if "device\n" in result.stdout:
                self.logger.success("Device connected")
                self.logger.debug_msg(f"ADB output: {result.stdout}")
                return True
            else:
                self.logger.error("No device found")
                if self.wireless_adb:
                    self.logger.error(f"Make sure your device is on the same network and wireless debugging is enabled.")
                    self.logger.error(f"If this is the first time, you may need to pair via USB first using:")
                    self.logger.error(f"  adb pair <IP>:<PAIRING_PORT>")
                    self.logger.error(f"  adb connect {self.wireless_adb}")
                return False
        except Exception as e:
            self.logger.error(f"Error checking device: {e}")
            return False
    
    def connect(self) -> bool:
        """Connect to WhatsApp via Appium."""
        self.logger.info("Stopping WhatsApp (this does NOT delete any data)...")
        subprocess.run(["adb", "shell", "am", "force-stop", "com.whatsapp"], capture_output=True)
        sleep(0.5)  # Brief delay for app to stop (system command, not UI)
        self.logger.success("WhatsApp stopped")
        
        self.logger.info("Setting up WebDriver options...")
        options = UiAutomator2Options()
        options.load_capabilities({
            "platformName": "Android",
            "deviceName": "Pixel_10_Pro",
            "automationName": "UiAutomator2",
            "appPackage": "com.whatsapp",
            "appActivity": "com.whatsapp.Main",
            "noReset": True,
            "fullReset": False
        })
        
        self.logger.info("Connecting to Appium server...")
        try:
            self.driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
            self.logger.success("Driver connected successfully!")
            
            # Wait a moment for app to start, then check package
            sleep(2)  # Give app time to launch
            
            # Check package name directly (more reliable than activity)
            current_package = self.driver.current_package
            self.logger.debug_msg(f"Current package after launch: {current_package}")
            
            if current_package == "com.whatsapp":
                self.logger.success("WhatsApp is open!")
                return True
            else:
                self.logger.warning(f"WhatsApp package not detected. Current: {current_package}")
                
                # Try waiting for activity as fallback
                if self._wait_for_activity("Main", timeout=5):
                    current_package = self.driver.current_package
                    if current_package == "com.whatsapp":
                        self.logger.success("WhatsApp is open!")
                        return True
            
            # Try activating WhatsApp if not detected
            try:
                self.logger.info("Attempting to activate WhatsApp...")
                self.driver.activate_app("com.whatsapp")
                sleep(2)  # Brief wait after activation
                current_package = self.driver.current_package
                self.logger.debug_msg(f"After activation, package: {current_package}")
                if current_package == "com.whatsapp":
                    self.logger.success("WhatsApp activated successfully!")
                    return True
                else:
                    self.logger.warning(f"Package still not correct after activation: {current_package}")
            except Exception as e:
                self.logger.error(f"Could not activate WhatsApp: {e}")
            
            # Final check - sometimes it takes a moment
            sleep(1)
            current_package = self.driver.current_package
            if current_package == "com.whatsapp":
                self.logger.success("WhatsApp detected on final check!")
                return True
            
            return False
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
                self.logger.error(f"Error closing driver: {e}")


class ChatExporter:
    """Handles chat export operations."""
    
    def __init__(self, driver: WhatsAppDriver, logger: Logger):
        self.driver = driver
        self.logger = logger
        # Cache for element finding strategies: {screen_type: (locator_type, locator_value)}
        self._element_strategy_cache: Dict[str, Tuple[str, str]] = {}
    
    def _is_share_dialog_visible(self) -> bool:
        """
        Check if the share dialog is currently visible.
        This helps detect when WhatsApp skips media selection for text-only chats.
        
        Returns True if share dialog is detected, False otherwise.
        """
        try:
            # Check current package - share dialog uses com.android.intentresolver
            current_package = self.driver.driver.current_package
            if current_package == "com.android.intentresolver":
                self.logger.debug_msg("Share dialog detected by package name")
                return True
            
            # Check for share dialog indicators in UI
            all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
            for elem in all_text_elements:
                try:
                    if elem.is_displayed():
                        text = elem.text.strip().lower()
                        # Look for "Sharing X file" text that appears in share dialog
                        if "sharing" in text and ("file" in text or "files" in text):
                            self.logger.debug_msg(f"Share dialog detected by text: '{elem.text.strip()}'")
                            return True
                        # Also check for "My Drive" which appears in share dialog
                        if text == "my drive":
                            self.logger.debug_msg("Share dialog detected by 'My Drive' text")
                            return True
                except:
                    continue
            
            # Check for share dialog container elements
            try:
                # Share dialog has specific resource IDs
                share_containers = self.driver.driver.find_elements("xpath", "//*[@resource-id='com.android.intentresolver:id/chooser_scrollable_container'] | //*[@resource-id='android:id/resolver_list']")
                if share_containers and any(elem.is_displayed() for elem in share_containers):
                    self.logger.debug_msg("Share dialog detected by container elements")
                    return True
            except:
                pass
                
        except Exception as e:
            self.logger.debug_msg(f"Error checking for share dialog: {e}")
        
        return False
    
    def _handle_advanced_chat_privacy_error(self, chat_name: str) -> bool:
        """
        Check for and handle the advanced chat privacy error dialog.
        This dialog appears when a chat has advanced privacy settings enabled that prevent export.
        
        Returns True if error dialog was detected and handled (chat should be skipped), False otherwise.
        """
        try:
            # Look for error dialog indicators
            all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
            error_dialog_detected = False
            
            for elem in all_text_elements:
                try:
                    if elem.is_displayed():
                        text = elem.text.strip().lower()
                        # Look for error message about advanced chat privacy
                        if ("advanced chat privacy" in text or 
                            "can't export chats" in text or
                            "prevents the exporting" in text or
                            "cannot export" in text):
                            error_dialog_detected = True
                            self.logger.warning(f"Advanced chat privacy error detected: '{elem.text.strip()}'")
                            break
                except:
                    continue
            
            if not error_dialog_detected:
                return False
            
            # Error dialog detected - find and click OK button
            self.logger.warning(f"Advanced chat privacy prevents export of '{chat_name}'")
            self.logger.info("Looking for OK button in error dialog...")
            
            ok_button = None
            
            # Strategy 1: Look for button with "OK" text
            try:
                all_buttons = self.driver.driver.find_elements("xpath", "//android.widget.Button")
                for btn in all_buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            button_text = btn.text.strip().lower()
                            if button_text == "ok":
                                ok_button = btn
                                self.logger.debug_msg("Found OK button by text")
                                break
                    except:
                        continue
            except Exception as e:
                self.logger.debug_msg(f"Strategy 1 failed: {e}")
            
            # Strategy 2: Look for clickable containers with "OK" text
            if not ok_button:
                try:
                    clickable_elements = self.driver.driver.find_elements("xpath", "//android.widget.LinearLayout[@clickable='true'] | //android.widget.RelativeLayout[@clickable='true'] | //android.widget.FrameLayout[@clickable='true']")
                    for elem in clickable_elements:
                        try:
                            if elem.is_displayed() and elem.is_enabled():
                                text_views = elem.find_elements("xpath", ".//android.widget.TextView")
                                for tv in text_views:
                                    try:
                                        text = tv.text.strip().lower()
                                        if text == "ok":
                                            ok_button = elem
                                            self.logger.debug_msg("Found OK button in container")
                                            break
                                    except:
                                        continue
                                if ok_button:
                                    break
                        except:
                            continue
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 2 failed: {e}")
            
            # Strategy 3: Look for TextView with "OK" text and find its clickable parent
            if not ok_button:
                try:
                    for elem in all_text_elements:
                        try:
                            if elem.is_displayed():
                                text = elem.text.strip().lower()
                                if text == "ok":
                                    # Try to find clickable parent
                                    try:
                                        parent = elem.find_element("xpath", "..")
                                        if parent.get_attribute("clickable") == "true":
                                            ok_button = parent
                                            self.logger.debug_msg("Found OK button via TextView parent")
                                            break
                                    except:
                                        # If parent isn't clickable, try clicking the TextView itself
                                        ok_button = elem
                                        self.logger.debug_msg("Using TextView directly as OK button")
                                        break
                        except:
                            continue
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 3 failed: {e}")
            
            if ok_button:
                try:
                    ok_button.click()
                    sleep(0.5)  # Brief delay after clicking OK
                    self.logger.info("Clicked OK button in error dialog")
                except Exception as e:
                    self.logger.debug_msg(f"Error clicking OK button: {e}")
                    # Try pressing back as fallback
                    self.driver.driver.press_keycode(4)
                    sleep(0.5)
            else:
                # If we can't find OK button, try pressing back as fallback
                self.logger.warning("Could not find OK button, using back button as fallback")
                self.driver.driver.press_keycode(4)
                sleep(0.5)
            
            # Close any remaining menus/dialogs and return to main screen
            self.logger.info("Closing menus and returning to main screen...")
            for _ in range(3):  # Press back up to 3 times to ensure we're back
                try:
                    current_activity = self.driver.driver.current_activity
                    if ".home" in current_activity.lower() or "HomeActivity" in current_activity:
                        break
                    self.driver.driver.press_keycode(4)
                    sleep(0.3)
                except:
                    break
            
            self.logger.info("Returned to main screen (skipped due to advanced chat privacy)")
            return True  # Error dialog was handled, chat should be skipped
            
        except Exception as e:
            self.logger.debug_msg(f"Error checking for advanced chat privacy dialog: {e}")
            return False  # If we can't check properly, assume no error dialog
    
    def _wait_for_share_dialog(self, max_retries: int = 7) -> bool:
        """
        Wait for share dialog to appear after selecting media option.
        Uses exponential backoff with retries.
        
        Returns True if share dialog appears, False if it doesn't appear after retries.
        """
        for attempt in range(max_retries):
            # Exponential backoff: 2s, 4s, 8s, 16s, 32s, 64s, 90s (capped at 90)
            wait_time = min(2 ** (attempt + 1), 90)
            self.logger.debug_msg(f"Waiting for share dialog (attempt {attempt + 1}/{max_retries}, waiting {wait_time}s)...")
            sleep(wait_time)
            
            if self._is_share_dialog_visible():
                return True
                    
        self.logger.warning(f"Share dialog did not appear after {max_retries} attempts")
        return False
    
    def export_chat_to_google_drive(self, chat_name: str, include_media: bool = True) -> bool:
        """
        Export a chat to Google Drive with or without media.
        
        This function assumes you're already in the conversation view for the chat.
        
        Args:
            chat_name: Name of the chat being exported
            include_media: If True, export with media; if False, export without media
        
        Returns True if export initiated successfully, False if skipped (community chat).
        """
        media_status = "with media" if include_media else "without media"
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"📤 EXPORTING CHAT: '{chat_name}' ({media_status})")
        self.logger.info(f"{'='*70}")
        
        # STEP 1: Open three-dot menu
        self.logger.step(1, "Opening menu...")
        try:
            sleep(0.5)  # Brief UI settle delay after entering chat
            
            menu_button = None
            screen_type = "menu_button"
            
            # Check cache first
            if screen_type in self._element_strategy_cache:
                cached_locator_type, cached_locator_value = self._element_strategy_cache[screen_type]
                self.logger.debug_msg(f"Trying cached strategy: {cached_locator_type}={cached_locator_value}")
                try:
                    menu_button = self.driver._wait_for_element(
                        cached_locator_type, cached_locator_value, timeout=5, expected_condition="visible"
                    )
                    if menu_button:
                        self.logger.debug_msg(f"Found menu button using cached strategy: {cached_locator_type}")
                except Exception as e:
                    self.logger.debug_msg(f"Cached strategy failed: {e}")
            
            # Strategy 1: Try by resource ID (wait for element)
            if not menu_button:
                try:
                    menu_button = self.driver._wait_for_element(
                        "id", "com.whatsapp:id/menuitem_overflow", timeout=5, expected_condition="visible"
                    )
                    if menu_button:
                        self.logger.debug_msg("Found menu button by resource ID")
                        # Cache successful strategy
                        self._element_strategy_cache[screen_type] = ("id", "com.whatsapp:id/menuitem_overflow")
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 1 failed: {e}")
            
            # Strategy 2: Try by content description
            if not menu_button:
                try:
                    menu_buttons = self.driver.driver.find_elements("xpath", "//*[@content-desc='More options']")
                    for btn in menu_buttons:
                        if btn.is_displayed():
                            menu_button = btn
                            self.logger.debug_msg("Found menu button by content description")
                            # Cache successful strategy
                            self._element_strategy_cache[screen_type] = ("xpath", "//*[@content-desc='More options']")
                            break
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 2 failed: {e}")
            
            # Strategy 3: Try by accessibility ID
            if not menu_button:
                try:
                    menu_button = self.driver._wait_for_element(
                        "accessibility_id", "More options", timeout=3, expected_condition="visible"
                    )
                    if menu_button:
                        self.logger.debug_msg("Found menu button by accessibility ID")
                        # Cache successful strategy
                        self._element_strategy_cache[screen_type] = ("accessibility_id", "More options")
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 3 failed: {e}")
            
            # Strategy 4: Try to find ImageView/ImageButton in top right area
            if not menu_button:
                try:
                    size = self.driver.driver.get_window_size()
                    screen_width = size['width']
                    right_area_x = screen_width - 200
                    
                    all_elements = self.driver.driver.find_elements("xpath", "//android.widget.ImageView | //android.widget.ImageButton")
                    for elem in all_elements:
                        try:
                            if elem.is_displayed() and elem.is_enabled():
                                location = elem.location
                                if location['x'] > right_area_x and location['y'] < 400:
                                    menu_button = elem
                                    self.logger.debug_msg(f"Found potential menu button at ({location['x']}, {location['y']})")
                                    # Note: This strategy is position-based, don't cache it
                                    break
                        except:
                            continue
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 4 failed: {e}")
            
            if not menu_button:
                # Clear cache on failure to allow retry with different strategies
                if screen_type in self._element_strategy_cache:
                    del self._element_strategy_cache[screen_type]
                raise Exception("Could not locate three-dot menu button")
            
            if not menu_button.is_enabled():
                raise Exception("Menu button found but not enabled!")
            
            menu_button.click()
            sleep(0.5)  # Brief delay for menu animation
            self.logger.success("Menu opened")
            
        except Exception as e:
            self.logger.error(f"ERROR opening menu: {e}")
            # Clear cache on navigation errors
            if "menu_button" in self._element_strategy_cache:
                del self._element_strategy_cache["menu_button"]
            self.driver.get_page_source(f"menu_error_{chat_name}.xml")
            raise
        
        # STEP 2: Click "More"
        self.logger.step(2, "Looking for 'More' option...")
        try:
            sleep(0.3)  # Brief delay for menu to fully render
            
            more_option = None
            
            # Find by text content
            try:
                all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
                for elem in all_text_elements:
                    try:
                        if elem.is_displayed():
                            text = elem.text.strip()
                            if text and text.lower() == "more":
                                more_option = elem
                                self.logger.debug_msg(f"Found 'More' option: '{text}'")
                                break
                    except:
                        continue
            except Exception as e:
                self.logger.debug_msg(f"Strategy failed: {e}")
            
            # Try finding clickable items in menu
            if not more_option:
                try:
                    menu_items = self.driver.driver.find_elements("xpath", "//android.widget.LinearLayout[contains(@resource-id, 'menu')] | //android.widget.RelativeLayout[contains(@resource-id, 'menu')]")
                    for item in menu_items:
                        try:
                            if item.is_displayed():
                                text_views = item.find_elements("xpath", ".//android.widget.TextView")
                                for tv in text_views:
                                    try:
                                        text = tv.text.strip()
                                        if text and text.lower() == "more":
                                            more_option = item
                                            self.logger.debug_msg("Found 'More' option in menu item")
                                            break
                                    except:
                                        continue
                                if more_option:
                                    break
                        except:
                            continue
                except Exception as e:
                    self.logger.debug_msg(f"Strategy 2 failed: {e}")
            
            if not more_option:
                # This is likely a community chat
                self.logger.warning("Could not find 'More' option - likely a community chat")
                self.driver.driver.press_keycode(4)  # Close menu
                sleep(0.3)
                self.driver.driver.press_keycode(4)  # Go back to main screen
                sleep(0.5)
                self.logger.info("Returned to main screen (skipped community chat)")
                return False  # Skip this chat
            
            more_option.click()
            sleep(0.5)  # Brief delay for submenu to appear
            self.logger.success("'More' clicked")
            
        except Exception as e:
            self.logger.error(f"ERROR clicking 'More': {e}")
            self.driver.get_page_source(f"more_error_{chat_name}.xml")
            raise
        
        # STEP 3: Click "Export chat"
        self.logger.step(3, "Looking for 'Export chat' option...")
        try:
            sleep(0.3)  # Brief delay for submenu to render
            
            export_option = None
            
            all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
            for elem in all_text_elements:
                try:
                    if elem.is_displayed():
                        text = elem.text.strip()
                        if text and ("export" in text.lower() or "export chat" in text.lower()):
                            export_option = elem
                            self.logger.debug_msg(f"Found 'Export chat' option: '{text}'")
                            break
                except:
                    continue
            
            if not export_option:
                # Export option not available
                self.logger.warning("Could not find 'Export chat' option - this chat may not support export")
                self.logger.info("Closing menus and returning to main screen...")
                self.driver.driver.press_keycode(4)  # Close submenu
                sleep(0.3)
                self.driver.driver.press_keycode(4)  # Close main menu
                sleep(0.3)
                self.driver.driver.press_keycode(4)  # Go back to main screen
                sleep(0.5)
                self.logger.info("Returned to main screen (skipped - export not available)")
                return False  # Skip this chat
            
            export_option.click()
            sleep(0.5)  # Brief delay for export dialog
            self.logger.success("'Export chat' clicked")
            
        except Exception as e:
            self.logger.error(f"ERROR clicking 'Export chat': {e}")
            self.driver.get_page_source(f"export_error_{chat_name}.xml")
            raise
        
        # Check for advanced chat privacy error dialog
        if self._handle_advanced_chat_privacy_error(chat_name):
            # Error dialog was detected and handled - skip this chat
            return False
        
        # STEP 4: Select media option (Include or Without) OR detect text-only chat
        media_option_name = "Include media" if include_media else "Without media"
        self.logger.step(4, f"Selecting '{media_option_name}' or detecting text-only chat...")
        try:
            sleep(0.5)  # Brief delay for export dialog to appear
            
            # First, check if share dialog appeared immediately (text-only chat)
            if self._is_share_dialog_visible():
                self.logger.info("Share dialog detected immediately - this appears to be a text-only chat")
                self.logger.info("WhatsApp skipped media selection (no media in this chat)")
                self.logger.success("Proceeding directly to share dialog selection")
                # Skip media selection step and go directly to STEP 5
            else:
                # Media selection dialog should appear - proceed with normal flow
                self.logger.debug_msg("Media selection dialog expected - searching for options...")
                
                media_option = None
                
                # Comprehensive scan
                all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
                clickable_buttons = self.driver.driver.find_elements("xpath", "//android.widget.Button")
                clickable_containers = self.driver.driver.find_elements("xpath", "//android.widget.LinearLayout[@clickable='true'] | //android.widget.RelativeLayout[@clickable='true'] | //android.widget.FrameLayout[@clickable='true']")
                
                # Strategy 1: Check buttons
                for btn in clickable_buttons:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            text = btn.text.strip().lower()
                            if include_media:
                                # Looking for "include media" (not "without")
                                if "include" in text and "media" in text and "without" not in text:
                                    media_option = btn
                                    self.logger.debug_msg(f"Found in button: '{btn.text.strip()}'")
                                    break
                            else:
                                # Looking for "without media"
                                if "without" in text and "media" in text:
                                    media_option = btn
                                    self.logger.debug_msg(f"Found in button: '{btn.text.strip()}'")
                                    break
                    except:
                        continue
                
                # Strategy 2: Check containers
                if not media_option:
                    for container in clickable_containers:
                        try:
                            if container.is_displayed() and container.is_enabled():
                                text_views = container.find_elements("xpath", ".//android.widget.TextView")
                                for tv in text_views:
                                    try:
                                        text = tv.text.strip().lower()
                                        if include_media:
                                            # Looking for "include media" (not "without")
                                            if "include" in text and "media" in text and "without" not in text:
                                                media_option = container
                                                self.logger.debug_msg(f"Found in container: '{tv.text.strip()}'")
                                                break
                                        else:
                                            # Looking for "without media"
                                            if "without" in text and "media" in text:
                                                media_option = container
                                                self.logger.debug_msg(f"Found in container: '{tv.text.strip()}'")
                                                break
                                    except:
                                        continue
                                if media_option:
                                    break
                        except:
                            continue
                
                # Strategy 3: Look for options by position (if first is "Without media", second is "Include media")
                if not media_option:
                    all_options = []
                    for container in clickable_containers:
                        try:
                            if container.is_displayed() and container.is_enabled():
                                text_views = container.find_elements("xpath", ".//android.widget.TextView")
                                for tv in text_views:
                                    try:
                                        text = tv.text.strip().lower()
                                        if "media" in text:
                                            all_options.append((container, text, tv.text.strip()))
                                            break
                                    except:
                                        continue
                        except:
                            continue
                    
                    if len(all_options) >= 2:
                        all_options.sort(key=lambda x: x[0].location['y'])
                        # First option is typically "Without media", second is "Include media"
                        if include_media and len(all_options) >= 2:
                            # Want second option (Include media)
                            media_option, _, option_text = all_options[1]
                            self.logger.debug_msg(f"Selected second option by position: '{option_text}'")
                        elif not include_media and len(all_options) >= 1:
                            # Want first option (Without media)
                            media_option, _, option_text = all_options[0]
                            self.logger.debug_msg(f"Selected first option by position: '{option_text}'")
                
                # If we still haven't found media option, check again if share dialog appeared
                if not media_option:
                    sleep(0.5)  # Brief wait
                    if self._is_share_dialog_visible():
                        self.logger.info("Share dialog detected - WhatsApp skipped media selection (text-only chat)")
                        self.logger.success("Proceeding directly to share dialog selection")
                        # Skip media selection step and go directly to STEP 5
                    else:
                        raise Exception(f"Could not locate '{media_option_name}' option and share dialog not detected")
                else:
                    media_option.click()
                    self.logger.success(f"'{media_option_name}' clicked")
                    
                    # Wait for share dialog with exponential backoff
                    self.logger.info("Waiting for share dialog to initialize...")
                    if not self._wait_for_share_dialog():
                        self.logger.warning("Share dialog may not have appeared, but continuing...")
                    else:
                        self.logger.success("Share dialog ready")
            
        except Exception as e:
            self.logger.error(f"ERROR selecting '{media_option_name}': {e}")
            self.driver.get_page_source(f"media_option_error_{chat_name}.xml")
            raise
        
        # STEP 5: Select "Drive" (Google Drive)
        self.logger.step(5, "Selecting 'Drive' (Google Drive)...")
        try:
            sleep(0.5)  # Brief delay for share dialog to fully render
            
            google_drive_option = None
            
            # Helper function to find "Drive" option
            def find_drive_option():
                all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
                clickable_elements = self.driver.driver.find_elements("xpath", "//android.widget.LinearLayout[@clickable='true'] | //android.widget.RelativeLayout[@clickable='true'] | //android.widget.Button")
                
                # Strategy 1: Look for "Drive" in text elements
                for elem in all_text_elements:
                    try:
                        if elem.is_displayed():
                            text = elem.text.strip()
                            if text and text.lower() == "drive":
                                if elem.is_enabled() or elem.is_displayed():
                                    self.logger.debug_msg(f"Found 'Drive': '{text}'")
                                    return elem
                    except:
                        continue
                
                # Strategy 2: Look for "Drive" in clickable containers
                for elem in clickable_elements:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            text_views = elem.find_elements("xpath", ".//android.widget.TextView")
                            for tv in text_views:
                                try:
                                    text = tv.text.strip()
                                    if text and text.lower() == "drive":
                                        self.logger.debug_msg(f"Found 'Drive' in container: '{text}'")
                                        return elem
                                except:
                                    continue
                    except:
                        continue
                
                # Strategy 3: Fallback to "My Drive"
                for elem in all_text_elements:
                    try:
                        if elem.is_displayed():
                            text = elem.text.strip()
                            if text and text.lower() == "my drive":
                                if elem.is_enabled() or elem.is_displayed():
                                    self.logger.debug_msg(f"Found 'My Drive' (fallback): '{text}'")
                                    return elem
                    except:
                        continue
                
                # Strategy 4: Look for "My Drive" in clickable containers
                for elem in clickable_elements:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            text_views = elem.find_elements("xpath", ".//android.widget.TextView")
                            for tv in text_views:
                                try:
                                    text = tv.text.strip()
                                    if text and text.lower() == "my drive":
                                        self.logger.debug_msg(f"Found 'My Drive' in container (fallback): '{text}'")
                                        return elem
                                except:
                                    continue
                    except:
                        continue
                
                return None
            
            # First attempt: try to find "Drive" without swiping
            google_drive_option = find_drive_option()
            
            # If not found, swipe up from bottom to make it visible
            if not google_drive_option:
                self.logger.debug_msg("'Drive' not immediately visible, swiping up from bottom...")
                window_size = self.driver.driver.get_window_size()
                screen_height = window_size['height']
                screen_width = window_size['width']
                
                # Swipe up from near bottom (swipe from Y=high to Y=low to scroll content up)
                # Try up to 3 times
                max_swipes = 3
                for swipe_attempt in range(max_swipes):
                    # Swipe from bottom (high Y) to top (low Y) to scroll content up
                    start_y = int(screen_height * 0.85)  # Near bottom
                    end_y = int(screen_height * 0.35)    # Upper portion
                    center_x = screen_width // 2
                    
                    self.driver.driver.swipe(center_x, start_y, center_x, end_y, duration=300)
                    sleep(0.5)  # Brief delay for UI to update
                    
                    # Try to find "Drive" again
                    google_drive_option = find_drive_option()
                    if google_drive_option:
                        self.logger.debug_msg(f"Found 'Drive' after {swipe_attempt + 1} swipe(s)")
                        break
                    else:
                        self.logger.debug_msg(f"Swipe {swipe_attempt + 1}/{max_swipes} - 'Drive' still not found")
            
            if not google_drive_option:
                raise Exception("Could not locate 'Drive' option after swiping")
            
            # Verification
            verification_text = None
            try:
                if google_drive_option.tag_name == "android.widget.TextView":
                    verification_text = google_drive_option.text.strip()
                else:
                    text_views = google_drive_option.find_elements("xpath", ".//android.widget.TextView")
                    for tv in text_views:
                        try:
                            text = tv.text.strip()
                            if text and len(text) > 0:
                                verification_text = text
                                if "drive" in text.lower():
                                    break
                        except:
                            continue
            except:
                pass
            
            if verification_text:
                verification_text_lower = verification_text.lower()
                if "drive" not in verification_text_lower:
                    raise Exception(f"VERIFICATION FAILED: Not Google Drive! Got '{verification_text}'")
                if "external" in verification_text_lower or "usb" in verification_text_lower or "sd card" in verification_text_lower:
                    raise Exception(f"VERIFICATION FAILED: This is a physical drive, not Google Drive! Got '{verification_text}'")
                self.logger.debug_msg(f"Verified: '{verification_text}' is Google Drive")
            
            google_drive_option.click()
            sleep(0.5)  # Brief delay for Google Drive to open
            self.logger.success("'Drive' selected - Google Drive window should now be opening")
            
        except Exception as e:
            self.logger.error(f"ERROR selecting 'Drive': {e}")
            self.driver.get_page_source(f"google_drive_error_{chat_name}.xml")
            raise
        
        # Wait for Google Drive window to appear
        self.logger.debug_msg("Waiting for Google Drive window to appear...")
        sleep(1.0)  # Initial wait for window transition
        
        # Check if we're now in Google Drive (package change or activity change)
        try:
            current_package = self.driver.driver.current_package
            current_activity = self.driver.driver.current_activity
            self.logger.debug_msg(f"After clicking Drive - Package: {current_package}, Activity: {current_activity}")
            
            # Google Drive package is typically com.google.android.apps.drive
            if "drive" in current_package.lower() or "drive" in current_activity.lower():
                self.logger.debug_msg("Google Drive window detected")
            else:
                # Wait a bit more for transition
                sleep(1.0)
                current_package = self.driver.driver.current_package
                current_activity = self.driver.driver.current_activity
                self.logger.debug_msg(f"After additional wait - Package: {current_package}, Activity: {current_activity}")
        except Exception as e:
            self.logger.debug_msg(f"Could not check package/activity: {e}")
        
        # STEP 6: Click "Upload" button in top right
        self.logger.step(6, "Clicking 'Upload' button in Google Drive window...")
        try:
            sleep(0.5)  # Brief delay for Google Drive window to fully render
            
            upload_button = None
            window_size = self.driver.driver.get_window_size()
            screen_width = window_size['width']
            screen_height = window_size['height']
            
            # Define top right area (rightmost 30% of screen width, top 15% of screen height)
            top_right_x_min = int(screen_width * 0.7)
            top_right_y_max = int(screen_height * 0.15)
            
            # Strategy 1: Try by resource ID (most reliable - com.google.android.apps.docs:id/save_button)
            try:
                upload_button = self.driver._wait_for_element(
                    "id", "com.google.android.apps.docs:id/save_button", timeout=3, expected_condition="visible"
                )
                if upload_button:
                    # Verify it has "Upload" text
                    try:
                        button_text = upload_button.text.strip().lower()
                        if button_text == "upload":
                            self.logger.debug_msg(f"Found 'Upload' button by resource ID: '{upload_button.text}'")
                        else:
                            upload_button = None  # Wrong button
                    except:
                        pass
            except Exception as e:
                self.logger.debug_msg(f"Strategy 1 (resource ID) failed: {e}")
            
            # Strategy 2: Look for Button elements with "Upload" text in top right area
            if not upload_button:
                all_buttons = self.driver.driver.find_elements("xpath", "//android.widget.Button")
                for elem in all_buttons:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            # Check button's own text attribute
                            button_text = elem.text.strip().lower()
                            if button_text == "upload":
                                location = elem.location
                                # Check if in top right area (or just accept if text matches)
                                if location['x'] >= top_right_x_min and location['y'] <= top_right_y_max:
                                    upload_button = elem
                                    self.logger.debug_msg(f"Found 'Upload' button by Button.text at ({location['x']}, {location['y']})")
                                    break
                                else:
                                    # Still accept if text matches (may be slightly outside area)
                                    upload_button = elem
                                    self.logger.debug_msg(f"Found 'Upload' button by Button.text at ({location['x']}, {location['y']}) - position check relaxed")
                                    break
                    except:
                        continue
            
            # Strategy 3: Look for "Upload" text in TextView elements in top right area
            if not upload_button:
                all_text_elements = self.driver.driver.find_elements("xpath", "//android.widget.TextView")
                for elem in all_text_elements:
                    try:
                        if elem.is_displayed():
                            text = elem.text.strip().lower()
                            if text == "upload":
                                location = elem.location
                                if location['x'] >= top_right_x_min and location['y'] <= top_right_y_max:
                                    # Try to find parent button or clickable container
                                    try:
                                        parent = elem.find_element("xpath", "..")
                                        if parent.tag_name == "android.widget.Button" and parent.is_enabled():
                                            upload_button = parent
                                            self.logger.debug_msg(f"Found 'Upload' button via TextView parent at ({location['x']}, {location['y']})")
                                            break
                                    except:
                                        pass
                    except:
                        continue
            
            # Strategy 4: Look for "Upload" in clickable containers (buttons, ImageButtons)
            if not upload_button:
                clickable_elements = self.driver.driver.find_elements("xpath", "//android.widget.Button | //android.widget.ImageButton | //android.widget.ImageView[@clickable='true']")
                for elem in clickable_elements:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            location = elem.location
                            # Check if in top right area
                            if location['x'] >= top_right_x_min and location['y'] <= top_right_y_max:
                                # Check if it contains "Upload" text in child TextViews
                                text_views = elem.find_elements("xpath", ".//android.widget.TextView")
                                for tv in text_views:
                                    try:
                                        text = tv.text.strip().lower()
                                        if text == "upload":
                                            upload_button = elem
                                            self.logger.debug_msg(f"Found 'Upload' button in container at ({location['x']}, {location['y']})")
                                            break
                                    except:
                                        continue
                                if upload_button:
                                    break
                    except:
                        continue
            
            # Strategy 5: Fallback - find any button with "Upload" text regardless of position
            if not upload_button:
                all_buttons = self.driver.driver.find_elements("xpath", "//android.widget.Button")
                for elem in all_buttons:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            button_text = elem.text.strip().lower()
                            if button_text == "upload":
                                upload_button = elem
                                location = elem.location
                                self.logger.debug_msg(f"Found 'Upload' button by Button.text (position-independent) at ({location['x']}, {location['y']})")
                                break
                    except:
                        continue
            
            if not upload_button:
                raise Exception("Could not locate 'Upload' button in Google Drive window")
            
            # Verify it's actually "Upload"
            verification_text = None
            verification_passed = False
            try:
                # First check the button's own text attribute (for Button elements)
                if upload_button.tag_name == "android.widget.Button":
                    try:
                        button_text = upload_button.text
                        if button_text:
                            verification_text = button_text.strip()
                            if verification_text.lower() == "upload":
                                verification_passed = True
                                self.logger.debug_msg(f"Verified: Button text is '{verification_text}'")
                    except:
                        pass
                
                # If not verified yet, check TextView children
                if not verification_passed:
                    text_views = upload_button.find_elements("xpath", ".//android.widget.TextView")
                    for tv in text_views:
                        try:
                            text = tv.text.strip()
                            if text and len(text) > 0:
                                verification_text = text
                                if "upload" in text.lower():
                                    verification_passed = True
                                    self.logger.debug_msg(f"Verified: TextView child text is '{verification_text}'")
                                    break
                        except:
                            continue
                
                # If still not verified, check content description
                if not verification_passed:
                    try:
                        content_desc = upload_button.get_attribute("content-desc")
                        if content_desc and "upload" in content_desc.lower():
                            verification_text = content_desc
                            verification_passed = True
                            self.logger.debug_msg(f"Verified: Content description is '{verification_text}'")
                    except:
                        pass
                
                # If found by resource ID (com.google.android.apps.docs:id/save_button), trust it
                if not verification_passed:
                    try:
                        resource_id = upload_button.get_attribute("resource-id")
                        if resource_id and "save_button" in resource_id:
                            verification_passed = True
                            self.logger.debug_msg(f"Verified: Found by resource ID '{resource_id}' - trusting it's the Upload button")
                    except:
                        pass
                
            except Exception as e:
                self.logger.debug_msg(f"Verification check error: {e}")
            
            # Only fail if we have verification text but it doesn't contain "upload"
            if verification_text and not verification_passed:
                verification_text_lower = verification_text.lower()
                if "upload" not in verification_text_lower:
                    raise Exception(f"VERIFICATION FAILED: Not Upload button! Got '{verification_text}'")
            
            # If we got here without verification but button exists, log warning but proceed
            if not verification_passed:
                self.logger.debug_msg("Could not verify button text, but proceeding with click (button found by search strategies)")
            
            upload_button.click()
            sleep(0.5)  # Brief delay after clicking Upload
            self.logger.success("'Upload' button clicked - export should now be processing")
            
        except Exception as e:
            self.logger.error(f"ERROR clicking 'Upload' button: {e}")
            self.driver.get_page_source(f"upload_error_{chat_name}.xml")
            raise
        
        self.logger.success(f"SUCCESS: Export initiated for '{chat_name}'")
        self.logger.info("📤 Google Drive should now be handling the export...")
        
        return True
    
    def format_time(self, seconds: float) -> str:
        """Format seconds into a human-readable time string."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.1f}s"
    
    def export_chats(self, chat_names: List[str], include_media: bool = True, resume_folder: Optional[Path] = None) -> Tuple[Dict[str, bool], Dict[str, float], float, Dict[str, bool]]:
        """Export multiple chats.
        
        Args:
            chat_names: List of chat names to export
            include_media: If True, export with media; if False, export without media
            resume_folder: Optional path to Google Drive folder to check for existing exports
        
        Returns:
            Tuple of (results dict, timing dict, total_time, skipped_already_exists dict)
            - results: Dict mapping chat_name -> success (bool)
            - timings: Dict mapping chat_name -> elapsed_time (float seconds)
            - total_time: Total time elapsed for batch (float seconds)
            - skipped_already_exists: Dict mapping chat_name -> True if skipped because already exists
        """
        results = {}
        timings = {}
        skipped_already_exists = {}
        total = len(chat_names)
        batch_start_time = time.time()
        
        for i, chat_name in enumerate(chat_names, 1):
            self.logger.info(f"\nProcessing chat {i}/{total}: '{chat_name}'")
            
            chat_start_time = time.time()
            
            # Check if chat already exists (resume mode)
            if resume_folder:
                exists, matching_files = check_chat_exists(resume_folder, chat_name)
                if exists:
                    skipped_already_exists[chat_name] = True
                    if self.logger.debug:
                        self.logger.debug_msg(f"Chat '{chat_name}' already exists in resume folder")
                        for file_name in matching_files:
                            self.logger.debug_msg(f"  Found existing file: {file_name}")
                        self.logger.info(f"⏭️  Skipping '{chat_name}' (already exported)")
                    else:
                        self.logger.info(f"⏭️  Skipping '{chat_name}' (already exported)")
                    results[chat_name] = False
                    chat_end_time = time.time()
                    timings[chat_name] = chat_end_time - chat_start_time
                    continue
            
            try:
                # Navigate to main screen first
                self.driver.navigate_to_main()
                sleep(0.3)  # Brief delay after navigation
                
                # Click into chat
                if not self.driver.click_chat(chat_name):
                    self.logger.warning(f"Could not open chat '{chat_name}' - skipping")
                    results[chat_name] = False
                    chat_end_time = time.time()
                    timings[chat_name] = chat_end_time - chat_start_time
                    continue
                
                # Export the chat
                success = self.export_chat_to_google_drive(chat_name, include_media=include_media)
                results[chat_name] = success
                
                # Navigate back to main screen
                self.driver.navigate_back_to_main()
                
            except Exception as e:
                error_msg = str(e)
                if "community" in error_msg.lower() or "more" in error_msg.lower():
                    self.logger.warning(f"Skipped '{chat_name}' - community chat or no export option")
                else:
                    self.logger.error(f"Error during export for '{chat_name}': {e}")
                results[chat_name] = False
                
                # Try to navigate back
                try:
                    self.driver.navigate_back_to_main()
                except:
                    pass
            
            # Calculate and report timing for this chat
            chat_end_time = time.time()
            chat_elapsed = chat_end_time - chat_start_time
            timings[chat_name] = chat_elapsed
            
            # Calculate cumulative time so far
            cumulative_time = chat_end_time - batch_start_time
            
            # Report timing
            status_emoji = "✅" if results.get(chat_name, False) else "⚠️"
            status_text = "EXPORTED" if results.get(chat_name, False) else "SKIPPED"
            self.logger.info(f"\n{status_emoji} Chat '{chat_name}' {status_text}")
            self.logger.info(f"   ⏱️  Time for this chat: {self.format_time(chat_elapsed)}")
            self.logger.info(f"   ⏱️  Total elapsed time: {self.format_time(cumulative_time)}")
        
        total_time = time.time() - batch_start_time
        return results, timings, total_time, skipped_already_exists


def input_with_timeout(prompt: str, timeout: int, logger: Logger, default_value: str = "") -> Tuple[str, bool]:
    """Get user input with optional timeout and countdown display.
    
    Args:
        prompt: Prompt string to display
        timeout: Timeout in seconds (0 = no timeout)
        logger: Logger instance for output
        default_value: Default value to return if timeout expires
        
    Returns:
        Tuple of (user input string or default_value if timeout expires, timeout_occurred)
    """
    if timeout <= 0:
        # No timeout, just get input normally
        return input(prompt).strip(), False
    
    result = [None]
    timeout_occurred = [False]
    input_received = threading.Event()
    countdown_active = threading.Event()
    countdown_active.set()
    
    def get_input():
        """Get input in a separate thread."""
        try:
            result[0] = input(prompt).strip()
            countdown_active.clear()
            input_received.set()
        except (EOFError, KeyboardInterrupt):
            countdown_active.clear()
            input_received.set()
    
    def show_countdown():
        """Show countdown timer on a separate line."""
        remaining = timeout
        # Print initial empty line for countdown (will be updated)
        print()  # New line for countdown display
        while remaining > 0 and countdown_active.is_set() and not input_received.is_set():
            # Move cursor up one line, clear it, print countdown, then move back down
            countdown_msg = f"⏱️  Time remaining: {remaining:2d} seconds (will default to 'all' if no input)..."
            sys.stdout.write(f"\033[1A\033[2K{countdown_msg}\033[1B")  # Up, clear, print, down
            sys.stdout.flush()
            sleep(1)
            remaining -= 1
        
        if countdown_active.is_set() and not input_received.is_set():
            # Timeout reached - clear the countdown line
            sys.stdout.write("\033[1A\033[2K")  # Move up and clear
            sys.stdout.flush()
            result[0] = default_value
            timeout_occurred[0] = True
            input_received.set()
    
    # Start countdown thread
    countdown_thread = threading.Thread(target=show_countdown, daemon=True)
    countdown_thread.start()
    
    # Small delay to let countdown start
    sleep(0.1)
    
    # Start input thread
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()
    
    # Wait for input or timeout
    input_received.wait(timeout + 1)
    
    # Clear countdown line if still visible
    if countdown_active.is_set():
        sys.stdout.write("\033[1A\033[2K")
        sys.stdout.flush()
    
    return result[0] if result[0] is not None else default_value, timeout_occurred[0]


def interactive_mode(driver: WhatsAppDriver, exporter: ChatExporter, logger: Logger, test_limit: Optional[int] = None, include_media: bool = True, sort_alphabetical: bool = True, resume_folder: Optional[Path] = None, auto_all: bool = False):
    """Interactive mode: prompt user to select chats to export.
    
    Args:
        driver: WhatsAppDriver instance
        exporter: ChatExporter instance
        logger: Logger instance
        test_limit: If set, limit to this many chats for testing
        include_media: If True, export with media; if False, export without media
        sort_alphabetical: If True, sort chats alphabetically. If False, keep original order.
        resume_folder: Optional path to Google Drive folder to check for existing exports
        auto_all: If True, default to 'all' after 30 seconds if no input is provided
    """
    logger.info("=" * 70)
    if test_limit:
        logger.info(f"📋 INTERACTIVE MODE (TEST MODE - Limited to {test_limit} chats)")
    else:
        logger.info("📋 INTERACTIVE MODE")
    logger.info("=" * 70)
    
    # Collect all chats (with limit if test mode)
    if test_limit:
        logger.info(f"Loading chats (test mode: limited to {test_limit})...")
        all_chats = driver.collect_all_chats(limit=test_limit, sort_alphabetical=sort_alphabetical)
    else:
        logger.info("Loading all chats...")
        all_chats = driver.collect_all_chats(sort_alphabetical=sort_alphabetical)
    
    if not all_chats:
        logger.error("No chats found!")
        return
    
    # Display chats
    logger.info(f"\nFound {len(all_chats)} chats:")
    logger.info("-" * 70)
    for i, chat_name in enumerate(all_chats, 1):
        logger.info(f"{i:3d}. {chat_name}")
    
    # Prompt user for selection
    sort_info = "alphabetically" if sort_alphabetical else "in original order"
    logger.info("\n" + "=" * 70)
    logger.info("Select chats to export:")
    logger.info(f"  - Chats are listed {sort_info}")
    logger.info("  - Enter chat numbers (comma-separated, e.g., 1,3,5)")
    logger.info("  - Use ranges with hyphens (e.g., 100-200 or 1,3,5-10,20)")
    logger.info("  - Enter 'all' to export all chats")
    logger.info("  - Enter 'q', 'quit', or 'exit' to quit")
    if auto_all:
        logger.info("  - Will default to 'all' after 30 seconds if no input is provided")
    logger.info("=" * 70)
    
    # Get user input with optional timeout
    timeout_seconds = 30 if auto_all else 0
    selection, timeout_occurred = input_with_timeout("\nYour selection: ", timeout_seconds, logger, default_value="all" if auto_all else "")
    selection = selection.lower()
    
    if timeout_occurred:
        logger.info("⏱️  Timeout reached - defaulting to 'all'")
    
    # Handle exit gracefully
    if selection == 'q' or selection == 'quit' or selection == 'exit':
        logger.info("Exiting...")
        return
    
    # Handle empty input
    if not selection:
        logger.warning("No selection entered. Exiting...")
        return
    
    # Parse selection
    chats_to_export = []
    if selection == 'all':
        chats_to_export = all_chats
    else:
        try:
            indices = []
            # Split by comma first
            parts = [x.strip() for x in selection.split(',')]
            for part in parts:
                if '-' in part:
                    # Handle range (e.g., "100-200")
                    range_parts = part.split('-')
                    if len(range_parts) != 2:
                        raise ValueError(f"Invalid range format: {part}")
                    start = int(range_parts[0].strip())
                    end = int(range_parts[1].strip())
                    if start > end:
                        raise ValueError(f"Invalid range: start ({start}) must be <= end ({end})")
                    # Add all indices in range (inclusive)
                    indices.extend(range(start, end + 1))
                else:
                    # Single number
                    indices.append(int(part))
            
            # Remove duplicates while preserving order
            seen = set()
            unique_indices = []
            for idx in indices:
                if idx not in seen:
                    seen.add(idx)
                    unique_indices.append(idx)
            
            for idx in unique_indices:
                if 1 <= idx <= len(all_chats):
                    chats_to_export.append(all_chats[idx - 1])
                else:
                    logger.warning(f"Invalid index: {idx}")
        except ValueError as e:
            logger.error(f"Invalid input: {e}. Please enter numbers separated by commas, ranges with hyphens (e.g., 100-200), 'all', or 'q' to quit.")
            return
    
    if not chats_to_export:
        logger.warning("No chats selected for export.")
        return
    
    media_status = "with media" if include_media else "without media"
    logger.info(f"\n📤 Exporting {len(chats_to_export)} chat(s) {media_status}...")
    
    if resume_folder:
        logger.info(f"🔄 Resume mode enabled: Checking for existing exports in {resume_folder}")
    
    # Export selected chats
    results, timings, total_time, skipped_already_exists = exporter.export_chats(chats_to_export, include_media=include_media, resume_folder=resume_folder)
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("✅ EXPORT COMPLETE")
    logger.info("=" * 70)
    
    total_exported = sum(1 for v in results.values() if v)
    total_skipped_already_exists = len(skipped_already_exists)
    total_skipped_other = sum(1 for v in results.values() if not v) - total_skipped_already_exists
    
    # Calculate average time (only for successfully exported chats)
    exported_timings = [timings[chat] for chat, success in results.items() if success]
    avg_time = sum(exported_timings) / len(exported_timings) if exported_timings else 0
    
    logger.info(f"\n📊 FINAL STATISTICS:")
    logger.info(f"   Total chats processed: {len(results)}")
    logger.info(f"   Successfully exported: {total_exported}")
    if total_skipped_already_exists > 0:
        logger.info(f"   Skipped (already exists): {total_skipped_already_exists}")
    if total_skipped_other > 0:
        logger.info(f"   Skipped (error/community): {total_skipped_other}")
    if total_skipped_already_exists == 0 and total_skipped_other == 0:
        logger.info(f"   Skipped: {sum(1 for v in results.values() if not v)}")
    
    logger.info(f"\n⏱️  TIMING SUMMARY:")
    logger.info(f"   Total time taken: {exporter.format_time(total_time)}")
    if exported_timings:
        logger.info(f"   Average time per chat: {exporter.format_time(avg_time)}")
        if len(exported_timings) > 1:
            fastest_time = min(exported_timings)
            slowest_time = max(exported_timings)
            logger.info(f"   Fastest chat: {exporter.format_time(fastest_time)}")
            logger.info(f"   Slowest chat: {exporter.format_time(slowest_time)}")
    
    logger.info(f"\n📋 RESULTS BY CHAT:")
    logger.info("-" * 70)
    for chat_name, success in sorted(results.items()):
        if chat_name in skipped_already_exists:
            status = "⏭️  SKIPPED (already exists)"
        elif success:
            status = "✅ EXPORTED"
        else:
            status = "⚠️ SKIPPED"
        chat_time = timings.get(chat_name, 0)
        logger.info(f"   {status}: {chat_name} ({exporter.format_time(chat_time)})")
        
        # In debug mode, show matching files for skipped chats
        if logger.debug and chat_name in skipped_already_exists:
            exists, matching_files = check_chat_exists(resume_folder, chat_name)
            if matching_files:
                for file_name in matching_files:
                    logger.debug_msg(f"      Found: {file_name}")


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Default to include_media=True if neither flag is specified
    if args.include_media is None:
        args.include_media = True
    
    logger = Logger(debug=args.debug)
    
    # Check for colorama
    if not COLORAMA_AVAILABLE:
        logger.warning("colorama not installed. Install with: pip install colorama")
        logger.info("Continuing without colored output...")
    
    logger.info("=" * 70)
    logger.info("🚀 WhatsApp Chat Auto-Export")
    logger.info("=" * 70)
    
    appium_manager = None
    driver_manager = None
    
    def cleanup():
        """Cleanup handler."""
        logger.info("\n" + "=" * 70)
        logger.info("🧹 CLEANUP")
        logger.info("=" * 70)
        if driver_manager:
            driver_manager.quit()
        if appium_manager:
            appium_manager.stop_appium()
        logger.info("Cleanup complete")
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\n\n⚠️ Interrupted by user (Ctrl+C)")
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Start Appium (unless skipped)
        appium_manager = AppiumManager(logger)
        if not args.skip_appium:
            if not appium_manager.start_appium():
                logger.error("Failed to start Appium. Exiting.")
                sys.exit(1)
        else:
            logger.info("Skipping Appium startup (--skip-appium flag)")
        
        # Initialize driver
        driver_manager = WhatsAppDriver(logger, wireless_adb=args.wireless_adb)
        
        # Check device connection
        if not driver_manager.check_device_connection():
            logger.error("No device connected. Please connect your Android device and try again.")
            cleanup()
            sys.exit(1)
        
        # Connect to WhatsApp
        if not driver_manager.connect():
            logger.error("Failed to connect to WhatsApp. Exiting.")
            cleanup()
            sys.exit(1)
        
        # Navigate to main screen
        if not driver_manager.navigate_to_main():
            logger.error("Failed to navigate to main screen. Exiting.")
            cleanup()
            sys.exit(1)
        
        # Validate resume directory if provided
        resume_folder = None
        if args.resume:
            resume_folder = validate_resume_directory(args.resume, logger)
            if resume_folder is None:
                logger.error("Invalid resume directory. Exiting.")
                cleanup()
                sys.exit(1)
        
        # Initialize exporter
        exporter = ChatExporter(driver_manager, logger)
        
        # Run interactive mode
        sort_alphabetical = args.sort_order == 'alphabetical'
        interactive_mode(driver_manager, exporter, logger, test_limit=args.test, include_media=args.include_media, sort_alphabetical=sort_alphabetical, resume_folder=resume_folder, auto_all=args.all)
        
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        cleanup()
        sys.exit(1)
    finally:
        cleanup()


if __name__ == "__main__":
    main()

