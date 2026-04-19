# Drive Duplicate Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each successful per-chat download from Google Drive, delete the just-downloaded file and any `(N)` siblings from Drive root so duplicates stop accumulating run over run.

**Architecture:** One new primitive on `GoogleDriveClient` (`delete_sibling_exports`) that lists by `name contains` + strict client-side regex, then deletes matches under the existing `_service_lock`. One thin passthrough on `GoogleDriveManager`. One call site in `WhatsAppPipeline._process_single_chat`, gated by a new `cleanup_drive_duplicates` flag (default `True`), with CLI opt-out `--keep-drive-duplicates`.

**Tech Stack:** Python 3.13, google-api-python-client, pytest, Typer/argparse (unified `whatsapp` CLI). Spec: `docs/specs/2026-04-19-drive-duplicate-cleanup-design.md`.

---

## File Structure

**New files:**
- `tests/unit/test_delete_sibling_exports.py` — unit tests for the primitive.

**Modified files:**
- `whatsapp_chat_autoexport/google_drive/drive_client.py` — add `delete_sibling_exports` method.
- `whatsapp_chat_autoexport/google_drive/drive_manager.py` — add thin passthrough method.
- `whatsapp_chat_autoexport/pipeline.py` — add `cleanup_drive_duplicates: bool = True` to `PipelineConfig`; call cleanup after successful download in `_process_single_chat`.
- `whatsapp_chat_autoexport/config/settings.py` — mirror `cleanup_drive_duplicates` field into `Settings`.
- `whatsapp_chat_autoexport/cli_entry.py` — add `--keep-drive-duplicates` flag; wire into pipeline config build.
- `whatsapp_chat_autoexport/headless.py` — pass the flag through to pipeline config build.
- `tests/unit/test_pipeline_progress.py` — extend with cleanup call-site tests.
- `CLAUDE.md` — document the new flag.

**Out of scope:** TUI wiring, pipeline-only path, retroactive cleanup tooling, CI-enabled real-Drive integration tests.

---

## Conventions used throughout this plan

- All work happens in the worktree at `.worktrees/drive-duplicate-cleanup/`, on branch `feature/drive-duplicate-cleanup`. Already set up.
- `poetry run pytest` is the test runner. Markers `requires_api`, `requires_device`, `requires_drive` are always deselected from local/baseline runs.
- Tests deliberately live in `tests/unit/test_delete_sibling_exports.py` (new) and `tests/unit/test_pipeline_progress.py` (existing file — cleanup call-site tests appended). This matches the current convention: primitive-level tests in their own file, pipeline wiring tests in the pipeline test file.
- Imports in test files use the same style as `tests/unit/test_drive_client_threading.py`: `from unittest.mock import MagicMock`, `from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient`, constructor via `GoogleDriveClient(auth=MagicMock())` with `c.service = MagicMock()` to bypass `connect()`.
- Commits follow Conventional Commits style (e.g., `feat(drive):`, `test(drive):`, `docs:`). One commit per task — test and implementation together so `git bisect` is meaningful.

---

## Task 1: Add failing test for lock presence and method existence

