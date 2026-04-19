# Drive Client Thread-Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GoogleDriveClient` thread-safe by serializing all access to `self.service` through a single `threading.Lock`, eliminating the SSL-corruption cascade that crashed the 2026-04-18 smoke test.

**Architecture:** Add a single `threading.Lock()` as an instance attribute on `GoogleDriveClient`. Every public method that touches `self.service` wraps its body in `with self._service_lock:`. Callers (`GoogleDriveManager`, `ParallelPipeline`) are unchanged.

**Tech Stack:** Python 3.13, `threading.Lock`, `pytest`, `unittest.mock`, `google-api-python-client`, `httplib2`.

**Spec:** `docs/specs/2026-04-19-drive-client-thread-safety-design.md`
**Source failure report:** `docs/failure-reports/2026-04-18-pipeline-throughput-smoke-regression.md`

---

## Pre-flight

Before starting Task 1, the implementer must:

1. Create a worktree at `.worktrees/fix-drive-thread-safety` on branch `fix/drive-thread-safety` (using `superpowers:using-git-worktrees`).
2. Run `poetry install --with dev` inside the worktree.
3. Run `poetry run pytest -q` and confirm baseline is green before any task is committed. If any pre-existing failures appear, list them and deselect them with `--deselect` on per-task runs so they don't confound our signal.

Known pre-existing flaky/failing tests to deselect if they surface (from recent CI runs):
- `tests/integration/test_textual_tui.py::test_connect_pane_mounts_connect_button`
- `tests/integration/test_textual_tui.py::test_discovered_chats_defaults_empty`
- `tests/integration/test_textual_tui.py::test_discover_select_pane_mounts_discovery_inventory`

---

## File Structure

**Modified:**
- `whatsapp_chat_autoexport/google_drive/drive_client.py` — add `threading` import, `self._service_lock`, wrap six method bodies in `with self._service_lock:`, add module docstring note.

**Created:**
- `tests/unit/test_drive_client_threading.py` — unit tests for the locking contract.
- `tests/integration/test_drive_client_concurrency.py` — real-Drive concurrency test, marked `requires_drive`, skipped by default.
- `tests/integration/README_drive_integration.md` — setup instructions for the real-Drive test.

**Modified (config):**
- `pyproject.toml` — register the `requires_drive` marker.

No other files should be touched.

---

## Task 1: Add `requires_drive` pytest marker

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Open `pyproject.toml` and add the marker**

Find the `markers = [` block under `[tool.pytest.ini_options]` (around line `markers = [` in the file). Add a new entry for `requires_drive`.

The full updated markers list must read:

```toml
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "requires_api: marks tests that require API keys",
    "requires_device: marks tests that require an Android device",
    "requires_drive: marks tests that require live Google Drive credentials and the fixture folder env var",
    "unit: marks tests as unit tests",
]
```

- [ ] **Step 2: Verify pytest still runs**

Run: `poetry run pytest --collect-only -q -k "nothing_should_match_this_xyz" 2>&1 | tail -5`
Expected: pytest collects 0 tests and exits cleanly (exit code 0 or 5). No "unknown marker" warning.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "test(drive): register requires_drive pytest marker"
```

---

## Task 2: Write failing unit test — lock exists on the client

**Files:**
- Create: `tests/unit/test_drive_client_threading.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_drive_client_threading.py` with:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestLockPresence::test_client_has_service_lock_after_construction -v`
Expected: FAIL with `AttributeError: 'GoogleDriveClient' object has no attribute '_service_lock'` or `AssertionError`.

- [ ] **Step 3: Implement minimal code to make the test pass**

Open `whatsapp_chat_autoexport/google_drive/drive_client.py`. At the top, add `import threading` alongside the existing imports. Modify the top of the file and the `__init__` method as follows.

Replace the module docstring at the top:

