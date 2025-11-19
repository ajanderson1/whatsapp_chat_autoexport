"""
Checkpoint management for resuming WhatsApp exports after interruptions.

This module provides checkpoint functionality to track export progress locally,
allowing exports to resume from the exact chat index even after session loss or script restart.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class CheckpointManager:
    """
    Manages checkpoint files for resuming WhatsApp chat exports.

    Checkpoints are saved locally and track:
    - Last completed chat index (position in the chat list)
    - Last completed chat name
    - Total number of chats in the batch
    - Timestamp of last save

    This allows resuming from exact position after:
    - Session loss (wireless ADB disconnect)
    - Script crashes or interruptions
    - Manual script restarts
    """

    def __init__(self, checkpoint_path: Optional[Path] = None):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_path: Path to checkpoint file. Defaults to ~/.whatsapp_export_checkpoint.json
        """
        if checkpoint_path is None:
            checkpoint_path = Path.home() / ".whatsapp_export_checkpoint.json"

        self.checkpoint_path = Path(checkpoint_path)
        self._checkpoint_data: Optional[Dict[str, Any]] = None

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint from file if it exists.

        Returns:
            Dictionary with checkpoint data if exists, None otherwise
            Format: {
                "last_completed_index": int,
                "last_chat_name": str,
                "total_chats": int,
                "timestamp": str (ISO format),
                "session_start": str (ISO format)
            }
        """
        if not self.checkpoint_path.exists():
            return None

        try:
            with open(self.checkpoint_path, 'r') as f:
                self._checkpoint_data = json.load(f)
                return self._checkpoint_data
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load checkpoint file: {e}")
            return None

    def save_checkpoint(self, chat_index: int, chat_name: str, total_chats: int, success: bool) -> None:
        """
        Save checkpoint after successfully exporting a chat.

        Args:
            chat_index: 0-based index of the chat that was just completed
            chat_name: Name of the chat that was just completed
            total_chats: Total number of chats in the batch
            success: Whether the export was successful
        """
        # Only save checkpoint for successful exports
        if not success:
            return

        # Initialize checkpoint data if this is first save
        if self._checkpoint_data is None:
            self._checkpoint_data = {
                "session_start": datetime.now().isoformat()
            }

        # Update checkpoint data
        self._checkpoint_data.update({
            "last_completed_index": chat_index,
            "last_chat_name": chat_name,
            "total_chats": total_chats,
            "timestamp": datetime.now().isoformat()
        })

        # Write to file
        try:
            with open(self.checkpoint_path, 'w') as f:
                json.dump(self._checkpoint_data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save checkpoint: {e}")

    def clear_checkpoint(self) -> None:
        """
        Clear checkpoint file (typically called after successful completion of all exports).
        """
        if self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
                self._checkpoint_data = None
            except IOError as e:
                print(f"Warning: Could not delete checkpoint file: {e}")

    def get_resume_index(self) -> Optional[int]:
        """
        Get the index to resume from (next chat after last completed).

        Returns:
            Index of next chat to export, or None if no checkpoint exists
        """
        checkpoint = self.load_checkpoint()
        if checkpoint is None:
            return None

        # Resume from next chat after last completed
        return checkpoint.get("last_completed_index", -1) + 1

    def format_checkpoint_info(self) -> str:
        """
        Format checkpoint information for display to user.

        Returns:
            Formatted string describing checkpoint state
        """
        checkpoint = self.load_checkpoint()
        if checkpoint is None:
            return "No checkpoint found"

        last_index = checkpoint.get("last_completed_index", -1)
        last_chat = checkpoint.get("last_chat_name", "Unknown")
        total = checkpoint.get("total_chats", 0)
        timestamp = checkpoint.get("timestamp", "Unknown")

        # Parse timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = timestamp

        return (
            f"Found checkpoint at chat {last_index + 1}/{total}\n"
            f"Last completed: '{last_chat}'\n"
            f"Timestamp: {time_str}"
        )