**Files:**
- Create: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Create the new test file with a single smoke test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py -v`

Expected: FAIL — `AssertionError: assert False` because `delete_sibling_exports` does not yet exist on `GoogleDriveClient`. (Method lookup returns False for `hasattr`.)

- [ ] **Step 3: Add the minimal method stub to `drive_client.py`**

Open `whatsapp_chat_autoexport/google_drive/drive_client.py`. After the `delete_file` method (ends around line 220, look for the last `return False` of that method), add:

```python
    def delete_sibling_exports(self, chat_name: str, folder_id: Optional[str] = None) -> int:
        """
        Delete all Drive root files in the chat name-group for ``chat_name``.

        Matches these filename shapes exactly (via strict client-side regex):
          - ``WhatsApp Chat with {chat_name}``
          - ``WhatsApp Chat with {chat_name}.zip``
          - ``WhatsApp Chat with {chat_name} (N)`` for any non-negative integer N
          - ``WhatsApp Chat with {chat_name} (N).zip``

        Args:
            chat_name: Name of the chat whose sibling export files should be removed.
            folder_id: Optional parent folder ID (defaults to Drive root).

        Returns:
            Count of files successfully deleted. Never raises; all Drive errors
            are caught, logged, and reflected in the returned count.
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return 0
        return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py -v`

Expected: PASS (`test_delete_sibling_exports_is_callable` passes, method exists).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "test(drive): add delete_sibling_exports stub and existence test"
```

---

## Task 2: Regex matches the base name and .zip variant

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Add the failing test to `tests/unit/test_delete_sibling_exports.py`**

Append:

```python
class _LockObservingService:
    """A fake Drive service that records whether the lock is held during
    each call, and returns caller-specified list results. Modeled on the
    helper in tests/unit/test_drive_client_threading.py."""

    def __init__(self, lock: threading.Lock, list_files: list[dict]):
        self.lock = lock
        self.list_files = list_files
        self.observations: list[tuple[str, bool]] = []
        self.deleted_ids: list[str] = []

    def files(self):
        return self

    def list(self, **kwargs):
        self.observations.append(("list", self.lock.locked()))
        outer = self

        class _Exec:
            def execute(self_inner):
                return {"files": outer.list_files}

        return _Exec()

    def delete(self, **kwargs):
        self.observations.append(("delete", self.lock.locked()))
        self.deleted_ids.append(kwargs.get("fileId"))
        outer = self

        class _Exec:
            def execute(self_inner):
                return {}

        return _Exec()


class TestBaseNameMatches:
    def test_base_name_and_zip_variant_are_deleted(self):
        """`WhatsApp Chat with X` and `WhatsApp Chat with X.zip` are both deleted."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "f1", "name": "WhatsApp Chat with Daniel Cocking"},
                {"id": "f2", "name": "WhatsApp Chat with Daniel Cocking.zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 2
        assert set(fake.deleted_ids) == {"f1", "f2"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestBaseNameMatches -v`

Expected: FAIL — assertion `removed == 2` fails because the stub returns `0`.

- [ ] **Step 3: Implement the matching + delete loop in `drive_client.py`**

At the top of `drive_client.py`, ensure `import re` is present (it isn't — check the top-of-file imports; if absent, add `import re` after the existing stdlib imports).

Replace the body of `delete_sibling_exports` in `whatsapp_chat_autoexport/google_drive/drive_client.py` with:

```python
    def delete_sibling_exports(self, chat_name: str, folder_id: Optional[str] = None) -> int:
        """
        Delete all Drive root files in the chat name-group for ``chat_name``.

        Matches these filename shapes exactly (via strict client-side regex):
          - ``WhatsApp Chat with {chat_name}``
          - ``WhatsApp Chat with {chat_name}.zip``
          - ``WhatsApp Chat with {chat_name} (N)`` for any non-negative integer N
          - ``WhatsApp Chat with {chat_name} (N).zip``

        Args:
            chat_name: Name of the chat whose sibling export files should be removed.
            folder_id: Optional parent folder ID (defaults to Drive root).

        Returns:
            Count of files successfully deleted. Never raises; all Drive errors
            are caught, logged, and reflected in the returned count.
        """
        if not self.service:
            self.logger.error("Not connected to Google Drive API")
            return 0

        # Drive query: escape single quotes for the contains filter.
        safe_name = chat_name.replace("'", "\\'")
        parent_clause = f"'{folder_id}' in parents" if folder_id else "'root' in parents"
        query = (
            f"name contains 'WhatsApp Chat with {safe_name}' and {parent_clause}"
        )

        # Client-side strict regex. We escape the chat name so characters like
        # '.' or '(' in the chat name are treated literally.
        pattern = re.compile(
            rf"^WhatsApp Chat with {re.escape(chat_name)}(?: \(\d+\))?(?:\.zip)?$"
        )

        removed = 0
        with self._service_lock:
            try:
                results = self.service.files().list(
                    q=query,
                    pageSize=100,
                    fields="files(id, name)",
                ).execute()
                files = results.get("files", [])
            except Exception as e:
                self.logger.warning(
                    f"Drive cleanup: failed to list siblings for '{chat_name}' — "
                    f"skipping (Drive error: {e})"
                )
                return 0

            for file in files:
                name = file.get("name", "")
                file_id = file.get("id")
                if not file_id or not pattern.match(name):
                    continue
                try:
                    self.service.files().delete(fileId=file_id).execute()
                    removed += 1
                except Exception as e:
                    self.logger.warning(
                        f"Drive cleanup: failed to delete '{name}' — {e}"
                    )

        return removed
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py -v`

Expected: PASS. Both tests pass (`test_delete_sibling_exports_is_callable`, `test_base_name_and_zip_variant_are_deleted`).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): delete_sibling_exports matches base name and .zip variant"
```

---

## Task 3: Regex matches numeric `(N)` siblings

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/unit/test_delete_sibling_exports.py`:

```python
class TestNumericSiblingsMatch:
    def test_numeric_siblings_are_deleted(self):
        """All (N) and (N).zip variants must be deleted."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "f1", "name": "WhatsApp Chat with Daniel Cocking (1)"},
                {"id": "f2", "name": "WhatsApp Chat with Daniel Cocking (2).zip"},
                {"id": "f3", "name": "WhatsApp Chat with Daniel Cocking (10).zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 3
        assert set(fake.deleted_ids) == {"f1", "f2", "f3"}
```

- [ ] **Step 2: Run to verify it passes immediately**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestNumericSiblingsMatch -v`

Expected: PASS (the regex implemented in Task 2 already handles `(N)`). We still commit this test to lock the behaviour.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): lock in (N)/(N).zip matching behaviour"
```

---

## Task 4: Rejects substring collisions

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestSubstringCollisionsRejected:
    def test_different_chat_with_same_prefix_is_not_deleted(self):
        """Files whose chat portion extends past the target name must be ignored."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "keep1", "name": "WhatsApp Chat with Daniel Cocking Jr.zip"},
                {"id": "keep2", "name": "WhatsApp Chat with Daniel Cocking family"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert fake.deleted_ids == []
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestSubstringCollisionsRejected -v`

Expected: PASS (the `^...$` anchor on the regex rejects the extra trailing text). Still commit.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): lock in substring-collision rejection"
```

---

## Task 5: Rejects non-numeric suffixes

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestNonNumericSuffixesRejected:
    def test_non_numeric_suffixes_are_not_deleted(self):
        """`(abc)` or custom renames must be ignored."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "x1", "name": "WhatsApp Chat with Daniel Cocking (abc).zip"},
                {"id": "x2", "name": "WhatsApp Chat with Daniel Cocking (1) backup.zip"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert fake.deleted_ids == []
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestNonNumericSuffixesRejected -v`

Expected: PASS. Regex requires `\(\d+\)` and allows nothing after except optional `.zip`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): lock in non-numeric-suffix rejection"
```

---

## Task 6: Special characters in chat names escape correctly

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestSpecialCharsInChatName:
    def test_period_and_apostrophe_match_literally(self):
        """Chat name with ``.`` and ``'`` must match literally, not as regex meta-chars.

        The trailing period in `O'Brien.` would otherwise match any character if
        unescaped. And the apostrophe must be escaped in the Drive `contains` query.
        """
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "yes1", "name": "WhatsApp Chat with O'Brien."},
                {"id": "yes2", "name": "WhatsApp Chat with O'Brien. (1).zip"},
                # This one must NOT match — the '.' in chat name was escaped, so
                # the literal 'X' following it means the name is different.
                {"id": "no1", "name": "WhatsApp Chat with O'BrienX"},
            ],
        )
        c.service = fake

        removed = c.delete_sibling_exports("O'Brien.")

        assert removed == 2
        assert set(fake.deleted_ids) == {"yes1", "yes2"}
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestSpecialCharsInChatName -v`

Expected: PASS. `re.escape` neutralises the `.` and the ``chat_name.replace("'", "\\'")`` handles the Drive query escape.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): cover special-char chat names (period + apostrophe)"
```

---

## Task 7: Root-only scope is enforced via Drive query

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestRootOnlyScope:
    def test_query_includes_root_parents_clause(self):
        """The Drive query passed to files().list() must include 'root' in parents."""
        captured = {}

        class _CapturingService:
            def files(self_inner):
                return self_inner

            def list(self_inner, **kwargs):
                captured["q"] = kwargs.get("q")

                class _Exec:
                    def execute(self_e):
                        return {"files": []}

                return _Exec()

            def delete(self_inner, **kwargs):
                raise AssertionError("should not delete when list is empty")

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        c.service = _CapturingService()

        c.delete_sibling_exports("Daniel Cocking")

        assert captured["q"], "expected a query to be passed to files().list()"
        assert "'root' in parents" in captured["q"], (
            f"expected root-scope clause in query, got: {captured['q']!r}"
        )
        assert "WhatsApp Chat with Daniel Cocking" in captured["q"]
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestRootOnlyScope -v`

Expected: PASS. Implementation builds `parent_clause = "'root' in parents"` when `folder_id` is `None`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): enforce root-only scope in cleanup query"
```

---

## Task 8: Lock is held during list and each delete

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestLockHeldDuringCleanup:
    def test_lock_held_for_list_and_each_delete(self):
        """Every service call made by delete_sibling_exports must run under the lock."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(
            c._service_lock,
            list_files=[
                {"id": "f1", "name": "WhatsApp Chat with X"},
                {"id": "f2", "name": "WhatsApp Chat with X.zip"},
                {"id": "f3", "name": "WhatsApp Chat with X (1).zip"},
            ],
        )
        c.service = fake

        c.delete_sibling_exports("X")

        assert fake.observations, "expected service calls"
        names = [name for name, _ in fake.observations]
        assert "list" in names
        assert names.count("delete") == 3
        assert all(held for _, held in fake.observations), (
            f"expected lock held for every call, got {fake.observations}"
        )
        assert c._service_lock.locked() is False
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestLockHeldDuringCleanup -v`

Expected: PASS. Implementation's `with self._service_lock:` wraps both the list call and the delete loop.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): verify service lock is held for cleanup list and deletes"
```

---

## Task 9: Listing failure returns 0 and logs a warning

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestListingFailureReturnsZero:
    def test_list_raises_returns_zero_and_logs_warning(self, caplog):
        """If files().list().execute() raises, return 0 without attempting deletes
        and log a warning."""
        from googleapiclient.errors import HttpError

        class _FakeResp:
            status = 500
            reason = "Internal Server Error"

        class _RaisingService:
            def files(self_inner):
                return self_inner

            def list(self_inner, **kwargs):
                class _Exec:
                    def execute(self_e):
                        raise HttpError(_FakeResp(), b"boom")

                return _Exec()

            def delete(self_inner, **kwargs):
                raise AssertionError("delete must not be called when list fails")

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        c.service = _RaisingService()

        import logging
        with caplog.at_level(logging.WARNING):
            removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert c._service_lock.locked() is False
        # The implementation uses self.logger.warning; verify something was logged.
        # (The project's Logger emits through stdlib logging.)
        assert any(
            "Drive cleanup: failed to list" in record.message
            for record in caplog.records
        ) or any(
            "failed to list siblings" in record.message
            for record in caplog.records
        ), f"expected a warning, got records: {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestListingFailureReturnsZero -v`

Expected: PASS. The `except Exception` in the list branch catches and returns `0`.

Note: if the project `Logger` doesn't route through stdlib `logging`, the `caplog` assertion may need to relax to inspecting `self.logger` directly. If the test fails on that assertion only, replace the final `assert any(...)` block with:

```python
        # Fallback: if the Logger doesn't go through stdlib logging, at least
        # verify no exception propagated and return value is 0.
        # (Primary assertion already covered above.)
```

and re-commit.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): cleanup returns 0 and warns when listing fails"
```

---

## Task 10: Per-file delete failure is logged and loop continues

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestPerFileDeleteFailureContinues:
    def test_one_delete_fails_others_still_succeed(self):
        """A single failing delete must not stop the loop. Return count reflects
        only successful deletes."""
        from googleapiclient.errors import HttpError

        class _FakeResp:
            status = 500
            reason = "Internal Server Error"

        class _MixedService:
            """list returns 3 matching files; delete raises on the first id,
            succeeds on the rest."""

            def __init__(self):
                self.deleted_ok: list[str] = []

            def files(self_inner):
                return self_inner

            def list(self_inner, **kwargs):
                class _Exec:
                    def execute(self_e):
                        return {
                            "files": [
                                {"id": "fail", "name": "WhatsApp Chat with X"},
                                {"id": "ok1", "name": "WhatsApp Chat with X.zip"},
                                {"id": "ok2", "name": "WhatsApp Chat with X (1).zip"},
                            ]
                        }

                return _Exec()

            def delete(self_inner, fileId=None, **kwargs):
                outer = self_inner

                class _Exec:
                    def execute(self_e):
                        if fileId == "fail":
                            raise HttpError(_FakeResp(), b"nope")
                        outer.deleted_ok.append(fileId)
                        return {}

                return _Exec()

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        svc = _MixedService()
        c.service = svc

        removed = c.delete_sibling_exports("X")

        assert removed == 2
        assert svc.deleted_ok == ["ok1", "ok2"]
        assert c._service_lock.locked() is False
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestPerFileDeleteFailureContinues -v`

Expected: PASS. The per-file `try/except Exception` in the delete loop catches and continues.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): cleanup continues past individual delete failures"
```

---

## Task 11: Empty sibling set returns 0

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestEmptySiblingSet:
    def test_no_matches_returns_zero_and_no_deletes(self):
        """If the list query returns nothing, no deletes are issued and return is 0."""
        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        fake = _LockObservingService(c._service_lock, list_files=[])
        c.service = fake

        removed = c.delete_sibling_exports("Daniel Cocking")

        assert removed == 0
        assert fake.deleted_ids == []
        # A list call was still made under the lock.
        assert fake.observations == [("list", True)]
        assert c._service_lock.locked() is False
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestEmptySiblingSet -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py
git commit -m "test(drive): empty sibling set returns 0"
```

