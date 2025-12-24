"""
Interactive Mode module for WhatsApp Chat Auto-Export.

Handles interactive chat selection and user prompts.
"""

import sys
import threading
from time import sleep
from typing import Optional, Tuple, List
from pathlib import Path

from .whatsapp_driver import WhatsAppDriver
from .chat_exporter import ChatExporter
from ..utils.logger import Logger


def parse_range_max_index(range_str: str) -> Optional[int]:
    """Parse a range string and return the maximum index needed.

    Args:
        range_str: Range string like "3", "1,5,10", "100-200", or "1,5,10-20,30"

    Returns:
        Maximum index needed to satisfy the range, or None if invalid/empty
    """
    if not range_str or range_str.lower() == 'all':
        return None

    try:
        max_index = 0
        parts = [x.strip() for x in range_str.split(',')]
        for part in parts:
            if '-' in part:
                # Handle range (e.g., "100-200")
                range_parts = part.split('-')
                if len(range_parts) == 2:
                    end = int(range_parts[1].strip())
                    max_index = max(max_index, end)
            else:
                # Single number
                max_index = max(max_index, int(part))
        return max_index if max_index > 0 else None
    except (ValueError, IndexError):
        return None


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
    
    def get_input():
        """Get input in a separate thread."""
        try:
            result[0] = input(prompt).strip()
            input_received.set()
        except (EOFError, KeyboardInterrupt):
            input_received.set()
    
    # Start input thread
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()

    # Dynamic countdown - update every second with in-place replacement
    remaining = timeout
    default_msg = f"'{default_value}'" if default_value else "no default"

    while remaining > 0 and not input_received.is_set():
        # Use \r to return to start of line, then overwrite
        countdown_msg = f"⏱️  {remaining:2d}s remaining (will default to {default_msg} if no input)..."
        sys.stdout.write(f"\r{countdown_msg}")
        sys.stdout.flush()

        sleep(1)
        remaining -= 1

    # Clear the countdown line when done
    if not input_received.is_set():
        sys.stdout.write("\r" + " " * 70 + "\r")  # Clear the line
        sys.stdout.flush()

    # Wait a bit more for input thread to complete
    input_received.wait(timeout=1)

    if result[0] is None:
        # Timeout reached
        result[0] = default_value
        timeout_occurred[0] = True
        print()  # New line after timeout
    
    return result[0] if result[0] is not None else default_value, timeout_occurred[0]


def interactive_mode(driver: WhatsAppDriver, exporter: ChatExporter, logger: Logger, test_limit: Optional[int] = None, include_media: bool = True, sort_alphabetical: bool = True, resume_folder: Optional[Path] = None, auto_all: bool = False, google_drive_folder: Optional[str] = None, default_range: Optional[str] = None):
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
        google_drive_folder: Optional Google Drive folder name for pipeline processing
        default_range: Optional range to use as default on timeout (e.g., "300-500" or "1,5,10-20")
    """
    logger.info("=" * 70)
    # Calculate range limit early for display purposes (--range takes precedence)
    range_max_index_display = parse_range_max_index(default_range) if default_range else None
    if range_max_index_display:
        logger.info(f"📋 INTERACTIVE MODE (Collecting up to {range_max_index_display} chats for --range)")
    elif test_limit:
        logger.info(f"📋 INTERACTIVE MODE (Limited to {test_limit} chats)")
    else:
        logger.info("📋 INTERACTIVE MODE")
    logger.info("=" * 70)

    # CRITICAL: Verify WhatsApp is still accessible before collecting chats
    # This prevents accidentally interacting with system UI
    if not driver.verify_whatsapp_is_open():
        logger.error("Cannot proceed - WhatsApp is not accessible. Exiting.")
        return

    # Calculate effective limit based on --range (takes precedence over --limit)
    range_max_index = parse_range_max_index(default_range) if default_range else None

    # Determine effective limit:
    # - If --range is set, it takes full precedence (--limit is ignored)
    # - If only --limit is set, use that
    # - If neither is set, collect all chats
    effective_limit = None
    if range_max_index:
        effective_limit = range_max_index
        if test_limit:
            logger.warning(f"--limit {test_limit} is being ignored because --range was specified")
    elif test_limit:
        effective_limit = test_limit

    # Collect chats with the calculated limit
    if effective_limit:
        logger.info(f"Loading chats (limited to {effective_limit})...")
        all_chats = driver.collect_all_chats(limit=effective_limit, sort_alphabetical=sort_alphabetical)
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

    # Determine default value and timeout behavior
    if default_range:
        # Range specified via --range flag
        default_value = default_range
        timeout_seconds = 30
        logger.info(f"  - Will default to range '{default_range}' after 30 seconds if no input is provided")
    elif auto_all:
        # --all flag or pipeline mode
        default_value = "all"
        timeout_seconds = 30
        logger.info("  - Will default to 'all' after 30 seconds if no input is provided")
    else:
        # No timeout
        default_value = ""
        timeout_seconds = 0

    logger.info("=" * 70)

    # Get user input with optional timeout
    selection, timeout_occurred = input_with_timeout("\nYour selection: ", timeout_seconds, logger, default_value=default_value)
    selection = selection.lower()

    if timeout_occurred:
        if default_range:
            logger.info(f"⏱️  Timeout reached - defaulting to range '{default_range}'")
        else:
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
    results, timings, total_time, skipped_already_exists = exporter.export_chats(
        chats_to_export, 
        include_media=include_media, 
        resume_folder=resume_folder,
        google_drive_folder=google_drive_folder
    )
    
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
            status = "⏭️ SKIPPED (already exists)"
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


