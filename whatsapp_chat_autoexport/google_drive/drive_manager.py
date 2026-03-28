"""
Google Drive Manager module.

High-level operations for WhatsApp chat export management.
"""

from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any, Callable
from .auth import GoogleDriveAuth
from .drive_client import GoogleDriveClient
from ..utils.logger import Logger


class GoogleDriveManager:
    """High-level Google Drive operations manager for WhatsApp exports."""

    def __init__(self,
                 credentials_dir: Optional[Path] = None,
                 logger: Optional[Logger] = None):
        """
        Initialize Google Drive manager.

        Args:
            credentials_dir: Directory for OAuth credentials
            logger: Logger instance for output
        """
        self.logger = logger or Logger()
        self.auth = GoogleDriveAuth(credentials_dir=credentials_dir, logger=self.logger)
        self.client = GoogleDriveClient(self.auth, logger=self.logger)

    def connect(self) -> bool:
        """
        Authenticate and connect to Google Drive.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("Connecting to Google Drive...")

        if not self.client.connect():
            return False

        self.logger.success("Google Drive connection established")
        return True

    def list_whatsapp_exports(self, folder_id: Optional[str] = None) -> List[Dict]:
        """
        List all WhatsApp export files in Google Drive.

        Args:
            folder_id: Optional folder ID to search in

        Returns:
            List of export file metadata dictionaries
        """
        self.logger.info("Searching for WhatsApp exports...")
        return self.client.list_whatsapp_exports(folder_id=folder_id)

    def wait_for_new_export(self,
                           initial_interval: int = 2,
                           max_interval: int = 8,
                           timeout: int = 300,
                           created_within_seconds: int = 300,
                           chat_name: Optional[str] = None,
                           include_media: bool = False,
                           # Legacy parameter — ignored, use initial_interval instead
                           poll_interval: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Wait for a new WhatsApp export to appear in Google Drive root.

        Continuously polls Google Drive looking for a WhatsApp export file
        created recently. Designed to wait for phone upload to complete after
        triggering an export.

        Uses progressive backoff: starts at initial_interval, doubles every
        2 polls, caps at max_interval.

        Args:
            initial_interval: Starting seconds between polls (default: 2)
            max_interval: Maximum seconds between polls (default: 8)
            timeout: Maximum seconds to wait (default: 300 / 5 minutes)
            created_within_seconds: Only consider files created within this window (default: 300 / 5 minutes)
            chat_name: Optional chat name to filter for specific export
            include_media: Whether export includes media; affects default timeout
            poll_interval: Deprecated — ignored. Use initial_interval instead.

        Returns:
            File metadata dict if found, None on timeout

        Raises:
            RuntimeError: If timeout occurs
        """
        file = self.client.poll_for_new_export(
            initial_interval=initial_interval,
            max_interval=max_interval,
            timeout=timeout,
            created_within_seconds=created_within_seconds,
            chat_name=chat_name,
            include_media=include_media,
        )
        
        if not file:
            raise RuntimeError(
                f"Timeout waiting for new export after {timeout}s. "
                "The export may still be uploading from your phone. "
                "Try increasing the timeout or check your phone's Google Drive upload status."
            )
            
        return file

    def download_export(self,
                        file_id: str,
                        file_name: str,
                        dest_dir: Path,
                        delete_after: bool = False) -> Tuple[bool, Optional[Path]]:
        """
        Download a single WhatsApp export file.

        Args:
            file_id: Google Drive file ID
            file_name: Name of the file
            dest_dir: Destination directory
            delete_after: Delete from Google Drive after successful download

        Returns:
            Tuple of (success: bool, downloaded_path: Optional[Path])
        """
        dest_path = dest_dir / file_name

        # Download file
        success = self.client.download_file(file_id, dest_path, show_progress=True)

        if not success:
            return False, None

        # Delete from Google Drive if requested
        if delete_after:
            self.logger.info(f"Deleting from Google Drive: {file_name}")
            delete_success = self.client.delete_file(file_id)
            
            if delete_success:
                self.logger.success(f"✓ Successfully deleted from Google Drive: {file_name}")
            else:
                self.logger.error(f"✗ Failed to delete from Google Drive: {file_name}")
                self.logger.warning("File was downloaded but remains on Google Drive")

        return True, dest_path

    def find_and_move_recent_export(self, chat_name: str, destination_folder_name: str, max_wait_seconds: int = 15) -> bool:
        """
        Find a recently uploaded WhatsApp export and move it to a specific folder.
        
        This is used after exporting a chat to Google Drive to organize it into a folder.
        Waits for the file to appear (polls every 2 seconds up to max_wait_seconds).
        
        Args:
            chat_name: Name of the chat (used to match filename)
            destination_folder_name: Name of the folder to move to
            max_wait_seconds: Maximum time to wait for file to appear
            
        Returns:
            True if file was found and moved, False otherwise
        """
        import time
        
        # Expected filename pattern: "WhatsApp Chat with {chat_name}.zip"
        expected_filename_part = chat_name
        
        self.logger.info(f"Waiting for export to appear on Google Drive (up to {max_wait_seconds}s)...")
        
        # Poll for the file
        attempts = 0
        max_attempts = max_wait_seconds // 2
        file_id = None
        file_name = None
        
        while attempts < max_attempts:
            # List recent WhatsApp exports
            files = self.list_whatsapp_exports(folder_id=None)  # Search in root
            
            # Find file matching chat name, sorted by creation time (newest first)
            matching_files = [
                f for f in files 
                if expected_filename_part in f['name']
            ]
            
            if matching_files:
                # Sort by modified time (most recent first)
                matching_files.sort(key=lambda x: x.get('modifiedTime', ''), reverse=True)
                file_id = matching_files[0]['id']
                file_name = matching_files[0]['name']
                self.logger.success(f"✓ Found export on Google Drive: {file_name}")
                break
            
            attempts += 1
            if attempts < max_attempts:
                time.sleep(2)
        
        if not file_id:
            self.logger.warning(f"Could not find export for '{chat_name}' on Google Drive after {max_wait_seconds}s")
            return False
        
        # Find or create destination folder
        folder_id = self.client.find_folder_by_name(destination_folder_name)
        
        if not folder_id:
            self.logger.info(f"Folder '{destination_folder_name}' not found, file will remain in My Drive")
            return False
        
        # Move file to folder
        self.logger.info(f"Moving '{file_name}' to folder '{destination_folder_name}'...")
        success = self.client.move_file(file_id, folder_id)
        
        if success:
            self.logger.success(f"✓ Moved to folder: {destination_folder_name}")
            return True
        else:
            self.logger.error(f"Failed to move file to folder")
            return False

    def batch_download_exports(self,
                                files: List[Dict],
                                dest_dir: Path,
                                delete_after: bool = False,
                                on_progress: Optional[Callable] = None) -> List[Path]:
        """
        Download multiple WhatsApp export files.

        Args:
            files: List of file metadata dictionaries from list_whatsapp_exports()
            dest_dir: Destination directory
            delete_after: Delete from Google Drive after successful downloads
            on_progress: Optional callback for progress updates.
                         Signature: on_progress(phase, message, current, total, item_name="")

        Returns:
            List of successfully downloaded file paths
        """
        if not files:
            self.logger.warning("No files to download")
            return []

        self.logger.info(f"Downloading {len(files)} file(s)...")

        # Create destination directory
        dest_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files = []

        # Skip tqdm entirely to avoid "bad value(s) in fds_to_keep" errors
        # tqdm creates multiprocessing locks that can fail in threaded contexts (TUI workers)
        # Use simple logger-based progress instead
        for i, file in enumerate(files, 1):
            file_id = file['id']
            file_name = file['name']

            self.logger.info(f"[{i}/{len(files)}] Downloading {file_name}...")

            success, dest_path = self.download_export(
                file_id,
                file_name,
                dest_dir,
                delete_after=delete_after
            )

            if success and dest_path:
                downloaded_files.append(dest_path)

            if on_progress:
                try:
                    on_progress("download", f"Downloaded {file_name}", i, len(files), file_name)
                except Exception:
                    pass  # Never let callback errors crash downloads

        self.logger.success(f"Downloaded {len(downloaded_files)}/{len(files)} file(s)")
        return downloaded_files

    def cleanup_exports(self, file_ids: List[str]) -> int:
        """
        Delete multiple files from Google Drive.

        Args:
            file_ids: List of Google Drive file IDs to delete

        Returns:
            Number of successfully deleted files
        """
        if not file_ids:
            self.logger.warning("No files to delete")
            return 0

        self.logger.info(f"Deleting {len(file_ids)} file(s) from Google Drive...")

        deleted_count = 0
        for file_id in file_ids:
            if self.client.delete_file(file_id):
                deleted_count += 1

        self.logger.success(f"Deleted {deleted_count}/{len(file_ids)} file(s)")
        return deleted_count

    def find_exports_in_folder(self, folder_name: str) -> Tuple[Optional[str], List[Dict]]:
        """
        Find WhatsApp exports in a specific folder by name.

        Args:
            folder_name: Name of the folder to search in

        Returns:
            Tuple of (folder_id: Optional[str], files: List[Dict])
        """
        # Find folder
        folder_id = self.client.find_folder_by_name(folder_name)

        if not folder_id:
            return None, []

        # List exports in folder
        files = self.list_whatsapp_exports(folder_id=folder_id)

        return folder_id, files

    def get_export_summary(self, folder_id: Optional[str] = None) -> Dict:
        """
        Get summary of WhatsApp exports.

        Args:
            folder_id: Optional folder ID to search in

        Returns:
            Dictionary with summary information
        """
        files = self.list_whatsapp_exports(folder_id=folder_id)

        total_size = sum(int(f.get('size', 0)) for f in files)
        total_size_mb = total_size / (1024 * 1024)

        summary = {
            'file_count': len(files),
            'total_size_bytes': total_size,
            'total_size_mb': total_size_mb,
            'files': files
        }

        return summary
