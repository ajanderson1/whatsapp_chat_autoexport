"""
Logger module for WhatsApp Chat Auto-Export.

Provides colored, categorized logging with debug mode support and
optional rotating file logging for persistent log history.
"""

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Callable, Literal

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

# Regex to strip leading emoji sequences from messages
_EMOJI_PREFIX_RE = re.compile(
    r'^[\U0001F300-\U0001FAFF\u2600-\u27BF\u2700-\u27BF\uFE00-\uFE0F\u200D\u20E3'
    r'\U0000FE0F\U000E0020-\U000E007F\u2B50\u2B55\u23CF\u23E9-\u23F3'
    r'\u23F8-\u23FA\u25AA\u25AB\u25B6\u25C0\u25FB-\u25FE\u2614\u2615'
    r'\u2648-\u2653\u267F\u2693\u26A1\u26AA\u26AB\u26BD\u26BE\u26C4'
    r'\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3\u26F5\u26FA\u26FD\u2702'
    r'\u2705\u2708-\u270D\u270F\u2712\u2714\u2716\u271D\u2721\u2728'
    r'\u2733\u2734\u2744\u2747\u274C\u274E\u2753-\u2755\u2757\u2763'
    r'\u2764\u2795-\u2797\u27A1\u27B0\u27BF]+\s*'
)

# Regex to strip ANSI escape codes
_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Regex to detect separator lines (e.g. "=====" or "-----")
_SEPARATOR_RE = re.compile(r'^[=\-]{10,}$')


def _get_project_root() -> Path:
    """Get the project root directory."""
    # Start from this file's directory and go up until we find pyproject.toml
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to the package root
    return Path(__file__).resolve().parent.parent.parent


def _get_default_log_dir() -> Path:
    """
    Get the default log directory.

    Returns:
        Path to .logs/ in the project root, or /output/logs/ if running in Docker
        with /output mounted.
    """
    # Check for Docker environment with mounted /output
    output_dir = Path("/output")
    if output_dir.exists() and output_dir.is_dir():
        return output_dir / "logs"

    # Default to project root .logs/
    return _get_project_root() / ".logs"


def _strip_ansi_and_emoji(text: str) -> str:
    """Strip ANSI escape codes and leading emojis from text."""
    # Remove ANSI escape codes
    text = _ANSI_ESCAPE_RE.sub('', text)
    # Remove leading emojis
    text = _EMOJI_PREFIX_RE.sub('', text)
    return text.strip()


