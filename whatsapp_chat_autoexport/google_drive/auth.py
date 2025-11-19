"""
Google Drive OAuth Authentication module.

Handles OAuth 2.0 authentication flow with local token storage.
"""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..utils.logger import Logger


# Google Drive API scopes
# If modifying these scopes, delete the token file to re-authenticate
SCOPES = ['https://www.googleapis.com/auth/drive']

# Default credential storage location
DEFAULT_CREDENTIALS_DIR = Path.home() / '.whatsapp_export'
DEFAULT_TOKEN_FILE = 'google_credentials.json'
DEFAULT_CLIENT_SECRETS_FILE = 'client_secrets.json'


class GoogleDriveAuth:
    """Manages Google Drive OAuth 2.0 authentication."""

    def __init__(self,
                 credentials_dir: Optional[Path] = None,
                 token_filename: str = DEFAULT_TOKEN_FILE,
                 client_secrets_filename: str = DEFAULT_CLIENT_SECRETS_FILE,
                 logger: Optional[Logger] = None):
        """
        Initialize Google Drive authentication manager.

        Args:
            credentials_dir: Directory to store credentials (default: ~/.whatsapp_export)
            token_filename: Name of token file (default: google_credentials.json)
            client_secrets_filename: Name of OAuth client secrets file (default: client_secrets.json)
            logger: Logger instance for output
        """
        self.credentials_dir = credentials_dir or DEFAULT_CREDENTIALS_DIR
        self.token_file = self.credentials_dir / token_filename
        self.client_secrets_file = self.credentials_dir / client_secrets_filename
        self.logger = logger or Logger()
        self.credentials: Optional[Credentials] = None

    def setup_credentials_directory(self) -> bool:
        """
        Create credentials directory if it doesn't exist.

        Returns:
            True if directory exists or was created, False on error
        """
        try:
            self.credentials_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug_msg(f"Credentials directory: {self.credentials_dir}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create credentials directory: {e}")
            return False

    def has_client_secrets(self) -> bool:
        """
        Check if OAuth client secrets file exists.

        Returns:
            True if client secrets file exists, False otherwise
        """
        return self.client_secrets_file.exists()

    def has_valid_token(self) -> bool:
        """
        Check if a valid token file exists.

        Returns:
            True if valid token exists, False otherwise
        """
        if not self.token_file.exists():
            return False

        try:
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
                return creds and creds.valid
        except Exception as e:
            self.logger.debug_msg(f"Token validation failed: {e}")
            return False

    def load_token(self) -> Optional[Credentials]:
        """
        Load credentials from token file.

        Returns:
            Credentials object if successful, None otherwise
        """
        if not self.token_file.exists():
            self.logger.debug_msg("Token file does not exist")
            return None

        try:
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
                self.logger.debug_msg("Token loaded successfully")
                return creds
        except Exception as e:
            self.logger.error(f"Failed to load token: {e}")
            return None

    def save_token(self, credentials: Credentials) -> bool:
        """
        Save credentials to token file.

        Args:
            credentials: Credentials object to save

        Returns:
            True if successful, False otherwise
        """
        try:
            self.setup_credentials_directory()
            with open(self.token_file, 'wb') as token:
                pickle.dump(credentials, token)
            self.logger.success(f"Token saved to: {self.token_file}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save token: {e}")
            return False

    def refresh_token(self, credentials: Credentials) -> bool:
        """
        Refresh expired credentials.

        Args:
            credentials: Credentials object to refresh

        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("Refreshing access token...")
            credentials.refresh(Request())
            self.save_token(credentials)
            self.logger.success("Token refreshed successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to refresh token: {e}")
            return False

    def run_oauth_flow(self) -> Optional[Credentials]:
        """
        Run the OAuth 2.0 authorization flow in the browser.

        Returns:
            Credentials object if successful, None otherwise
        """
        if not self.has_client_secrets():
            self.logger.error("=" * 70)
            self.logger.error("OAuth Client Secrets Not Found!")
            self.logger.error("=" * 70)
            self.logger.error(f"Expected location: {self.client_secrets_file}")
            self.logger.error("")
            self.logger.error("To set up Google Drive API access:")
            self.logger.error("1. Go to https://console.cloud.google.com/")
            self.logger.error("2. Create a new project or select existing")
            self.logger.error("3. Enable Google Drive API")
            self.logger.error("4. Create OAuth 2.0 credentials (Desktop app)")
            self.logger.error("5. Download client secrets JSON")
            self.logger.error(f"6. Save as: {self.client_secrets_file}")
            self.logger.error("=" * 70)
            return None

        try:
            self.logger.info("=" * 70)
            self.logger.info("Starting Google Drive OAuth Flow")
            self.logger.info("=" * 70)
            self.logger.info("A browser window will open for authentication...")
            self.logger.info("Please log in and authorize the application.")
            self.logger.info("")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_file),
                SCOPES
            )

            # Run local server for OAuth callback
            creds = flow.run_local_server(port=0)

            self.logger.success("Authentication successful!")
            self.save_token(creds)

            return creds

        except Exception as e:
            self.logger.error(f"OAuth flow failed: {e}")
            return None

    def authenticate(self, force_reauth: bool = False) -> Optional[Credentials]:
        """
        Authenticate with Google Drive API.

        This method handles the complete authentication flow:
        1. Check for existing valid token
        2. Refresh if expired
        3. Run OAuth flow if needed

        Args:
            force_reauth: Force re-authentication even if token exists

        Returns:
            Credentials object if successful, None otherwise
        """
        self.setup_credentials_directory()

        # Force re-authentication if requested
        if force_reauth:
            self.logger.info("Forcing re-authentication...")
            if self.token_file.exists():
                self.token_file.unlink()
                self.logger.debug_msg("Deleted existing token")

        # Try to load existing credentials
        creds = self.load_token()

        # No credentials exist - run OAuth flow
        if not creds:
            self.logger.info("No saved credentials found. Starting OAuth flow...")
            creds = self.run_oauth_flow()
            if creds:
                self.credentials = creds
                return creds
            else:
                return None

        # Credentials exist but are expired - try to refresh
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                self.logger.info("Credentials expired. Refreshing...")
                if self.refresh_token(creds):
                    self.credentials = creds
                    return creds
                else:
                    # Refresh failed - run OAuth flow
                    self.logger.warning("Token refresh failed. Re-authenticating...")
                    creds = self.run_oauth_flow()
                    if creds:
                        self.credentials = creds
                        return creds
                    else:
                        return None
            else:
                # No refresh token or other issue - run OAuth flow
                self.logger.info("Credentials invalid. Re-authenticating...")
                creds = self.run_oauth_flow()
                if creds:
                    self.credentials = creds
                    return creds
                else:
                    return None

        # Credentials are valid
        self.logger.success("Using saved credentials")
        self.credentials = creds
        return creds

    def get_credentials(self) -> Optional[Credentials]:
        """
        Get current credentials (authenticate if needed).

        Returns:
            Credentials object if authenticated, None otherwise
        """
        if self.credentials and self.credentials.valid:
            return self.credentials

        return self.authenticate()

    def revoke_credentials(self) -> bool:
        """
        Revoke current credentials and delete token file.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                self.logger.success("Token file deleted")

            self.credentials = None
            self.logger.info("Credentials revoked. You'll need to re-authenticate next time.")
            return True

        except Exception as e:
            self.logger.error(f"Failed to revoke credentials: {e}")
            return False
