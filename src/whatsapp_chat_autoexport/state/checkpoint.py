"""
Checkpoint management for session persistence.

Provides atomic save/restore of session state for recovery
after interruptions.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import threading

from .models import SessionState


class CheckpointManager:
    """
    Manages checkpoints for session state persistence.

    Provides atomic saves with rollback support and automatic
    checkpoint file rotation.
    """

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        max_checkpoints: int = 5,
        checkpoint_interval: int = 5,
    ):
        """
        Initialize the checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint files
            max_checkpoints: Maximum number of checkpoint files to keep
            checkpoint_interval: Save checkpoint every N chats
        """
        if checkpoint_dir is None:
            checkpoint_dir = Path.home() / ".whatsapp_export" / "checkpoints"

        self._checkpoint_dir = checkpoint_dir
        self._max_checkpoints = max_checkpoints
        self._checkpoint_interval = checkpoint_interval
        self._lock = threading.RLock()
        self._chats_since_checkpoint = 0

        # Ensure directory exists
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    @property
    def checkpoint_dir(self) -> Path:
        """Get the checkpoint directory."""
        return self._checkpoint_dir

    def save(
        self,
        session: SessionState,
        force: bool = False,
    ) -> Optional[Path]:
        """
        Save a checkpoint of the session state.

        Args:
            session: Session state to save
            force: Force save even if interval not reached

        Returns:
            Path to checkpoint file or None if skipped
        """
        with self._lock:
            self._chats_since_checkpoint += 1

            # Check if we should save
            if not force and self._chats_since_checkpoint < self._checkpoint_interval:
                return None

            self._chats_since_checkpoint = 0

            # Generate checkpoint filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            checkpoint_file = self._checkpoint_dir / f"checkpoint_{timestamp}.json"
            temp_file = checkpoint_file.with_suffix(".tmp")

            try:
                # Write to temp file first (atomic write)
                with open(temp_file, "w") as f:
                    json.dump(session.model_dump(mode="json"), f, indent=2, default=str)

                # Move temp to final location
                shutil.move(str(temp_file), str(checkpoint_file))

                # Rotate old checkpoints
                self._rotate_checkpoints()

                return checkpoint_file

            except Exception as e:
                # Clean up temp file on failure
                if temp_file.exists():
                    temp_file.unlink()
                raise RuntimeError(f"Failed to save checkpoint: {e}") from e

    def load_latest(self) -> Optional[SessionState]:
        """
        Load the most recent checkpoint.

        Returns:
            SessionState or None if no checkpoint exists
        """
        with self._lock:
            checkpoints = self._list_checkpoints()
            if not checkpoints:
                return None

            latest = checkpoints[-1]
            return self.load(latest)

    def load(self, checkpoint_path: Path) -> Optional[SessionState]:
        """
        Load a specific checkpoint.

        Args:
            checkpoint_path: Path to checkpoint file

        Returns:
            SessionState or None if load fails
        """
        with self._lock:
            if not checkpoint_path.exists():
                return None

            try:
                with open(checkpoint_path, "r") as f:
                    data = json.load(f)

                return SessionState.model_validate(data)

            except Exception:
                return None

    def list_checkpoints(self) -> List[Path]:
        """
        List all available checkpoints.

        Returns:
            List of checkpoint file paths, sorted oldest to newest
        """
        with self._lock:
            return self._list_checkpoints()

    def _list_checkpoints(self) -> List[Path]:
        """Internal checkpoint listing."""
        checkpoints = list(self._checkpoint_dir.glob("checkpoint_*.json"))
        checkpoints.sort(key=lambda p: p.stat().st_mtime)
        return checkpoints

    def _rotate_checkpoints(self) -> None:
        """Remove old checkpoints exceeding max limit."""
        checkpoints = self._list_checkpoints()

        while len(checkpoints) > self._max_checkpoints:
            oldest = checkpoints.pop(0)
            try:
                oldest.unlink()
            except Exception:
                pass

    def clear(self) -> None:
        """Remove all checkpoints."""
        with self._lock:
            for checkpoint in self._list_checkpoints():
                try:
                    checkpoint.unlink()
                except Exception:
                    pass

    def has_checkpoint(self) -> bool:
        """Check if any checkpoint exists."""
        return len(self._list_checkpoints()) > 0

    def get_checkpoint_info(self) -> dict:
        """
        Get information about available checkpoints.

        Returns:
            Dict with checkpoint statistics
        """
        checkpoints = self._list_checkpoints()

        if not checkpoints:
            return {
                "count": 0,
                "latest": None,
                "oldest": None,
            }

        return {
            "count": len(checkpoints),
            "latest": checkpoints[-1].name if checkpoints else None,
            "oldest": checkpoints[0].name if checkpoints else None,
            "latest_time": datetime.fromtimestamp(
                checkpoints[-1].stat().st_mtime
            ).isoformat() if checkpoints else None,
        }
