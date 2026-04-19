"""
Unit tests for GoogleDriveClient thread-safety.

These tests verify the locking contract on GoogleDriveClient — specifically
that every public method touching self.service acquires self._service_lock,
that exceptions release the lock, and that no method deadlocks by calling
another locked method while holding the lock.

They use unittest.mock and do NOT exercise real httplib2 or Google Drive.
Real-concurrency coverage lives in tests/integration/test_drive_client_concurrency.py.
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


class TestLockPresence:
    def test_client_has_service_lock_after_construction(self):
        """Constructing a GoogleDriveClient must create the _service_lock attribute."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        # threading.Lock() returns a _thread.lock instance; its type is the same
        # object that threading.Lock() itself returns, so we compare by behaviour:
        assert hasattr(c, "_service_lock")
        # Must be acquirable and releasable.
        assert c._service_lock.acquire(blocking=False) is True
        c._service_lock.release()
