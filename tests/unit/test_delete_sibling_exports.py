"""
Unit tests for GoogleDriveClient.delete_sibling_exports.

Verifies the post-download Drive cleanup primitive:
- method existence
- client-side regex matching (base name, .zip, (N) numeric suffixes)
- rejects substring collisions and non-numeric suffixes
- holds the service lock for list and each delete
- never raises; returns count of successful deletes
- handles listing failures, per-file delete failures, and stale 404s
"""
import threading
from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient


@pytest.fixture
def client():
    """A GoogleDriveClient with a mocked service attached (connect() bypassed)."""
    auth = MagicMock()
    c = GoogleDriveClient(auth=auth)
    c.service = MagicMock()
    return c


class TestMethodExists:
    def test_delete_sibling_exports_is_callable(self, client):
        """GoogleDriveClient must expose delete_sibling_exports(chat_name)."""
        assert hasattr(client, "delete_sibling_exports")
        assert callable(client.delete_sibling_exports)