```python
"""
Google Drive API Client module.

Low-level wrapper around Google Drive API for file operations.

Thread-safety:
    GoogleDriveClient serializes all access to self.service through
    self._service_lock. Every public method that touches self.service
    must acquire the lock for the full duration of its interaction with
    the service. Methods MUST NOT call each other while holding the lock
    (the lock is non-reentrant); any internal composition goes through
    the public API, which acquires the lock itself.
"""
```

Add `import threading` to the imports block so the imports read:

```python
import io
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from .auth import GoogleDriveAuth
from ..utils.logger import Logger
```

Update `__init__` to create the lock:

```python
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
        self._service_lock = threading.Lock()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestLockPresence::test_client_has_service_lock_after_construction -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): add _service_lock to GoogleDriveClient"
```

---

## Task 3: Add locked-call helpers and a failing test for `list_files`

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py` (at module scope, after `TestLockPresence`):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestListFilesLocking -v`
Expected: FAIL — one of the observations shows `held=False` because `list_files` does not currently acquire the lock.

- [ ] **Step 3: Implement minimal code to make the test pass**

In `whatsapp_chat_autoexport/google_drive/drive_client.py`, replace the body of `list_files` so the service-touching section is wrapped in the lock. The full method becomes:

```python
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

        # Build query
        if folder_id and query:
            full_query = f"'{folder_id}' in parents and {query}"
        elif folder_id:
            full_query = f"'{folder_id}' in parents"
        elif query:
            full_query = query
        else:
            full_query = None

        with self._service_lock:
            try:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestListFilesLocking -v`
Expected: PASS.

- [ ] **Step 5: Run the full drive-threading test file**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py -v`
Expected: 2 PASS, 0 FAIL.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access in list_files"
```

---

## Task 4: Lock `get_file_metadata`

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestGetFileMetadataLocking -v`
Expected: FAIL — `get_file_metadata` does not acquire the lock.

- [ ] **Step 3: Implement minimal code to make the test pass**

Replace the body of `get_file_metadata` so the service call is inside the lock:

```python
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

        with self._service_lock:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestGetFileMetadataLocking -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access in get_file_metadata"
```

---

## Task 5: Lock `delete_file`

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestDeleteFileLocking -v`
Expected: FAIL — `delete_file` does not hold the lock.

- [ ] **Step 3: Implement minimal code to make the test pass**

Replace the body of `delete_file`:

```python
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

        with self._service_lock:
            # Get file name first for logging
            try:
                file_metadata = self.service.files().get(
                    fileId=file_id,
                    fields="name"
                ).execute()
                file_name = file_metadata.get('name', file_id)
            except Exception:
                file_name = file_id

            try:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestDeleteFileLocking -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access in delete_file"
```

---

## Task 6: Lock `move_file`

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestMoveFileLocking -v`
Expected: FAIL.

- [ ] **Step 3: Implement minimal code to make the test pass**

Replace the body of `move_file`:

```python
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

        with self._service_lock:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestMoveFileLocking -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access in move_file"
```

---

## Task 7: Lock `download_file` — including the entire `next_chunk()` loop

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

This is the most important task for the bug we're fixing — `download_file` is where the concurrent SSL corruption happens. The lock MUST wrap the whole `next_chunk()` loop, not just the initial `get_media()` call.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestDownloadFileLocking -v`
Expected: FAIL — `download_file` does not hold the lock during the `next_chunk()` loop.

- [ ] **Step 3: Implement minimal code to make the test pass**

Replace the body of `download_file`. The entire block from the initial `files().get(...)` through the end of the `next_chunk()` loop must live inside the `with` block; only local file I/O (writing the buffer to disk) happens outside it.

