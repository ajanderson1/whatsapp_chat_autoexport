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


class _LockObservingService:
    """A fake service that records whether a lock is held at call time.

    The fake supports the chain `service.files().list(...).execute()` and
    similar calls used by GoogleDriveClient, returning caller-specified
    return values. For each recorded call, it snapshots `lock.locked()`
    so tests can assert the lock was held during the service interaction.
    """

    def __init__(self, lock: threading.Lock, return_values: dict):
        """
        Args:
            lock: The lock expected to be held during service calls.
            return_values: Mapping of call_name -> return dict for .execute().
                Keys: "list", "get_media", "get", "delete", "update".
        """
        self.lock = lock
        self.return_values = return_values
        self.observations: list[tuple[str, bool]] = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.observations.append(("list", self.lock.locked()))
        return _ExecReturning(self.return_values.get("list", {"files": []}))

    def get(self, **kwargs):
        self.observations.append(("get", self.lock.locked()))
        return _ExecReturning(self.return_values.get("get", {"name": "x", "size": 0}))

    def get_media(self, **kwargs):
        self.observations.append(("get_media", self.lock.locked()))
        return _GetMediaRequest()

    def delete(self, **kwargs):
        self.observations.append(("delete", self.lock.locked()))
        return _ExecReturning(self.return_values.get("delete", {}))

    def update(self, **kwargs):
        self.observations.append(("update", self.lock.locked()))
        return _ExecReturning(self.return_values.get("update", {}))


class _ExecReturning:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _GetMediaRequest:
    """Placeholder for a get_media() request handed to MediaIoBaseDownload."""
    pass


class TestListFilesLocking:
    def test_list_files_holds_lock_during_service_call(self):
        """list_files must hold _service_lock when calling self.service.files().list()."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(c._service_lock, return_values={"list": {"files": []}})
        c.service = fake

        c.list_files(query="name contains 'x'")

        # At least one service call was made, and every one of them was
        # observed with the lock held.
        assert fake.observations, "Expected service.files().list() to be called"
        assert all(held for _, held in fake.observations), (
            f"Expected all service calls under lock, got {fake.observations}"
        )
        # And the lock is released again afterwards.
        assert c._service_lock.locked() is False


class TestGetFileMetadataLocking:
    def test_get_file_metadata_holds_lock(self):
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            return_values={"get": {"id": "abc", "name": "f.zip", "size": 10}},
        )
        c.service = fake

        result = c.get_file_metadata("abc")

        assert result == {"id": "abc", "name": "f.zip", "size": 10}
        assert fake.observations, "Expected service.files().get() to be called"
        assert all(held for _, held in fake.observations), (
            f"Expected all service calls under lock, got {fake.observations}"
        )
        assert c._service_lock.locked() is False