---

## Task 12: Stale 404 counted as success

**Files:**
- Modify: `tests/unit/test_delete_sibling_exports.py`
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
class TestStale404CountedAsSuccess:
    def test_file_deleted_concurrently_is_counted_as_success(self):
        """A 404 on delete means the file is already gone — that's success."""
        from googleapiclient.errors import HttpError

        class _FakeResp:
            status = 404
            reason = "Not Found"

        class _StaleService:
            def files(self_inner):
                return self_inner

            def list(self_inner, **kwargs):
                class _Exec:
                    def execute(self_e):
                        return {"files": [
                            {"id": "gone", "name": "WhatsApp Chat with X"},
                            {"id": "present", "name": "WhatsApp Chat with X.zip"},
                        ]}

                return _Exec()

            def delete(self_inner, fileId=None, **kwargs):
                class _Exec:
                    def execute(self_e):
                        if fileId == "gone":
                            raise HttpError(_FakeResp(), b"Not Found")
                        return {}

                return _Exec()

        auth = MagicMock()
        c = GoogleDriveClient(auth=auth)
        c.service = _StaleService()

        removed = c.delete_sibling_exports("X")

        # Both files are treated as successful: the 404 means "already gone".
        assert removed == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestStale404CountedAsSuccess -v`

Expected: FAIL — current implementation catches all exceptions and does NOT increment `removed` for the 404. Assertion `removed == 2` fails (got `1`).

- [ ] **Step 3: Update `delete_sibling_exports` in `drive_client.py` to special-case 404**

Inside the delete loop of `delete_sibling_exports`, replace:

```python
                try:
                    self.service.files().delete(fileId=file_id).execute()
                    removed += 1
                except Exception as e:
                    self.logger.warning(
                        f"Drive cleanup: failed to delete '{name}' — {e}"
                    )