```python
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

        file_handle = io.BytesIO()
        file_name = "unknown"

        with self._service_lock:
            try:
                # Get file metadata first
                file_metadata = self.service.files().get(
                    fileId=file_id,
                    fields="name, size"
                ).execute()

                file_name = file_metadata.get('name', 'unknown')
                file_size = int(file_metadata.get('size', 0))

                self.logger.info(f"Downloading: {file_name} ({file_size} bytes)")

                # Download file — ALL next_chunk() calls must stay under the lock
                # because each re-enters the shared service/Http instance.
                request = self.service.files().get_media(fileId=file_id)
                downloader = MediaIoBaseDownload(file_handle, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if show_progress and status:
                        progress = int(status.progress() * 100)
                        self.logger.debug_msg(f"Download progress: {progress}%")

            except HttpError as error:
                self.logger.error(f"HTTP error downloading file: {error}")
                return False
            except Exception as e:
                self.logger.error(f"Error downloading file: {e}")
                return False

        # Local filesystem I/O: safe to do without the Drive lock.
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(file_handle.getvalue())
            self.logger.success(f"Downloaded to: {dest_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error writing downloaded file to disk: {e}")
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestDownloadFileLocking -v`
Expected: PASS.

- [ ] **Step 5: Run the full drive-threading test file so far**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access for full download_file chunk loop"
```

---

## Task 8: Lock `poll_for_new_export`

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

`poll_for_new_export` loops with `time.sleep` between polls. The service call inside the loop body must be locked; the sleep must NOT be, so we don't hold the lock across idle seconds.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestPollForNewExportLocking -v`
Expected: FAIL — `poll_for_new_export` does not acquire the lock.

- [ ] **Step 3: Implement minimal code to make the test pass**

Replace the body of `poll_for_new_export` — only the `service.files().list(...).execute()` block must live inside the `with` block; the `time.sleep` and the backoff bookkeeping stay outside. The full method becomes:

```python
    def poll_for_new_export(self,
                           initial_interval: int = 2,
                           max_interval: int = 8,
                           timeout: int = 300,
                           created_within_seconds: int = 300,
                           chat_name: Optional[str] = None,
                           include_media: bool = False,
                           # Legacy parameter — ignored, use initial_interval instead
                           poll_interval: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Poll Google Drive root for newly created WhatsApp export.

        This method continuously polls the root of Google Drive looking for
        a WhatsApp export file that was created recently. It's designed to wait
        for the phone to finish uploading after triggering an export.

        Uses progressive backoff: starts at initial_interval, doubles every
        2 polls, caps at max_interval. Schedule example (defaults):
        Poll 1: 2s, Poll 2: 2s, Poll 3: 4s, Poll 4: 4s, Poll 5+: 8s

        Args:
            initial_interval: Starting seconds between polls (default: 2)
            max_interval: Maximum seconds between polls (default: 8)
            timeout: Maximum seconds to wait before giving up.
                     When not explicitly provided, defaults to 120s if include_media
                     is False, or 300s if include_media is True.
            created_within_seconds: Only consider files created within this many seconds (default: 300 / 5 min)
            chat_name: Optional chat name to filter for specific export
            include_media: Whether export includes media; affects default timeout
            poll_interval: Deprecated — ignored. Use initial_interval instead.

        Returns:
            File metadata dict if found, None if timeout
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return None

        if not include_media and timeout == 300:
            timeout = 120

        start_time = time.time()
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=created_within_seconds)
        poll_count = 0
        current_interval = initial_interval

        filter_desc = f" for '{chat_name}'" if chat_name else ""
        self.logger.info(f"Polling for new WhatsApp export{filter_desc} in Drive root...")
        self.logger.info(f"Initial interval: {initial_interval}s, Max interval: {max_interval}s, Timeout: {timeout}s")
        self.logger.info(f"Looking for files created after: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        while True:
            elapsed = time.time() - start_time
            poll_count += 1

            if elapsed > timeout:
                self.logger.error(f"Timeout after {timeout}s ({poll_count} polls){filter_desc}")
                return None

            query = "name contains 'WhatsApp Chat with' and 'root' in parents"
            if chat_name:
                safe_name = chat_name.replace("'", "\\'")
                query += f" and name contains '{safe_name}'"

            files: List[Dict[str, Any]] = []
            with self._service_lock:
                try:
                    results = self.service.files().list(
                        q=query,
                        pageSize=100,
                        fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents)",
                        orderBy="createdTime desc"
                    ).execute()
                    files = results.get('files', [])
                except HttpError as error:
                    self.logger.error(f"HTTP error during polling: {error}")
                    files = []
                except Exception as e:
                    self.logger.error(f"Error during polling: {e}")
                    files = []

            for file in files:
                created_time_str = file.get('createdTime')
                if not created_time_str:
                    continue

                created_time = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))

                if created_time > cutoff_time:
                    size_mb = int(file.get('size', 0)) / (1024 * 1024)
                    self.logger.success(f"Found new export: {file['name']} ({size_mb:.2f} MB)")
                    self.logger.success(f"Created: {created_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    return file

            remaining = timeout - elapsed
            self.logger.debug_msg(f"Poll #{poll_count}: No new exports found. Waiting {current_interval}s... ({remaining:.0f}s remaining)")
            time.sleep(current_interval)

            if poll_count % 2 == 0:
                current_interval = min(current_interval * 2, max_interval)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestPollForNewExportLocking -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_drive_client_threading.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): lock service access in poll_for_new_export"
```

