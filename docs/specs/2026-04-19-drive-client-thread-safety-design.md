---
date: 2026-04-19
topic: drive-client-thread-safety
status: approved
related-failure-report: docs/failure-reports/2026-04-18-pipeline-throughput-smoke-regression.md
---

# Google Drive Client Thread-Safety — Design Spec

## Background

On 2026-04-18 a smoke test of the Fix 4+5 pipeline-throughput work crashed with a segmentation fault after ~30 seconds, preceded by a cascade of Google Drive SSL errors (`WRONG_VERSION_NUMBER`, `UNEXPECTED_RECORD`, `IncompleteRead`, `read operation timed out`). Root cause: `google-api-python-client`'s `service` object and the underlying `httplib2.Http` connection are not thread-safe. When multiple `ParallelPipeline` workers call `DriveClient` methods concurrently, they share one `Http` instance and corrupt each other's SSL streams.

See `docs/failure-reports/2026-04-18-pipeline-throughput-smoke-regression.md` for the full incident.

This spec covers **F1 only** — the thread-safety fix. F2 (discovery-sweep scope) and F3 (segfault diagnosis) are deliberately out of scope.

## Goal

Make `GoogleDriveClient` thread-safe by serializing all access to `self.service` through a single lock. Callers (`GoogleDriveManager`, `ParallelPipeline`, etc.) are unchanged; thread-safety is a property of the client itself.

## Non-goals

- **Per-thread service instances.** Simpler to add a lock than to refactor ownership.
- **Lock-free / concurrent downloads.** Drive I/O is not the pipeline's throughput bottleneck — transcription is.
- **F2: discovery-sweep scope control.** Separate follow-up. For the next smoke test, the user will manually clean up the ~320-file Drive backlog.
- **F3: segfault diagnosis.** Expected to disappear once the SSL cascade stops. If it reproduces after F1 ships, it becomes its own work item.
- **Re-introducing the Fix 4+5 throughput changes.** This fix ships on top of current `main` (commit `5d6d4bf`), which predates the reverted work. Re-introducing the cache, retry, and discovery-based listing is a separate future project.

## Architecture

### Where the lock lives

`whatsapp_chat_autoexport/google_drive/drive_client.py`, inside `GoogleDriveClient`:

```python
import threading

class GoogleDriveClient:
    def __init__(self, auth, logger=None):
        self.auth = auth
        self.logger = logger or Logger()
        self.service = None
        self._service_lock = threading.Lock()
```

One `Lock` per client instance. We only ever construct one client per process today, so this is effectively process-global for Drive access — which is exactly what we want.

### What the lock wraps

Every public method on `GoogleDriveClient` that touches `self.service`. That includes:

- `list_files`
- `download_file` — the **entire** `MediaIoBaseDownload.next_chunk()` loop must be inside the lock (each `next_chunk()` call re-enters the service)
- `delete_file`
- `move_file`
- `get_file_metadata`
- `list_whatsapp_exports` — delegates to `list_files`, so locks at the inner call
- `poll_for_new_export`
- (`connect` builds the service; does not need locking — called once at startup before any worker exists)

Pattern:

```python
def list_files(self, ...):
    if not self.service:
        ...
        return []
    with self._service_lock:
        try:
            results = self.service.files().list(...).execute()
            ...
            return files
        except HttpError as error:
            ...
            return []
```

### What callers see

Nothing changes. `GoogleDriveManager` and any future concurrent caller keep calling `GoogleDriveClient` methods the same way. Thread-safety is fully encapsulated in `GoogleDriveClient`.

### Lock type: `Lock`, not `RLock`

We use `threading.Lock` (non-reentrant) so that any accidental method-to-method recursion inside `GoogleDriveClient` deadlocks immediately rather than hiding a locking bug. Today no method on `GoogleDriveClient` calls another method that also locks — `list_whatsapp_exports` is the only internal caller, and it calls `list_files` which acquires the lock itself. This is the one place we must restructure: `list_whatsapp_exports` must not hold the lock when calling `list_files`.

Audit checklist for this rule:

- `list_whatsapp_exports` → calls `list_files` → OK (no outer lock held, lock is acquired in `list_files`)
- `find_folder_by_name` → calls `list_files` → OK (no outer lock held)
- All other methods → do not call other `GoogleDriveClient` methods