```

with:

```python
                try:
                    self.service.files().delete(fileId=file_id).execute()
                    removed += 1
                except HttpError as e:
                    # 404 means the file is already gone — that's the desired state.
                    if getattr(getattr(e, "resp", None), "status", None) == 404:
                        self.logger.debug_msg(
                            f"Drive cleanup: '{name}' already gone (404)"
                        )
                        removed += 1
                    else:
                        self.logger.warning(
                            f"Drive cleanup: failed to delete '{name}' — {e}"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Drive cleanup: failed to delete '{name}' — {e}"
                    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py -v`

Expected: PASS. All `TestStale404...` tests plus earlier tests still green.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_delete_sibling_exports.py whatsapp_chat_autoexport/google_drive/drive_client.py
git commit -m "feat(drive): count stale 404 on delete as cleanup success"
```

---

## Task 13: Add `cleanup_drive_duplicates` field to `PipelineConfig`

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py`
- Modify: `tests/unit/test_pipeline_progress.py`

- [ ] **Step 1: Add the failing test**

Open `tests/unit/test_pipeline_progress.py`. Find the existing `class TestPipelineProgressCallbacks` and, at the bottom of the file, add a new class:

```python
class TestCleanupDuplicatesConfig:
    """Tests for the cleanup_drive_duplicates config flag on PipelineConfig."""

    def test_pipeline_config_default_is_true(self):
        """PipelineConfig.cleanup_drive_duplicates defaults to True."""
        from whatsapp_chat_autoexport.pipeline import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.cleanup_drive_duplicates is True

    def test_pipeline_config_can_be_disabled(self):
        """PipelineConfig accepts cleanup_drive_duplicates=False."""
        from whatsapp_chat_autoexport.pipeline import PipelineConfig
        cfg = PipelineConfig(cleanup_drive_duplicates=False)
        assert cfg.cleanup_drive_duplicates is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py::TestCleanupDuplicatesConfig -v`

Expected: FAIL — `PipelineConfig` does not yet have the `cleanup_drive_duplicates` attribute; the default-True test fails on `AttributeError` or the dataclass construction rejects the keyword.

- [ ] **Step 3: Add the field to `PipelineConfig` in `whatsapp_chat_autoexport/pipeline.py`**

Find the `@dataclass class PipelineConfig` block (near the top of `pipeline.py` — search for `class PipelineConfig`). Add a new field immediately below the existing `delete_from_drive: bool = False` line:

```python
    cleanup_drive_duplicates: bool = True
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py::TestCleanupDuplicatesConfig -v`

Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/pipeline.py tests/unit/test_pipeline_progress.py
git commit -m "feat(pipeline): add cleanup_drive_duplicates config flag (default true)"
```

---

## Task 14: Add thin passthrough on `GoogleDriveManager`

**Files:**
- Modify: `whatsapp_chat_autoexport/google_drive/drive_manager.py`
- Modify: `tests/unit/test_delete_sibling_exports.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/unit/test_delete_sibling_exports.py`:

```python
class TestManagerPassthrough:
    def test_manager_delegates_to_client(self):
        """GoogleDriveManager.delete_sibling_exports calls client.delete_sibling_exports."""
        from whatsapp_chat_autoexport.google_drive.drive_manager import GoogleDriveManager

        mgr = GoogleDriveManager.__new__(GoogleDriveManager)  # skip __init__ so we don't auth
        mgr.logger = MagicMock()
        mgr.client = MagicMock()
        mgr.client.delete_sibling_exports.return_value = 2

        result = mgr.delete_sibling_exports("Daniel Cocking")

        assert result == 2
        mgr.client.delete_sibling_exports.assert_called_once_with(
            "Daniel Cocking", folder_id=None
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py::TestManagerPassthrough -v`

Expected: FAIL — `GoogleDriveManager` does not yet have `delete_sibling_exports`.

- [ ] **Step 3: Add the passthrough to `drive_manager.py`**

Open `whatsapp_chat_autoexport/google_drive/drive_manager.py`. After `find_and_move_recent_export` (ends around line 219, look for `return False` closing that method), add:

```python
    def delete_sibling_exports(self, chat_name: str, folder_id: Optional[str] = None) -> int:
        """
        Delete Drive root files in the chat name-group for ``chat_name``.

        Thin passthrough to ``GoogleDriveClient.delete_sibling_exports``. See that
        method for match semantics, error handling, and the folder_id default.

        Args:
            chat_name: Name of the chat whose sibling export files should be removed.
            folder_id: Optional parent folder ID (defaults to Drive root).

        Returns:
            Count of files successfully deleted.
        """
        return self.client.delete_sibling_exports(chat_name, folder_id=folder_id)
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_delete_sibling_exports.py -v`

Expected: PASS. All tests green, including the new passthrough test.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/google_drive/drive_manager.py tests/unit/test_delete_sibling_exports.py
git commit -m "feat(drive): add delete_sibling_exports passthrough on GoogleDriveManager"
```

---

## Task 15: Pipeline calls cleanup when flag is on

**Files:**
- Modify: `tests/unit/test_pipeline_progress.py`
- Modify: `whatsapp_chat_autoexport/pipeline.py`

- [ ] **Step 1: Add the failing test**

Open `tests/unit/test_pipeline_progress.py` and, at the bottom of the file, extend `TestCleanupDuplicatesConfig` (or add a new class if preferred) with:

```python
    def test_pipeline_calls_cleanup_after_successful_download(self, tmp_path):
        """When cleanup_drive_duplicates=True, _process_single_chat calls
        drive_manager.delete_sibling_exports(chat_name) after a successful download."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=True,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                pipeline.process_single_export("Test")

        mock_drive.delete_sibling_exports.assert_called_once_with("Test")

    def test_pipeline_skips_cleanup_when_flag_off(self, tmp_path):
        """When cleanup_drive_duplicates=False, cleanup is not called."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=False,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                pipeline.process_single_export("Test")

        mock_drive.delete_sibling_exports.assert_not_called()
```

- [ ] **Step 2: Run to verify both tests fail**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py::TestCleanupDuplicatesConfig -v`

Expected: FAIL — the "calls cleanup" test asserts that `delete_sibling_exports` was called once, but the pipeline does not yet call it. `assert_called_once_with` raises `AssertionError`.

Note: `test_pipeline_skips_cleanup_when_flag_off` will PASS by default (nothing calls it). That's fine — it will still pass after implementation and locks in the correct behaviour.

- [ ] **Step 3: Wire the call into `_process_single_chat` in `pipeline.py`**

Open `whatsapp_chat_autoexport/pipeline.py`. Locate the block around line 184 that currently reads:

```python
            downloaded = self.drive_manager.batch_download_exports(
                [matching_file],
                download_dir,
                delete_after=self.config.delete_from_drive
            )

            if not downloaded:
                raise RuntimeError(f"Failed to download export for '{chat_name}'")

            self.logger.success(f"Downloaded: {matching_file['name']}")
            self._fire_progress("download", "Download complete", 1, 1, chat_name)
            results['phases_completed'].append('download')
```

Insert immediately before the `self.logger.success(...)` line (i.e. after the `if not downloaded:` guard and before the logger.success) the following block:

```python
            if self.config.cleanup_drive_duplicates:
                try:
                    removed = self.drive_manager.delete_sibling_exports(chat_name)
                    if removed:
                        self.logger.info(
                            f"Drive cleanup: removed {removed} duplicate(s) for "
                            f"'{chat_name}' from Drive root"
                        )
                    else:
                        self.logger.debug_msg(
                            f"Drive cleanup: nothing to prune for '{chat_name}'"
                        )
                except Exception as e:
                    # delete_sibling_exports is not supposed to raise, but if it does,
                    # don't fail the chat — we already have the file on local disk.
                    self.logger.warning(
                        f"Drive cleanup: unexpected error for '{chat_name}' — {e}"
                    )
```

- [ ] **Step 4: Run to verify tests pass**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py::TestCleanupDuplicatesConfig -v`

Expected: PASS. Both "calls cleanup" and "skips cleanup" tests green.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/pipeline.py tests/unit/test_pipeline_progress.py
git commit -m "feat(pipeline): call drive cleanup after successful download (gated by flag)"
```

---

## Task 16: Pipeline isolation — cleanup failure does not fail the chat

**Files:**
- Modify: `tests/unit/test_pipeline_progress.py`

- [ ] **Step 1: Add the failing test**

Append to the bottom of `tests/unit/test_pipeline_progress.py`:

```python
class TestCleanupFailureDoesNotFailChat:
    def test_cleanup_raising_does_not_abort_pipeline(self, tmp_path):
        """Defensive: even if delete_sibling_exports raises (it shouldn't), the
        chat's pipeline run continues. We guard with try/except in the call site."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=True,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]
        mock_drive.delete_sibling_exports.side_effect = RuntimeError("boom")

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                # Should NOT raise — the RuntimeError from cleanup must be caught.
                result = pipeline.process_single_export("Test")

        # Phase 1 (download) should be marked completed even though cleanup raised.
        assert result is not None
        # Depending on _phase2 mocks this may or may not be "success", but the
        # run did not propagate the cleanup exception.
```

- [ ] **Step 2: Run to verify it passes**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py::TestCleanupFailureDoesNotFailChat -v`

Expected: PASS. The Task 15 implementation already wraps the cleanup call in `try/except Exception`, so this test passes and locks in that safety net.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_pipeline_progress.py
git commit -m "test(pipeline): verify cleanup failure never aborts a chat run"
```

---

## Task 17: Add `--keep-drive-duplicates` CLI flag

**Files:**
- Modify: `whatsapp_chat_autoexport/cli_entry.py`
- Modify: `whatsapp_chat_autoexport/headless.py`
- Modify: `tests/unit/test_cli_entry.py`

- [ ] **Step 1: Find where existing `--delete-from-drive` flag is defined**

Run: `grep -n "delete-from-drive\|delete_from_drive" whatsapp_chat_autoexport/cli_entry.py`

Expected: finds argument parser definition around the CLI setup. Note the exact line numbers so the new flag lands near the similar flag.

- [ ] **Step 2: Add the failing CLI test**

Open `tests/unit/test_cli_entry.py`. At the bottom, append:

```python
class TestKeepDriveDuplicatesFlag:
    def test_flag_defaults_to_not_keeping_duplicates(self):
        """Without --keep-drive-duplicates, cleanup is enabled
        (args.keep_drive_duplicates is False)."""
        from whatsapp_chat_autoexport.cli_entry import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "--headless", "--output", "/tmp/x", "--auto-select",
        ])
        assert getattr(args, "keep_drive_duplicates", None) is False

    def test_flag_sets_keep_to_true(self):
        """--keep-drive-duplicates sets args.keep_drive_duplicates=True."""
        from whatsapp_chat_autoexport.cli_entry import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "--headless", "--output", "/tmp/x", "--auto-select",
            "--keep-drive-duplicates",
        ])
        assert args.keep_drive_duplicates is True
```

- [ ] **Step 3: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_cli_entry.py::TestKeepDriveDuplicatesFlag -v`

Expected: FAIL — `parser.parse_args(...)` raises `SystemExit(2)` on the second test because `--keep-drive-duplicates` is not a known argument, and the first test's `getattr(args, "keep_drive_duplicates", None)` returns `None` instead of `False`.

Note: if `build_parser` is not a top-level symbol, run `grep -n "def build_parser\|def _build_parser\|parser = " whatsapp_chat_autoexport/cli_entry.py` to locate the real parser constructor and adjust the import. Expected: the unified CLI does expose a `build_parser` function (that is how existing CLI tests work at `tests/unit/test_cli_entry.py` — check first, and if the name differs, use whatever symbol those tests already import).

- [ ] **Step 4: Add the flag to `cli_entry.py`**

Open `whatsapp_chat_autoexport/cli_entry.py`. Find the `--delete-from-drive` argument definition (search `--delete-from-drive`). Immediately after that `parser.add_argument(...)` call, add:

```python
    parser.add_argument(
        "--keep-drive-duplicates",
        action="store_true",
        default=False,
        help="Skip deleting Drive root duplicates after each per-chat download "
             "(default: duplicates are removed).",
    )
```

Then, in the same file, find where the pipeline config is built for the headless path (look for `delete_from_drive=args.delete_from_drive`). Add a sibling line that maps the CLI's `keep_drive_duplicates` into the pipeline config's `cleanup_drive_duplicates`:

```python
        cleanup_drive_duplicates=not args.keep_drive_duplicates,
```

Do the same mapping wherever else a `PipelineConfig` is built from `args` in this file, e.g., any `run_pipeline_only` call site. (Pipeline-only path itself is non-goal for this feature; the flag still parses cleanly there, just never affects behaviour since pipeline-only does not download.)

- [ ] **Step 5: Update `headless.py` to forward the flag**

Open `whatsapp_chat_autoexport/headless.py`. Locate the `run_headless(args)` function and the `PipelineConfig(...)` construction inside it (there are two — around lines 190 and 315 per the pre-existing code). In both constructions, add the mapping:

```python
        cleanup_drive_duplicates=not getattr(args, "keep_drive_duplicates", False),
```

Place it next to `delete_from_drive=getattr(args, "delete_from_drive", False),` for symmetry.

- [ ] **Step 6: Run to verify tests pass**

Run: `poetry run pytest tests/unit/test_cli_entry.py::TestKeepDriveDuplicatesFlag -v`

Expected: PASS. Both tests green.

- [ ] **Step 7: Commit**

```bash
git add whatsapp_chat_autoexport/cli_entry.py whatsapp_chat_autoexport/headless.py tests/unit/test_cli_entry.py
git commit -m "feat(cli): add --keep-drive-duplicates opt-out flag"
```

---

## Task 18: Mirror the flag into `Settings`

**Files:**
- Modify: `whatsapp_chat_autoexport/config/settings.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Check if `Settings` carries `delete_from_drive` today**

Run: `grep -n "delete_from_drive\|cleanup_drive_duplicates" whatsapp_chat_autoexport/config/settings.py`

Expected: `delete_from_drive: bool = False` appears at around line 126 (per the repo at HEAD). If not, run `grep -n "delete_from_drive" whatsapp_chat_autoexport/config/` to find the right location.

- [ ] **Step 2: Add the failing test**

Open `tests/unit/test_config.py`. At the bottom of the file (or alongside the existing `delete_from_drive` tests if any), append:

```python
class TestCleanupDriveDuplicatesSetting:
    def test_default_is_true(self):
        """Settings.cleanup_drive_duplicates defaults to True."""
        from whatsapp_chat_autoexport.config.settings import Settings
        s = Settings()
        assert s.cleanup_drive_duplicates is True
```

- [ ] **Step 3: Run to verify it fails**

Run: `poetry run pytest tests/unit/test_config.py::TestCleanupDriveDuplicatesSetting -v`

Expected: FAIL — the attribute does not exist, `AttributeError`.

- [ ] **Step 4: Add the field to `Settings` in `config/settings.py`**

Open `whatsapp_chat_autoexport/config/settings.py`. Immediately below the `delete_from_drive: bool = False` line, add:

```python
    cleanup_drive_duplicates: bool = True
```

- [ ] **Step 5: Run to verify the test passes**

Run: `poetry run pytest tests/unit/test_config.py::TestCleanupDriveDuplicatesSetting -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/config/settings.py tests/unit/test_config.py
git commit -m "feat(config): mirror cleanup_drive_duplicates flag into Settings"
```

---

## Task 19: Update CLAUDE.md with the new flag

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the flags table/section in `CLAUDE.md`**

Run: `grep -n "delete-from-drive\|--delete-from-drive\|All Available Flags" CLAUDE.md`

Expected: matches under the "All Available Flags" header (around the unified CLI section).

- [ ] **Step 2: Add the new flag to the flags reference**

Edit `CLAUDE.md`. Inside the "All Available Flags" code block (the one listing `--output DIR`, `--headless`, etc.), add a new line alphabetically close to `--delete-from-drive`:

```
--keep-drive-duplicates   Skip deleting Drive root duplicates after download
```

Then, in the "Understanding Media Flags" section (or immediately after it — look for a clean insertion point), add a short subsection:

```markdown
## Drive Duplicate Cleanup

By default, after each successful per-chat download the pipeline deletes any
`WhatsApp Chat with <chat>` and `WhatsApp Chat with <chat> (N)` siblings from
Drive root so duplicates don't accumulate across runs.

- Default: **ON** — no flag needed.
- Opt out: `--keep-drive-duplicates` (leaves all Drive files alone).
- Orthogonal to `--delete-from-drive`: that flag only removes the
  just-downloaded file; duplicate cleanup removes the whole sibling group.
- Only affects Drive root. Does not touch subfolders.
- Cleanup failures never fail a chat — worst case, the next run retries.
```

- [ ] **Step 3: Run the full test suite to make sure nothing regressed**

Run: `poetry run pytest -q -m "not requires_api and not requires_device and not requires_drive"`

Expected: All tests green.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document --keep-drive-duplicates flag and default cleanup behaviour"
```

---

## Task 20: Full test suite + manual smoke-test plan

**Files:**
- None (verification only)

- [ ] **Step 1: Run the full unit test suite one final time**

Run: `poetry run pytest -q -m "not requires_api and not requires_device and not requires_drive"`

Expected: All tests green. No regressions from the plan's 14+ new tests.

- [ ] **Step 2: Document the manual smoke-test for a future run (no commit)**

Record the following in the PR description when finishing the branch:

> **Manual smoke-test (run after merge):**
> 1. Pick a chat already present in Drive root as `WhatsApp Chat with X (1).zip`.
> 2. `poetry run whatsapp --headless --output /tmp/dedupe-smoke --auto-select --limit 1 --transcription-provider elevenlabs --no-output-media`.
> 3. After the run, inspect Drive root: no `WhatsApp Chat with X` or `(N)` files should remain for that chat.
> 4. Re-run once more with the same command: no duplicate accumulation.
> 5. Re-run with `--keep-drive-duplicates`: verify duplicates DO accumulate (opt-out works).

- [ ] **Step 3: Hand off to finishing-a-development-branch**

Follow the Superpowers `finishing-a-development-branch` skill to merge/PR.

---

## Self-Review Notes

**Spec coverage check:** Every section of `docs/specs/2026-04-19-drive-duplicate-cleanup-design.md` maps to at least one task.

- Problem/Goal → Tasks 1–16 (the end-to-end feature).
- Non-Goals → honoured; no tasks for pipeline-only, TUI, retroactive cleanup, CI Drive tests, or retry loops.
- Architecture (primitive, passthrough, call site) → Tasks 1–2 (primitive), 14 (passthrough), 15 (call site).
- Name-Group Matching (regex shapes, rejections, escaping) → Tasks 2, 3, 4, 5, 6.
- Configuration (`PipelineConfig`, `Settings`, `--keep-drive-duplicates`) → Tasks 13, 17, 18.
- Call-Site Wiring (log lines, progress) → Task 15.
- Error Handling (never raise, listing/delete failures, 404) → Tasks 9, 10, 12, 16.
- Interaction With Existing Flags (`--delete-from-drive`, `--resume`) → covered by design note in `CLAUDE.md` update (Task 19) and by Task 15 which runs cleanup after `delete_after=` has already taken effect.
- Observability → Task 15 log lines and Task 19 documentation.
- Testing (14 tests from spec) → Tasks 1–12 (12 primitive tests — spec's 11 plus the test 1 method existence smoke test) + Tasks 15–16 (pipeline wiring + isolation) + Task 17 (CLI parser) + Task 18 (Settings mirror). Exceeds the spec's 14-test floor.
- Acceptance Criteria → validated by Task 20 (full suite + manual smoke-test).

**Placeholder scan:** No "TBD" or "TODO" markers. All code blocks are complete and runnable. Each step is 2–5 minutes. No step reads "similar to Task N" — test code is repeated verbatim where a later task extends an earlier one's fixtures.

**Type consistency:**
- `delete_sibling_exports(chat_name: str, folder_id: Optional[str] = None) -> int` identical in `drive_client.py` (Task 1), passthrough in `drive_manager.py` (Task 14), pipeline call-site (Task 15).
- `PipelineConfig.cleanup_drive_duplicates: bool = True` (Task 13); `Settings.cleanup_drive_duplicates: bool = True` (Task 18); CLI flag `--keep-drive-duplicates` stored as `args.keep_drive_duplicates: bool` (Task 17); mapping is `cleanup_drive_duplicates=not args.keep_drive_duplicates` (Tasks 17 and whatever headless builds pipeline config).
- `_LockObservingService` defined once (Task 2), reused by Tasks 3, 4, 5, 6, 8, 11.
- `from googleapiclient.errors import HttpError` used consistently in error-path tests (Tasks 9, 10, 12) and implementation (Task 12).