---

## Task 9: Exception-safety test — lock releases on error

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`

The `with` statement already guarantees the lock is released on exception. This task just pins the behaviour down with an explicit test so a future refactor can't silently regress it.

- [ ] **Step 1: Write the failing test (that should now pass immediately)**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestLockReleasedOnException -v`
Expected: PASS (the `with` statement already provides this guarantee — the test exists to protect it).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_drive_client_threading.py
git commit -m "test(drive): verify lock is released on HttpError"
```

---

## Task 10: No-deadlock test — `list_whatsapp_exports` composes `list_files` safely

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`

`list_whatsapp_exports` calls `list_files` internally. Since the lock is non-reentrant (`Lock`, not `RLock`), this would deadlock if `list_whatsapp_exports` ever held the lock itself. This test proves the composition rule is respected.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_drive_client_threading.py`:

```python
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
```

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestNoNestedLocking -v`
Expected: PASS (current code does NOT hold the lock in `list_whatsapp_exports`; the test pins that invariant).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_drive_client_threading.py
git commit -m "test(drive): guard against nested locking in list_whatsapp_exports"
```

---

## Task 11: Concurrent-access test with mocks

**Files:**
- Modify: `tests/unit/test_drive_client_threading.py`

This test fires multiple threads at the client simultaneously. It uses a mocked service whose `execute()` sleeps briefly, forcing contention. It proves serialization at the lock level, even though it still doesn't exercise real `httplib2`.

- [ ] **Step 1: Write the failing test (should pass with current implementation)**

Append to `tests/unit/test_drive_client_threading.py`:

```python
class _SleepyLockProbeService:
    """A fake service whose list() holds the 'service' for a short sleep,
    and records the maximum observed concurrency under the lock."""

    def __init__(self, lock: threading.Lock):
        self.lock = lock
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self.max_observed_inflight = 0

    def files(self):
        return self

    def list(self, **kwargs):
        return self

    def execute(self):
        import time as _t
        with self._inflight_lock:
            self._inflight += 1
            if self._inflight > self.max_observed_inflight:
                self.max_observed_inflight = self._inflight
        try:
            _t.sleep(0.02)  # encourage contention
        finally:
            with self._inflight_lock:
                self._inflight -= 1
        return {"files": []}


class TestConcurrentCallsAreSerialized:
    def test_ten_threads_calling_list_files_see_no_overlap(self):
        from concurrent.futures import ThreadPoolExecutor

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        probe = _SleepyLockProbeService(c._service_lock)
        c.service = probe

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(lambda _: c.list_files(query="x"), range(10)))

        # Because _service_lock serializes every list_files call, the probe's
        # max_observed_inflight should be exactly 1.
        assert probe.max_observed_inflight == 1, (
            f"Expected serialized access (max 1 in-flight), observed "
            f"{probe.max_observed_inflight} concurrent calls"
        )
