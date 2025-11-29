"""
Chat Exporter module for WhatsApp Chat Auto-Export.

Handles chat export operations including menu navigation, media selection,
and Google Drive upload.
"""

import subprocess
import os
import time
from time import sleep
from typing import Optional, Tuple, List, Dict, Set
from pathlib import Path

from .whatsapp_driver import WhatsAppDriver
from ..utils.logger import Logger


# Helper functions for resume functionality

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


# Main ChatExporter class

class ChatExporter:
    """Handles chat export operations."""
    
    def __init__(self, driver: WhatsAppDriver, logger: Logger, pipeline: Optional['WhatsAppPipeline'] = None):
        self.driver = driver
        self.logger = logger
        self.pipeline = pipeline
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
            sleep(1.0)  # Increased delay for export dialog to fully appear
            
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
                    # Verify what we're about to click
                    try:
                        verification_text = media_option.text.strip() if hasattr(media_option, 'text') else "Unknown"
                        self.logger.info(f"About to click: '{verification_text}'")
                    except:
                        self.logger.debug_msg("Could not get verification text before click")

                    media_option.click()
                    self.logger.success(f"✓ '{media_option_name}' clicked")

                    # Increased wait time for media to be prepared (especially for large media exports)
                    sleep(2.0)  # Longer wait for media processing

                    # Wait for share dialog with exponential backoff
                    self.logger.info("Waiting for share dialog to initialize...")
                    if not self._wait_for_share_dialog():
                        self.logger.warning("Share dialog may not have appeared, but continuing...")
                    else:
                        self.logger.success("✓ Share dialog ready")
            
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
    
    def export_chats(self, chat_names: List[str], include_media: bool = True, resume_folder: Optional[Path] = None, google_drive_folder: Optional[str] = None) -> Tuple[Dict[str, bool], Dict[str, float], float, Dict[str, bool]]:
        """Export multiple chats.
        
        Args:
            chat_names: List of chat names to export
            include_media: If True, export with media; if False, export without media
            resume_folder: Optional path to Google Drive folder to check for existing exports
            google_drive_folder: Optional Google Drive folder name for pipeline processing
        
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

            # CRITICAL: Verify WhatsApp is still accessible before each export
            # This prevents accidentally interacting with system UI
            if not self.driver.verify_whatsapp_is_open():
                self.logger.error(f"WhatsApp is not accessible - cannot export '{chat_name}'. Stopping batch.")
                results[chat_name] = False
                timings[chat_name] = 0
                break  # Stop the batch if WhatsApp becomes inaccessible

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

                # Export the chat to Google Drive
                export_success = self.export_chat_to_google_drive(chat_name, include_media=include_media)

                # Navigate back to main screen
                self.driver.navigate_back_to_main()

                if export_success:
                    # If export succeeded and pipeline is configured, process the chat
                    if self.pipeline:
                        self.logger.info(f"\n🔄 Starting pipeline processing for '{chat_name}'...")

                        # Give Google Drive a moment to finish uploading
                        sleep(2.0)

                        # Process the pipeline
                        try:
                            pipeline_result = self.pipeline.process_single_export(
                                chat_name=chat_name,
                                google_drive_folder=google_drive_folder
                            )

                            if pipeline_result['success']:
                                self.logger.success(f"✅ Pipeline completed for '{chat_name}'")
                                if pipeline_result.get('output_path'):
                                    self.logger.info(f"   📁 Output: {pipeline_result['output_path']}")
                                results[chat_name] = True
                            else:
                                self.logger.warning(f"⚠️  Pipeline failed for '{chat_name}'")
                                if pipeline_result.get('errors'):
                                    for error in pipeline_result['errors']:
                                        self.logger.error(f"   Error: {error}")
                                results[chat_name] = False

                        except Exception as e:
                            self.logger.error(f"Pipeline processing failed for '{chat_name}': {e}")
                            results[chat_name] = False
                    else:
                        # No pipeline configured, just mark export as successful
                        results[chat_name] = True
                else:
                    results[chat_name] = False

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