We'll add a module-level docstring note: "`GoogleDriveClient` methods must not call each other while holding `_service_lock`."

### Concurrency impact

All Drive operations become serialized. Downloads that were intended to run 4-wide under the reverted Fix 4+5 would run 1-wide. This is acceptable:

- Current `main` does not run concurrent Drive calls — today's code is sequential, so there is no regression.
- The fix makes the client *safe for future concurrent callers*. When the Fix 4+5 work is re-attempted, throughput on the pipeline as a whole will be governed by transcription (parallel inside `TranscriptionManager`), not by Drive I/O.
- Correctness > throughput. This is the bug that caused the revert.

## Error handling

No change. Existing `try/except HttpError` and `except Exception` blocks stay where they are, inside the `with` block. The lock is released by the `with` statement whether the body returns normally or raises.

## Testing

### Unit tests (in CI)

Added to `tests/unit/test_drive_client_threading.py` (new file):

1. **Lock exists and is a `threading.Lock`.** Construct a client, assert `isinstance(client._service_lock, type(threading.Lock()))`.
2. **Each locked method acquires the lock during execution.** Wrap `self.service` with a mock that records whether the lock was held at call time. For each method (`list_files`, `download_file`, `delete_file`, `move_file`, `get_file_metadata`, `poll_for_new_export`), assert the lock was held when the mocked service was called.
3. **Exceptions release the lock.** Make the mocked service raise `HttpError`; assert `client._service_lock.locked() is False` after the call returns.
4. **`list_whatsapp_exports` does not deadlock.** It calls `list_files` internally; this test proves the no-nested-locking rule is respected.

These tests use `unittest.mock` against the service object. They prove the locking contract; they do not prove thread-safety in the real `httplib2` stack.

### Real-Drive integration test (local-only, manual)

Added to `tests/integration/test_drive_client_concurrency.py` (new file), marked `@pytest.mark.requires_drive`, skipped by default and in CI.

- Builds a real `GoogleDriveClient` against the user's live Drive credentials.
- Expects a pre-created test folder on Drive containing ~10 small fixture files (uploaded by a one-time setup script committed with the test).
- Spins up `ThreadPoolExecutor(max_workers=4)` and issues 20 concurrent `download_file` calls across the fixture files.
- Passes if: all 20 downloads complete, all downloaded bytes match expected content, and no SSL errors are raised.

Setup instructions documented in a short README alongside the test:

- `tests/integration/README_drive_integration.md` explains how to create the fixture folder, generate the fixture files, and set `DRIVE_INTEGRATION_FIXTURE_FOLDER_ID` in the environment.
- The user runs this manually before approving the merge.

### Smoke test (on device)

Post-merge, before any re-attempt at Fix 4+5, the user manually:

1. Deletes the ~320 backlog files from Drive.
2. Runs `poetry run whatsapp --headless --output ~/whatsapp_exports_test --auto-select --limit 5 --no-output-media`.
3. Confirms no SSL error cascade and no segfault.

This is the real proof the fix works end-to-end. The integration test is a regression guard; the smoke test is the acceptance gate.

## Files touched

- **Modify:** `whatsapp_chat_autoexport/google_drive/drive_client.py` — add lock, wrap methods, add module docstring note.
- **Create:** `tests/unit/test_drive_client_threading.py` — unit tests for locking contract.
- **Create:** `tests/integration/test_drive_client_concurrency.py` — real-Drive concurrency test (local-only).
- **Create:** `tests/integration/README_drive_integration.md` — setup instructions for the real-Drive test.

No changes to `GoogleDriveManager`, `ParallelPipeline`, `WhatsAppPipeline`, or any caller.

## Out of scope (explicit list)

The following are NOT part of this spec and will NOT be touched:

- Discovery-sweep scope control (F2).
- Segfault reproducer / diagnosis (F3).
- Real-concurrency integration test infrastructure for CI (F4).
- Resource limits for ffmpeg/file descriptors (F5).
- Graceful backoff on error cascades (F6).
- Re-introducing the Fix 4+5 work (transcription cache, retry wrapper, discovery-based listing, 4-wide pipeline workers).

## Acceptance criteria

1. Unit tests pass in CI. Full suite stays green.
2. Real-Drive integration test passes when run manually against live credentials and the fixture folder.
3. Manual smoke test on device (5 chats, `--no-output-media`) completes without SSL errors or segfault.