```

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/unit/test_drive_client_threading.py::TestConcurrentCallsAreSerialized -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_drive_client_threading.py
git commit -m "test(drive): concurrent calls via ThreadPoolExecutor see serialized access"
```

---

## Task 12: Full unit-test suite verification

**Files:** (none)

- [ ] **Step 1: Run the entire project test suite**

Run:

```bash
poetry run pytest -q \
  --deselect tests/integration/test_textual_tui.py::test_connect_pane_mounts_connect_button \
  --deselect tests/integration/test_textual_tui.py::test_discovered_chats_defaults_empty \
  --deselect tests/integration/test_textual_tui.py::test_discover_select_pane_mounts_discovery_inventory
```

Expected: all tests pass (831+ unit, 28 integration, including the new drive-threading file's tests).

- [ ] **Step 2: If any test fails that is not one of the pre-existing known-flakes, stop and investigate**

Do NOT proceed until the suite is green. Do NOT add further deselects without noting them in a commit message.

- [ ] **Step 3: (No commit — this is a verification task.)**

---

## Task 13: Create the real-Drive integration test harness

**Files:**
- Create: `tests/integration/test_drive_client_concurrency.py`
- Create: `tests/integration/README_drive_integration.md`

- [ ] **Step 1: Create the README first**

Create `tests/integration/README_drive_integration.md`:

```markdown
# Real-Drive Integration Test

This directory contains a thread-safety test that exercises `GoogleDriveClient`
against real Google Drive, not mocks. It is gated behind the pytest marker
`requires_drive` and is **not run in CI**. You run it manually before merging
changes to `GoogleDriveClient`.

## One-time setup

1. Authenticate the Drive client as you normally would
   (`poetry run whatsapp` → settings → Google Drive connect).
2. Create a folder on Google Drive named `whatsapp-drive-integration-test`
   (or any name). Upload ~10 small binary files to it — any files will do;
   100 KB – 1 MB each is fine. Note the folder ID from the Drive URL
   (`https://drive.google.com/drive/folders/<THIS_PART>`).
3. Set the env var before running the test:

   ```bash
   export DRIVE_INTEGRATION_FIXTURE_FOLDER_ID=<the folder id>
   ```

## Running

```bash
poetry run pytest tests/integration/test_drive_client_concurrency.py -m requires_drive -v
```

The test will:
- Connect to Drive using your local credentials.
- List files in the fixture folder.
- Download all fixture files concurrently (4 worker threads, multiple rounds)
  and assert every download succeeded with no SSL or HTTP errors.

Expected runtime: 30s – 2min depending on file sizes and network.

## When to run

- Before merging any change to `whatsapp_chat_autoexport/google_drive/drive_client.py`.
- After any dependency bump of `google-api-python-client`, `httplib2`, or OpenSSL
  (including Python upgrades).
```

- [ ] **Step 2: Create the integration test**

Create `tests/integration/test_drive_client_concurrency.py`:

```python
"""
Real-Drive concurrency test for GoogleDriveClient.

GATED: This test requires live Google Drive credentials and a fixture folder
populated with small binary files. It is skipped by default and in CI.

Run locally with:

    export DRIVE_INTEGRATION_FIXTURE_FOLDER_ID=<drive folder id>
    poetry run pytest tests/integration/test_drive_client_concurrency.py \
        -m requires_drive -v

See tests/integration/README_drive_integration.md for setup.
"""
import hashlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.google_drive.auth import GoogleDriveAuth
from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient


pytestmark = [pytest.mark.integration, pytest.mark.requires_drive]


FIXTURE_FOLDER_ENV = "DRIVE_INTEGRATION_FIXTURE_FOLDER_ID"


def _fixture_folder_id() -> str:
    folder_id = os.environ.get(FIXTURE_FOLDER_ENV)
    if not folder_id:
        pytest.skip(
            f"Set {FIXTURE_FOLDER_ENV} to a Drive folder populated with "
            f"small fixture files. See README_drive_integration.md."
        )
    return folder_id


@pytest.fixture(scope="module")
def connected_client() -> GoogleDriveClient:
    auth = GoogleDriveAuth()
    client = GoogleDriveClient(auth=auth)
    assert client.connect(), "Failed to connect to Google Drive"
    return client


def test_concurrent_downloads_do_not_corrupt_each_other(connected_client, tmp_path):
    """Fire 4-wide concurrent downloads across all fixture files, repeated
    enough times to produce clear contention. Every download must succeed
    with content matching a pre-download sequential baseline."""
    folder_id = _fixture_folder_id()
    files = connected_client.list_files(folder_id=folder_id, page_size=100)
    assert files, (
        f"Fixture folder {folder_id} is empty. Upload a handful of small files "
        f"before running this test."
    )

    # Baseline: sequential downloads to establish expected hashes.
    baseline_hashes: dict[str, str] = {}
    baseline_dir = tmp_path / "baseline"
    for f in files:
        dest = baseline_dir / f["name"]
        assert connected_client.download_file(f["id"], dest, show_progress=False), (
            f"Baseline download failed for {f['name']}"
        )
        baseline_hashes[f["id"]] = hashlib.sha256(dest.read_bytes()).hexdigest()

    # Concurrent: 4 workers, enough rounds to drive contention.
    concurrent_dir = tmp_path / "concurrent"
    concurrent_dir.mkdir()
    # At least 20 downloads across 4 threads — enough to reliably trigger the
    # pre-fix SSL cascade in < 30s of wall time on a 1 Mbps line.
    rounds = max(1, 20 // len(files) + 1)
    jobs = [(f, r) for r in range(rounds) for f in files]

    def _do_download(file_and_round):
        file_meta, round_idx = file_and_round
        dest = concurrent_dir / f"{round_idx:02d}_{file_meta['name']}"
        ok = connected_client.download_file(file_meta["id"], dest, show_progress=False)
        if not ok:
            return (file_meta["id"], dest, None, "download returned False")
        try:
            actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        except Exception as e:
            return (file_meta["id"], dest, None, f"hash failed: {e}")
        return (file_meta["id"], dest, actual, None)

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_do_download, job) for job in jobs]
        for fut in as_completed(futures):
            file_id, dest, actual_hash, err = fut.result()
            if err:
                errors.append(f"{dest.name}: {err}")
                continue
            expected = baseline_hashes[file_id]
            if actual_hash != expected:
                errors.append(
                    f"{dest.name}: hash mismatch (expected {expected[:12]}, "
                    f"got {actual_hash[:12]})"
                )

    assert not errors, (
        "Concurrent downloads produced errors — thread-safety regression?\n"
        + "\n".join(errors)
    )
