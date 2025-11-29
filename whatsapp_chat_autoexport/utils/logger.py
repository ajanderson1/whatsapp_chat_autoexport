"""
Logger module for WhatsApp Chat Auto-Export.

Provides colored, categorized logging with debug mode support.
"""

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
