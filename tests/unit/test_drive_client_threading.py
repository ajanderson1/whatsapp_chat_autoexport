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


class TestDeleteFileLocking:
    def test_delete_file_holds_lock_for_both_service_calls(self):
        """delete_file does a pre-fetch (get) for the file name, then delete.

        Both must be under the lock.
        """
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            return_values={"get": {"name": "f.zip"}, "delete": {}},
        )
        c.service = fake

        ok = c.delete_file("abc")

        assert ok is True
        # Expect both a get and a delete, both with the lock held.
        names = [name for name, _ in fake.observations]
        assert "get" in names and "delete" in names, f"observations={fake.observations}"
        assert all(held for _, held in fake.observations), (
            f"Expected all service calls under lock, got {fake.observations}"
        )
        assert c._service_lock.locked() is False


class TestPollForNewExportLocking:
    def test_poll_for_new_export_locks_the_service_call_not_the_sleep(self, monkeypatch):
        """poll_for_new_export must hold the lock during service.files().list(),
        and release it before time.sleep()."""
        from whatsapp_chat_autoexport.google_drive import drive_client as dc_module

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)

        # A fake service that returns a file on first poll (so the loop exits).
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        fake = _LockObservingService(
            c._service_lock,
            return_values={
                "list": {
                    "files": [
                        {
                            "id": "abc",
                            "name": "WhatsApp Chat with Test.zip",
                            "createdTime": now_iso,
                            "size": "0",
                        }
                    ]
                }
            },
        )
        c.service = fake

        sleep_observations: list[bool] = []

        def _fake_sleep(_seconds):
            sleep_observations.append(c._service_lock.locked())

        monkeypatch.setattr(dc_module.time, "sleep", _fake_sleep)

        result = c.poll_for_new_export(
            initial_interval=0,
            max_interval=0,
            timeout=5,
            created_within_seconds=3600,
        )

        assert result is not None, "Expected the fake to return a file on first poll"
        # Every service call observed the lock held.
        assert fake.observations, "Expected service.files().list() to be called"
        assert all(held for _, held in fake.observations), (
            f"Expected all service calls under lock, got {fake.observations}"
        )
        # If sleep was called at all, it was outside the lock.
        assert all(held is False for held in sleep_observations), (
            f"time.sleep() must not hold the service lock; got {sleep_observations}"
        )
        # Lock released on return.
        assert c._service_lock.locked() is False


class _LockObservingDownloader:
    """Fake MediaIoBaseDownload that records lock state on each next_chunk()."""

    def __init__(self, lock: threading.Lock, chunks: int = 3):
        self.lock = lock
        self.remaining = chunks
        self.observations: list[bool] = []

    def next_chunk(self):
        self.observations.append(self.lock.locked())
        self.remaining -= 1
        status = MagicMock()
        status.progress = lambda: 1.0 - (self.remaining / 3.0)
        done = self.remaining <= 0
        return status, done


class TestDownloadFileLocking:
    def test_download_file_holds_lock_for_entire_chunk_loop(self, tmp_path, monkeypatch):
        """Every next_chunk() call must observe the lock as held."""
        from whatsapp_chat_autoexport.google_drive import drive_client as dc_module

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake_service = _LockObservingService(
            c._service_lock,
            return_values={"get": {"name": "f.zip", "size": 3}},
        )
        c.service = fake_service

        # Replace MediaIoBaseDownload so we don't need a real http stack.
        fake_downloader_holder = {}

        def _fake_downloader_factory(file_handle, request):
            d = _LockObservingDownloader(c._service_lock, chunks=3)
            fake_downloader_holder["d"] = d
            return d

        monkeypatch.setattr(dc_module, "MediaIoBaseDownload", _fake_downloader_factory)

        dest = tmp_path / "out.zip"
        ok = c.download_file("abc", dest, show_progress=False)

        assert ok is True, "download should report success"
        downloader = fake_downloader_holder["d"]
        assert downloader.observations, "Expected next_chunk() to be called"
        assert all(downloader.observations), (
            f"next_chunk() observations must all be True (lock held); got {downloader.observations}"
        )
        # Service-side observations too.
        assert all(held for _, held in fake_service.observations)
        # Lock released after return.
        assert c._service_lock.locked() is False


class TestMoveFileLocking:
    def test_move_file_holds_lock_for_both_service_calls(self):
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            return_values={
                "get": {"name": "f.zip", "parents": ["root"]},
                "update": {"id": "abc", "parents": ["dest"]},
            },
        )
        c.service = fake

        ok = c.move_file("abc", "dest")

        assert ok is True
        names = [name for name, _ in fake.observations]
        assert "get" in names and "update" in names, f"observations={fake.observations}"
        assert all(held for _, held in fake.observations), (
            f"Expected all service calls under lock, got {fake.observations}"
        )
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


class _RaisingService:
    """A fake service whose files().list() call raises HttpError."""

    def files(self):
        return self

    def list(self, **kwargs):
        return self

    def execute(self):
        # Build a minimal HttpError without needing a real httplib2 response.
        from googleapiclient.errors import HttpError

        class _FakeResp:
            status = 500
            reason = "Internal Server Error"

        raise HttpError(_FakeResp(), b"boom")


class TestLockReleasedOnException:
    def test_list_files_releases_lock_on_httperror(self):
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        c.service = _RaisingService()

        result = c.list_files(query="anything")

        # Error path returns []; the important assertion is that the lock
        # was released so future callers don't hang.
        assert result == []
        assert c._service_lock.locked() is False
        # And the lock is still usable.
        assert c._service_lock.acquire(blocking=False) is True
        c._service_lock.release()


class TestNoNestedLocking:
    def test_list_whatsapp_exports_does_not_deadlock(self):
        """list_whatsapp_exports calls list_files; must not hold the lock
        before delegating."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            return_values={"list": {"files": [{"id": "1", "name": "WhatsApp Chat with X.zip", "size": "0"}]}},
        )
        c.service = fake

        # If list_whatsapp_exports acquired the lock and then called list_files,
        # this call would hang and the test timeout would fire. pytest.ini sets
        # timeout=300 which is plenty short to notice a deadlock.
        files = c.list_whatsapp_exports()

        assert len(files) == 1
        # Sanity: service was called, and the lock was held when it was.
        assert all(held for _, held in fake.observations), (
            f"service calls must still be locked; got {fake.observations}"
        )
        assert c._service_lock.locked() is False