```

- [ ] **Step 3: Verify the file collects but is skipped by default**

Run: `poetry run pytest tests/integration/test_drive_client_concurrency.py --collect-only -q`
Expected: the test is collected. Output shows the test but it will skip when run without the env var.

Then run: `poetry run pytest tests/integration/test_drive_client_concurrency.py -q`
Expected: SKIPPED because `DRIVE_INTEGRATION_FIXTURE_FOLDER_ID` is not set, with message directing the reader to the README.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_drive_client_concurrency.py tests/integration/README_drive_integration.md
git commit -m "test(drive): real-Drive concurrency integration test (gated)"
```

---

## Task 14: Manual real-Drive integration test run

**Files:** (none)

- [ ] **Step 1: Follow the README to set up the fixture folder**

Open `tests/integration/README_drive_integration.md` and follow the "One-time setup" instructions: create a folder on Google Drive, upload ~10 small files to it, and note the folder ID.

- [ ] **Step 2: Export the fixture folder ID**

```bash
export DRIVE_INTEGRATION_FIXTURE_FOLDER_ID=<the folder id you created>
```

- [ ] **Step 3: Run the real-Drive integration test**

```bash
poetry run pytest tests/integration/test_drive_client_concurrency.py -m requires_drive -v
```

Expected: PASS within ~30 s – 2 min. No SSL errors in output.

