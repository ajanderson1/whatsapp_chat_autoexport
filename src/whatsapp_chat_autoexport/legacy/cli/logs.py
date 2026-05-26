#!/usr/bin/env python3
"""
Log viewer CLI for WhatsApp Chat Auto-Export.

Provides commands to view the persistent log file.
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
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


def _get_project_root() -> Path:
    """Get the project root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def _get_default_log_dir() -> Path:
    """Get the default log directory."""
    output_dir = Path("/output")
    if output_dir.exists() and output_dir.is_dir():
        return output_dir / "logs"
    return _get_project_root() / ".logs"


def _get_log_file(log_dir: Path) -> Path:
    """Get the main log file path."""
    return log_dir / "whatsapp_export.log"


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _print_colored(text: str, color: str = "") -> None:
    """Print with optional color support."""
    if COLORAMA_AVAILABLE and color:
        print(f"{color}{text}{Style.RESET_ALL}")
    else:
        print(text)


def _color_line(line: str) -> None:
    """Print a log line with color based on level."""
    line = line.rstrip()
    if '| ERROR' in line:
        _print_colored(line, Fore.RED)
    elif '| WARNING' in line:
        _print_colored(line, Fore.YELLOW)
    elif '| DEBUG' in line:
        _print_colored(line, Fore.MAGENTA)
    elif 'Session started' in line or 'Session ended' in line:
        _print_colored(line, Fore.GREEN)
    elif line.startswith('=' * 10):
        _print_colored(line, Fore.CYAN)
    else:
        print(line)


def cmd_info(log_file: Path) -> int:
    """Show log file information."""
    if not log_file.exists():
        _print_colored(f"Log file does not exist: {log_file}", Fore.YELLOW)
        _print_colored("No logs have been created yet.", Fore.CYAN)
        return 0

    stat = log_file.stat()
    _print_colored(f"\nLog file: {log_file}", Fore.CYAN)
    _print_colored(f"Size: {_format_size(stat.st_size)}", Fore.CYAN)

    # Count lines and sessions
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sessions = sum(1 for line in lines if 'Session started' in line)
    _print_colored(f"Total lines: {len(lines)}", Fore.CYAN)
    _print_colored(f"Sessions recorded: {sessions}", Fore.CYAN)

    # Show rotated backup files if any
    backup_files = list(log_file.parent.glob(f"{log_file.name}.*"))
    if backup_files:
        _print_colored(f"\nRotated backups: {len(backup_files)}", Fore.CYAN)
        for bf in sorted(backup_files):
            _print_colored(f"  - {bf.name} ({_format_size(bf.stat().st_size)})", Fore.CYAN)

    return 0


def cmd_show(log_file: Path, num_lines: int = 50) -> int:
    """Show the last N lines of the log file."""
    if not log_file.exists():
        _print_colored(f"Log file does not exist: {log_file}", Fore.YELLOW)
        _print_colored("No logs have been created yet.", Fore.CYAN)
        return 0

    _print_colored(f"\n=== {log_file.name} (last {num_lines} lines) ===\n", Fore.CYAN)

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        display_lines = lines[-num_lines:] if len(lines) > num_lines else lines

        for line in display_lines:
            _color_line(line)

        if len(lines) > num_lines:
            _print_colored(f"\n... showing last {num_lines} of {len(lines)} lines", Fore.CYAN)
            _print_colored(f"Use -n to show more lines, or -f to follow in real-time", Fore.CYAN)

    except Exception as e:
        _print_colored(f"Error reading log file: {e}", Fore.RED)
        return 1

    return 0


def cmd_follow(log_file: Path) -> int:
    """Follow (tail -f) the log file."""
    if not log_file.exists():
        _print_colored(f"Log file does not exist yet: {log_file}", Fore.YELLOW)
        _print_colored("Waiting for log entries...\n", Fore.CYAN)

    _print_colored(f"=== Following {log_file.name} (Ctrl+C to stop) ===\n", Fore.CYAN)

    try:
        # Wait for file to exist
        while not log_file.exists():
            time.sleep(0.5)

        with open(log_file, 'r', encoding='utf-8') as f:
            # Go to end of file
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    _color_line(line)
                else:
                    time.sleep(0.1)

    except KeyboardInterrupt:
        _print_colored("\n\nStopped following log.", Fore.CYAN)
        return 0
    except Exception as e:
        _print_colored(f"Error following log file: {e}", Fore.RED)
        return 1


def cmd_clear(log_file: Path) -> int:
    """Clear the log file (with confirmation)."""
    if not log_file.exists():
        _print_colored(f"Log file does not exist: {log_file}", Fore.YELLOW)
        return 0

    stat = log_file.stat()
    _print_colored(f"\nLog file: {log_file}", Fore.YELLOW)
    _print_colored(f"Size: {_format_size(stat.st_size)}", Fore.YELLOW)

    # Also find backup files
    backup_files = list(log_file.parent.glob(f"{log_file.name}.*"))
    if backup_files:
        _print_colored(f"Backup files: {len(backup_files)}", Fore.YELLOW)

    _print_colored("\nThis will delete the log file and all backups.", Fore.RED)
    response = input("Are you sure? (yes/no): ").strip().lower()

    if response not in ['y', 'yes']:
        _print_colored("Cancelled.", Fore.YELLOW)
        return 0

    try:
        log_file.unlink()
        for bf in backup_files:
            bf.unlink()
        _print_colored("Log file cleared.", Fore.GREEN)
    except Exception as e:
        _print_colored(f"Error clearing log file: {e}", Fore.RED)
        return 1

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Chat Auto-Export Log Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Show last 50 lines
  %(prog)s -n 100             # Show last 100 lines
  %(prog)s -f                 # Follow in real-time (like tail -f)
  %(prog)s --info             # Show log file info
  %(prog)s --clear            # Clear the log file
  %(prog)s --log-dir /path    # Use custom log directory
        """
    )

    parser.add_argument(
        '-n', '--lines',
        type=int,
        default=50,
        metavar='NUM',
        help='Number of lines to show (default: 50)'
    )

    parser.add_argument(
        '-f', '--follow',
        action='store_true',
        help='Follow mode (like tail -f)'
    )

    parser.add_argument(
        '--info',
        action='store_true',
        help='Show log file information'
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear the log file'
    )

    parser.add_argument(
        '--log-dir',
        type=str,
        metavar='DIR',
        help='Log directory (default: .logs/)'
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Determine log directory and file
    if args.log_dir:
        log_dir = Path(args.log_dir).expanduser()
    else:
        log_dir = _get_default_log_dir()

    log_file = _get_log_file(log_dir)

    # Execute appropriate command
    if args.info:
        return cmd_info(log_file)
    elif args.clear:
        return cmd_clear(log_file)
    elif args.follow:
        return cmd_follow(log_file)
    else:
        return cmd_show(log_file, args.lines)


if __name__ == "__main__":
    sys.exit(main())
