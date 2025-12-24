"""
Appium Manager module for WhatsApp Chat Auto-Export.

Manages the Appium server lifecycle.
"""

import subprocess
import os
import time
from typing import Optional

from ..utils.logger import Logger


class AppiumManager:
    """Manages Appium server lifecycle."""

    def __init__(self, logger: Logger):
        self.logger = logger
        self.appium_proc: Optional[subprocess.Popen] = None
        # Use ANDROID_HOME from environment (Docker sets this), fall back to macOS default
        self.android_home = os.environ.get(
            "ANDROID_HOME",
            os.path.expanduser("~/Library/Android/sdk")
        )

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
