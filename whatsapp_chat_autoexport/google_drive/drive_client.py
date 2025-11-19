"""
Google Drive API Client module.

Low-level wrapper around Google Drive API for file operations.
"""

import io
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from .auth import GoogleDriveAuth
from ..utils.logger import Logger


class GoogleDriveClient:
    """Low-level Google Drive API client."""

    def __init__(self, auth: GoogleDriveAuth, logger: Optional[Logger] = None):
        """
        Initialize Google Drive client.

        Args:
            auth: GoogleDriveAuth instance for authentication
            logger: Logger instance for output
        """
        self.auth = auth
        self.logger = logger or Logger()
        self.service = None

    def connect(self) -> bool:
        """
        Connect to Google Drive API.

        Returns:
            True if successful, False otherwise
        """
        try:
            credentials = self.auth.get_credentials()
            if not credentials:
                self.logger.error("Failed to get credentials")
                return False

            self.service = build('drive', 'v3', credentials=credentials)
            self.logger.success("Connected to Google Drive API")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Google Drive API: {e}")
            return False

    def list_files(self,
                   query: Optional[str] = None,
                   folder_id: Optional[str] = None,
                   page_size: int = 100) -> List[Dict[str, Any]]:
        """
        List files in Google Drive.

        Args:
            query: Google Drive query string (e.g., "name contains 'WhatsApp'")
            folder_id: Folder ID to search in (optional)
            page_size: Number of results per page (max 1000)

        Returns:
            List of file metadata dictionaries
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return []

        try:
            # Build query
            if folder_id and query:
                full_query = f"'{folder_id}' in parents and {query}"
            elif folder_id:
                full_query = f"'{folder_id}' in parents"
            elif query:
                full_query = query
            else:
                full_query = None

            # List files
            results = self.service.files().list(
                q=full_query,
                pageSize=page_size,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)"
            ).execute()

            files = results.get('files', [])
            self.logger.debug_msg(f"Found {len(files)} files")

            return files

        except HttpError as error:
            self.logger.error(f"HTTP error listing files: {error}")
            return []
        except Exception as e:
            self.logger.error(f"Error listing files: {e}")
            return []

    def download_file(self,
                      file_id: str,
                      dest_path: Path,
                      show_progress: bool = True) -> bool:
        """
        Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID
            dest_path: Local destination path
            show_progress: Show download progress (default: True)

        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return False

        try:
            # Get file metadata first
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields="name, size"
            ).execute()

            file_name = file_metadata.get('name', 'unknown')
            file_size = int(file_metadata.get('size', 0))

            self.logger.info(f"Downloading: {file_name} ({file_size} bytes)")

            # Download file
            request = self.service.files().get_media(fileId=file_id)
            file_handle = io.BytesIO()
            downloader = MediaIoBaseDownload(file_handle, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if show_progress and status:
                    progress = int(status.progress() * 100)
                    self.logger.debug_msg(f"Download progress: {progress}%")

            # Write to file
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(file_handle.getvalue())

            self.logger.success(f"Downloaded to: {dest_path}")
            return True

        except HttpError as error:
            self.logger.error(f"HTTP error downloading file: {error}")
            return False
        except Exception as e:
            self.logger.error(f"Error downloading file: {e}")
            return False

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return False

        try:
            # Get file name first for logging
            try:
                file_metadata = self.service.files().get(
                    fileId=file_id,
                    fields="name"
                ).execute()
                file_name = file_metadata.get('name', file_id)
            except:
                file_name = file_id

            # Delete file
            self.service.files().delete(fileId=file_id).execute()
            self.logger.success(f"Deleted from Google Drive: {file_name}")
            return True

        except HttpError as error:
            if error.resp.status == 404:
                self.logger.warning(f"File not found (already deleted?): {file_id}")
                return True  # Consider it success if already deleted
            else:
                self.logger.error(f"HTTP error deleting file: {error}")
                return False
        except Exception as e:
            self.logger.error(f"Error deleting file: {e}")
            return False

    def move_file(self, file_id: str, destination_folder_id: str) -> bool:
        """
        Move a file to a different folder in Google Drive.
        
        Args:
            file_id: Google Drive file ID to move
            destination_folder_id: Destination folder ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return False
        
        try:
            # Get current parents
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='name, parents'
            ).execute()
            
            file_name = file_metadata.get('name', file_id)
            previous_parents = file_metadata.get('parents', [])
            
            # Move file to new folder (remove from old parents, add to new parent)
            self.service.files().update(
                fileId=file_id,
                addParents=destination_folder_id,
                removeParents=','.join(previous_parents) if previous_parents else None,
                fields='id, parents'
            ).execute()
            
            self.logger.success(f"Moved to folder: {file_name}")
            return True
            
        except HttpError as error:
            if error.resp.status == 404:
                self.logger.error(f"File or folder not found: {file_id}")
                return False
            else:
                self.logger.error(f"HTTP error moving file: {error}")
                return False
        except Exception as e:
            self.logger.error(f"Error moving file: {e}")
            return False

    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dictionary if successful, None otherwise
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return None

        try:
            metadata = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, parents"
            ).execute()

            return metadata

        except HttpError as error:
            self.logger.error(f"HTTP error getting file metadata: {error}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting file metadata: {e}")
            return None

    def find_folder_by_name(self, folder_name: str) -> Optional[str]:
        """
        Find a folder by name and return its ID.

        Args:
            folder_name: Name of the folder to find

        Returns:
            Folder ID if found, None otherwise
        """
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
        folders = self.list_files(query=query)

        if folders:
            folder_id = folders[0]['id']
            self.logger.debug_msg(f"Found folder '{folder_name}': {folder_id}")
            return folder_id
        else:
            self.logger.warning(f"Folder not found: {folder_name}")
            return None

    def list_whatsapp_exports(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List WhatsApp chat export files.

        Args:
            folder_id: Folder ID to search in (optional)

        Returns:
            List of WhatsApp export file metadata
        """
        query = "name contains 'WhatsApp Chat with'"
        files = self.list_files(query=query, folder_id=folder_id)

        self.logger.info(f"Found {len(files)} WhatsApp export file(s)")
        for file in files:
            size_mb = int(file.get('size', 0)) / (1024 * 1024)
            self.logger.debug_msg(f"  - {file['name']} ({size_mb:.2f} MB)")

        return files

    def poll_for_new_export(self,
                           poll_interval: int = 8,
                           timeout: int = 300,
                           created_within_seconds: int = 300) -> Optional[Dict[str, Any]]:
        """
        Poll Google Drive root for newly created WhatsApp export.
        
        This method continuously polls the root of Google Drive looking for
        a WhatsApp export file that was created recently. It's designed to wait
        for the phone to finish uploading after triggering an export.
        
        Args:
            poll_interval: Seconds between polls (default: 8)
            timeout: Maximum seconds to wait before giving up (default: 300 / 5 min)
            created_within_seconds: Only consider files created within this many seconds (default: 300 / 5 min)
            
        Returns:
            File metadata dict if found, None if timeout
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return None
            
        start_time = time.time()
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=created_within_seconds)
        poll_count = 0
        
        self.logger.info(f"Polling for new WhatsApp export in Drive root...")
        self.logger.info(f"Poll interval: {poll_interval}s, Timeout: {timeout}s")
        self.logger.info(f"Looking for files created after: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        while True:
            elapsed = time.time() - start_time
            poll_count += 1
            
            # Check timeout
            if elapsed > timeout:
                self.logger.error(f"Timeout after {timeout}s ({poll_count} polls)")
                return None
            
            try:
                # Query for WhatsApp exports in root (no folder_id filter)
                # NOTE: Files may not have .zip extension when first uploaded
                query = "name contains 'WhatsApp Chat with' and 'root' in parents"
                
                results = self.service.files().list(
                    q=query,
                    pageSize=100,
                    fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents)",
                    orderBy="createdTime desc"
                ).execute()
                
                files = results.get('files', [])
                
                # Filter by creation time
                for file in files:
                    created_time_str = file.get('createdTime')
                    if not created_time_str:
                        continue
                        
                    # Parse ISO 8601 timestamp
                    created_time = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                    
                    if created_time > cutoff_time:
                        size_mb = int(file.get('size', 0)) / (1024 * 1024)
                        self.logger.success(f"Found new export: {file['name']} ({size_mb:.2f} MB)")
                        self.logger.success(f"Created: {created_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        return file
                
                # Not found yet - log progress and wait
                remaining = timeout - elapsed
                self.logger.debug_msg(f"Poll #{poll_count}: No new exports found. Waiting {poll_interval}s... ({remaining:.0f}s remaining)")
                time.sleep(poll_interval)
                
            except HttpError as error:
                self.logger.error(f"HTTP error during polling: {error}")
                time.sleep(poll_interval)  # Wait before retrying
            except Exception as e:
                self.logger.error(f"Error during polling: {e}")
                time.sleep(poll_interval)  # Wait before retrying