- [ ] **Step 4: If it fails with SSL errors, STOP and investigate**

This is the exact class of bug we're fixing. If the test fails with `WRONG_VERSION_NUMBER`, `UNEXPECTED_RECORD`, `IncompleteRead`, or similar, it means the lock is not wrapping something it should. Re-examine `download_file` first; the `next_chunk()` loop is the most likely suspect.

- [ ] **Step 5: (No commit — this is a verification task.)**

---

## Task 15: On-device smoke test

**Files:** (none)

This is the acceptance gate. The unit tests prove the lock is correct; the integration test proves it works against real Drive; this proves it works end-to-end through `ParallelPipeline`.

- [ ] **Step 1: Clean up the Drive backlog from 2026-04-16**

In a browser, go to Drive and delete all files matching "WhatsApp Chat with …" from the root folder. There were ~320 of them after the previous failed run. The revised discovery-sweep behaviour (F2) is NOT in this plan, so cleaning up manually is required before the smoke test or the sweep will pick up the backlog and obscure the result.

- [ ] **Step 2: Clean the local transcription cache**

```bash
rm -rf ~/.whatsapp_exports_cache/
```

(The cache was introduced in the reverted Fix 4+5 work; it should not exist on current `main`, but the smoke test before that did create it. Remove it for a clean baseline.)

- [ ] **Step 3: Ensure phone is connected, unlocked, and on the main WhatsApp screen**

- [ ] **Step 4: Run the smoke test**

```bash
poetry run whatsapp --headless \
  --output ~/whatsapp_exports_test \
  --auto-select \
  --limit 5 \
  --no-output-media
```

- [ ] **Step 5: Observe the run**

Watch the stderr log. Acceptance criteria:

- No `SSL: WRONG_VERSION_NUMBER`, `SSL: UNEXPECTED_RECORD`, `read operation timed out`, or `IncompleteRead` errors.
- No segmentation fault.
- Process exits with code 0.
- 5 chats exported and processed (or the process legitimately stops for an unrelated reason — e.g., running out of chats in auto-select — in which case the output directory should still contain the exported chats cleanly).

- [ ] **Step 6: If the smoke test passes, proceed to the finishing-a-development-branch skill**

- [ ] **Step 7: If the smoke test fails, STOP and write a new failure report**

Pattern from `docs/failure-reports/2026-04-18-pipeline-throughput-smoke-regression.md`. Do NOT merge. Do NOT push. Investigate the new failure mode.

- [ ] **Step 8: (No commit — this is a verification task.)**

---

## Self-Review Notes

**Spec coverage check:**
- Lock location (instance attribute on `GoogleDriveClient`) → Task 2.
- Lock wraps: `list_files` → 3, `get_file_metadata` → 4, `delete_file` → 5, `move_file` → 6, `download_file` + full `next_chunk()` loop → 7, `poll_for_new_export` → 8. `list_whatsapp_exports` calls through `list_files`, covered in Task 10.
- Module docstring note about non-reentrant locking → Task 2.
- `Lock` not `RLock` → Task 2 (explicit use of `threading.Lock`).
- Unit tests for: lock presence, lock acquired during each method's service calls, exception release, no deadlock in composition, concurrent serialization → Tasks 2, 3, 4, 5, 6, 7, 8, 9, 10, 11.
- `connect()` NOT locked → preserved (not mentioned in any task).
- Real-Drive integration test, `requires_drive` marker, skipped by default → Tasks 1, 13, 14.
- Setup README for integration test → Task 13.
- Smoke test as acceptance gate → Task 15.

**Placeholder scan:** no "TBD" / "TODO" / "implement later" anywhere in the plan. Every code step shows complete code.

**Type consistency:** method signatures unchanged from the existing `GoogleDriveClient`. Only the bodies change. `_service_lock` is introduced in Task 2 and referenced consistently everywhere after.

**Scope check:** Single subsystem (`GoogleDriveClient` thread-safety). One test file, one source file, plus integration test scaffolding. Self-contained.