class Logger:
    """Simple logger with debug mode support, colored output, and optional file logging."""

    # Class-level shutdown flag to suppress all logging during cleanup
    _shutdown = False

    @classmethod
    def set_shutdown(cls, shutdown: bool = True) -> None:
        """Set the global shutdown flag to suppress all logging."""
        cls._shutdown = shutdown

    def __init__(
        self,
        debug: bool = False,
        on_message: Optional[Callable] = None,
        log_dir: Optional[Path] = None,
        log_file_enabled: bool = True,
        log_level: Literal["debug", "info", "warning", "error"] = "info",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        logger_name: str = "whatsapp_export"
    ):
        """
        Initialize logger.

        Args:
            debug: Enable debug mode for verbose console output
            on_message: Optional callback called on each log message.
                        Signature: on_message(message: str, level: str)
                        where level is "info", "success", "warning", "error", "debug"
            log_dir: Directory for log files (default: project_root/.logs/)
            log_file_enabled: Whether to enable file logging (default: True)
            log_level: Minimum level for file logging: debug|info|warning|error
            max_bytes: Maximum size of each log file in bytes (default: 10MB)
            backup_count: Number of backup files to keep (default: 5)
            logger_name: Name for the logger instance
        """
        self.debug = debug
        self._on_message = on_message
        self._log_file_enabled = log_file_enabled
        self._log_level = log_level
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._logger_name = logger_name
        self._log_dir = log_dir
        self._log_file_path: Optional[Path] = None
        self._file_logger: Optional[logging.Logger] = None

        # Set up file logging if enabled
        if log_file_enabled:
            self._setup_file_logger()

    def _setup_file_logger(self) -> None:
        """Configure the rotating file handler for persistent logging."""
        try:
            # Determine log directory
            if self._log_dir:
                log_dir = Path(self._log_dir)
            else:
                log_dir = _get_default_log_dir()

            # Create log directory if it doesn't exist
            log_dir.mkdir(parents=True, exist_ok=True)

            # Use a single persistent log file (no timestamp - same file across sessions)
            log_filename = f"{self._logger_name}.log"
            self._log_file_path = log_dir / log_filename

            # Create logger (use fixed name so all sessions share the same logger)
            self._file_logger = logging.getLogger(f"{self._logger_name}_file")
            self._file_logger.setLevel(logging.DEBUG)  # Capture all, filter by handler

            # Prevent propagation to root logger
            self._file_logger.propagate = False

            # Remove existing handlers to avoid duplicates when Logger is instantiated multiple times
            self._file_logger.handlers.clear()

            # Create rotating file handler (appends to existing file)
            file_handler = RotatingFileHandler(
                self._log_file_path,
                maxBytes=self._max_bytes,
                backupCount=self._backup_count,
                encoding='utf-8'
            )

            # Set handler level based on config
            level_map = {
                "debug": logging.DEBUG,
                "info": logging.INFO,
                "warning": logging.WARNING,
                "error": logging.ERROR
            }
            file_handler.setLevel(level_map.get(self._log_level, logging.INFO))

            # Create formatter (clean, parseable format without emojis/ANSI)
            formatter = logging.Formatter(
                '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)

            # Add handler
            self._file_logger.addHandler(file_handler)

            # Log session start marker
            self._file_logger.info("=" * 60)
            self._file_logger.info(f"Session started")
            self._file_logger.info("=" * 60)

        except Exception as e:
            # Fall back to console-only logging if file setup fails
            print(f"Warning: Could not set up file logging: {e}", file=sys.stderr)
            self._file_logger = None
            self._log_file_path = None

    def _log_to_file(self, message: str, level: str) -> None:
        """
        Write a log message to the file logger.

        Args:
            message: The message to log (will be stripped of ANSI/emoji)
            level: Log level (debug, info, warning, error, success)
        """
        if not self._file_logger or Logger._shutdown:
            return

        # Clean the message for file output
        clean_message = _strip_ansi_and_emoji(message)

        # Skip empty messages and separators
        if not clean_message or _SEPARATOR_RE.match(clean_message):
            return

        # Map success to info for file logging
        file_level = level if level != "success" else "info"

        # Log at appropriate level
        level_method = getattr(self._file_logger, file_level, self._file_logger.info)
        try:
            level_method(clean_message)
        except Exception:
            pass  # Silently ignore file logging errors

    def get_log_file_path(self) -> Optional[Path]:
        """
        Get the current log file path.

        Returns:
            Path to the current log file, or None if file logging is disabled
        """
        return self._log_file_path

    def get_log_dir(self) -> Optional[Path]:
        """
        Get the log directory.

        Returns:
            Path to the log directory, or None if file logging is disabled
        """
        if self._log_file_path:
            return self._log_file_path.parent
        return None

    def _notify_callback(self, message: str, level: str) -> None:
        """Forward a log message to the on_message callback if set."""
        if not self._on_message:
            return

        # Strip the message
        clean = message.strip()

        # Skip empty lines
        if not clean:
            return

        # Skip separator lines
        if _SEPARATOR_RE.match(clean):
            return

        # Skip debug messages (too verbose for TUI)
        if level == "debug":
            return

        # Strip leading emoji prefixes (the TUI has its own prefix system)
        clean = _EMOJI_PREFIX_RE.sub('', clean).strip()

        # Skip if nothing left after stripping
        if not clean:
            return

        # Truncate long messages for compact display
        if len(clean) > 120:
            clean = clean[:117] + "..."

        try:
            self._on_message(clean, level)
        except Exception:
            pass

    def _print(self, message: str, color: str = "", emoji: str = ""):
        """Print with color and emoji support."""
        # Suppress all output during shutdown
        if Logger._shutdown:
            return
        if COLORAMA_AVAILABLE:
            print(f"{color}{emoji}{message}{Style.RESET_ALL}")
        else:
            print(f"{emoji}{message}")

    def info(self, message: str, emoji: str = ""):
        """Print info message."""
        self._print(message, Fore.CYAN, emoji)
        self._log_to_file(f"{emoji}{message}", "info")
        self._notify_callback(message, "info")

    def success(self, message: str):
        """Print success message."""
        self._print(message, Fore.GREEN, "")
        self._log_to_file(message, "success")
        self._notify_callback(message, "success")

    def warning(self, message: str):
        """Print warning message."""
        self._print(message, Fore.YELLOW, "")
        self._log_to_file(message, "warning")
        self._notify_callback(message, "warning")

    def error(self, message: str):
        """Print error message."""
        self._print(message, Fore.RED, "")
        self._log_to_file(message, "error")
        self._notify_callback(message, "error")

    def debug_msg(self, message: str):
        """Print debug message (only if debug mode enabled)."""
        if self.debug:
            self._print(message, Fore.MAGENTA, "")
            self._log_to_file(message, "debug")
            self._notify_callback(message, "debug")

    def step(self, step_num: int, message: str):
        """Print step message."""
        self.info(f"STEP {step_num}: {message}", "")

    def close(self) -> None:
        """Log session end marker. The file remains open for future sessions."""
        if self._file_logger:
            self._file_logger.info("=" * 60)
            self._file_logger.info("Session ended")
            self._file_logger.info("=" * 60)
            self._file_logger.info("")  # Blank line between sessions
