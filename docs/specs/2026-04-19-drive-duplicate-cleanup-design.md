# Drive Duplicate Cleanup — Design

**Status:** Draft
**Date:** 2026-04-19
**Author:** AJ Anderson (with Claude)
**Related:** `docs/specs/2026-04-19-drive-client-thread-safety-design.md`

## Problem

When `whatsapp` runs without `--delete-from-drive`, every re-export of a chat
leaves a file in Google Drive root named `WhatsApp Chat with <ChatName>`. On
the next run, the phone uploads to the same root with the same name, and
WhatsApp/Drive rename the new upload to `WhatsApp Chat with <ChatName> (1)`,
`(2)`, and so on. The polling downloader picks up the newest variant but does
nothing about the stale originals.

Result after a few runs: Drive root fills with duplicate sibling files
(`WhatsApp Chat with Daniel Cocking`, `... (1)`, `... (2)` …). This clutters
the user's Drive, confuses the resume flow (`check_chat_exists` matches only
the exact base name, not `(N)` variants), and eventually stresses the Drive
API with large root listings.

## Goal

After the pipeline successfully downloads a chat export, delete every
Drive-root file that belongs to that chat's name-group — the just-downloaded
file plus any base-name and `(N)` siblings. This should be the default
behaviour, with an opt-out flag for users who want the old semantics.

## Non-Goals

- **Pipeline-only mode (`--pipeline-only`) is not touched.** That path
  processes already-downloaded local files with no Drive side-effects.
- **No retroactive cleanup** of the user's existing historical duplicates.
  Cleanup applies only to chats this run downloads.
- **Not subfolder-aware.** WhatsApp uploads to Drive root only; this feature
  acts on Drive root only.
- **Not a replacement for `--delete-from-drive`.** Orthogonal: that flag
  deletes only the file just downloaded; cleanup deletes the whole
  name-group (which is a superset).
- **No TUI surface in this spec.** CLI and `PipelineConfig` only.
- **No retry loop on Drive failures.** Next run will re-list and retry.

## Architecture

The feature has one new primitive and one new call site.

**New primitive:** `GoogleDriveClient.delete_sibling_exports(chat_name: str, folder_id: Optional[str] = None) -> int`
in `whatsapp_chat_autoexport/google_drive/drive_client.py`. Returns the number
of files successfully deleted. Never raises — all Drive errors are caught,
logged, and reflected in the return value. Holds `self._service_lock` for
both the listing query and the per-file deletes (same pattern as other
methods on this class since the thread-safety fix in
`docs/specs/2026-04-19-drive-client-thread-safety-design.md`).

**New call site:** `WhatsAppPipeline._process_single_chat` in
`whatsapp_chat_autoexport/pipeline.py`, immediately after the successful
`batch_download_exports(...)` call (~line 188) and before the extract phase.

**Thin passthrough:** `GoogleDriveManager.delete_sibling_exports` in
`whatsapp_chat_autoexport/google_drive/drive_manager.py` — one-line delegate
to `self.client.delete_sibling_exports(...)`, matching the existing
manager→client pattern.

## Name-Group Matching

The primitive lists Drive root with a `contains` pre-filter, then applies a
strict client-side regex to decide what to delete.

**Drive query:**

```
name contains 'WhatsApp Chat with <escaped_chat_name>' and 'root' in parents
```

Single quotes inside `chat_name` are escaped with `\'` (same pattern used in
`poll_for_new_export` at `drive_client.py:405`).

**Client-side regex** (applied to each returned file's `name`):

```
^WhatsApp Chat with <re.escape(chat_name)>(?: \(\d+\))?(?:\.zip)?$
```

**Matches:**

- `WhatsApp Chat with Daniel Cocking`
- `WhatsApp Chat with Daniel Cocking.zip`
- `WhatsApp Chat with Daniel Cocking (1)`
- `WhatsApp Chat with Daniel Cocking (1).zip`
- `WhatsApp Chat with Daniel Cocking (42).zip`

**Does not match:**

- `WhatsApp Chat with Daniel Cocking Jr.zip` — different chat
- `WhatsApp Chat with Daniel Cocking family` — different chat
- `WhatsApp Chat with Daniel Cocking (abc).zip` — non-numeric suffix
- `WhatsApp Chat with Daniel Cocking (1) backup.zip` — custom rename
- Anything with a non-root parent (filtered by the Drive query)

**Deletion order:** deletes run sequentially under `_service_lock`. On any
per-file `HttpError`, log a warning with the file name and error code and
continue to the next file. Return the count of successful deletes.

## Configuration

**New field on `PipelineConfig`** (in `whatsapp_chat_autoexport/pipeline.py`):

```python
cleanup_drive_duplicates: bool = True
```

Mirrored into `Settings` in `whatsapp_chat_autoexport/config/settings.py` so
the existing config-loading flow carries it through.

**New CLI flag** on the unified `whatsapp` command
(`whatsapp_chat_autoexport/cli_entry.py`):

```
--keep-drive-duplicates   Skip deleting Drive root duplicates after download
                          (default: duplicates are removed)
```

No short flag. Wired through to `run_headless` (`headless.py`) and the
pipeline-only path ignores it (non-goal). `--delete-from-drive` remains
independent; with both defaults, every successful per-chat run removes both
the just-downloaded file and any `(N)` siblings.

## Call-Site Wiring

In `WhatsAppPipeline._process_single_chat` (`pipeline.py`, after the existing
`downloaded = self.drive_manager.batch_download_exports(...)` block and the
`if not downloaded: raise` guard):

```python
if self.config.cleanup_drive_duplicates:
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
```

The call does not fire a progress callback — the next `_fire_progress`
already transitions to the extract phase.

## Error Handling

- `delete_sibling_exports` never raises.
- **Listing failure:** `HttpError` or generic exception on `files().list()`
  is caught; logs
  `warning("Drive cleanup: failed to list siblings for '{chat}' — skipping "
  "(Drive error: {e})")` and returns `0`.
- **Per-file delete failure:** caught; logged at warning level with the file
  name and error code; iteration continues; failures are not counted in the
  return value.
- **Stale 404** (file deleted by a concurrent session between list and
  delete): caught as `HttpError` with status 404; logged at debug; counted as
  success (the file is gone, which is the desired state).
- **Quota / 5xx:** same path as any other `HttpError` — warning logged,
  partial count returned, pipeline continues.
- **Cleanup failure never fails the chat.** The file is already on local
  disk at this point; Drive-side cleanup is best-effort.

## Interaction With Existing Flags

- **`--delete-from-drive`:** deletes only the just-downloaded file inside
  `batch_download_exports`. When cleanup runs afterwards, the just-downloaded
  file is already gone and `delete_sibling_exports` will not see it in its
  listing — it only prunes the `(N)` siblings. No double-delete. No conflict.
- **`--resume <drive-mount-path>`:** untouched. Resume reads the user's
  mounted Drive folder locally; this feature acts on the Drive API. Running
  cleanup does not change resume's match set because resume is only checked
  *before* a chat is exported, not after.

## Observability

Log messages (all via the existing `Logger`):

- `info` — `"Drive cleanup: removed N duplicate(s) for '<chat>' from Drive root"` (when N > 0)
- `debug` — `"Drive cleanup: nothing to prune for '<chat>'"` (when N = 0)
- `warning` — `"Drive cleanup: failed to list siblings for '<chat>' — skipping (Drive error: <e>)"` (listing fail)
- `warning` — `"Drive cleanup: failed to delete '<file>' — <error-code>"` (per-file fail)
- `debug` — `"Drive cleanup: '<file>' already gone (404)"` (stale match)

## Testing

### Unit tests (new file `tests/unit/test_delete_sibling_exports.py`)

Mock the Drive service; no real API calls.

1. **Base name matched** — service returns `WhatsApp Chat with X` and
   `WhatsApp Chat with X.zip`; both deleted; return value = 2.
2. **Numeric siblings matched** — service returns `... (1)`, `... (2).zip`,
   `... (10).zip`; all deleted; return value = 3.
3. **Substring collisions rejected** — service returns `... Jr.zip`,
   `... family`; neither deleted; return value = 0.
4. **Non-numeric suffix rejected** — service returns `... (abc).zip`,
   `... (1) backup.zip`; neither deleted.
5. **Special-char chat name** — chat name `O'Brien.`; regex escapes `.`;
   Drive query escapes `'`; matches `WhatsApp Chat with O'Brien.` and
   `WhatsApp Chat with O'Brien. (1).zip`.
6. **Root-only scope** — verify the query string passed to `files().list()`
   contains `'root' in parents`.
7. **Lock held** — use `_LockObservingService` from the thread-safety tests;
   assert the lock is acquired for the list call and each delete.
8. **Listing failure returns 0** — `files().list().execute()` raises
   `HttpError`; no deletes issued; return 0; warning logged.
9. **Per-file delete failure continues** — first `delete()` raises
   `HttpError(500)`, second succeeds; return 1; warning logged.
10. **Empty sibling set** — list returns `[]`; return 0; debug log only.
11. **Stale 404 counted as success** — `delete()` raises
    `HttpError(status=404)`; counted in return value.

### Call-site tests (extend existing pipeline tests)

12. **Pipeline calls cleanup when flag on** — mock
    `drive_manager.delete_sibling_exports`; run one chat through
    `_process_single_chat`; assert called once with the chat name.
13. **Pipeline skips cleanup when flag off** — same fixture with
    `cleanup_drive_duplicates=False`; assert not called.
14. **Cleanup failure does not fail the chat** — mock cleanup to raise
    (defensive; it should not raise, but prove isolation); chat completes
    successfully.

### Integration / manual

No gated real-Drive integration test in this spec. One-shot manual
smoke-test: export the same chat twice in succession without
`--delete-from-drive`; confirm Drive root remains clean (only the most
recent file present during run, nothing persisted after).

## Acceptance Criteria

- After each successful per-chat download in `WhatsAppPipeline`, the Drive
  root contains no `WhatsApp Chat with <chat> (N)` or
  `WhatsApp Chat with <chat>` siblings for the chat just processed, unless
  `--keep-drive-duplicates` was set.
- `--keep-drive-duplicates` on the unified `whatsapp` command skips cleanup.
- Cleanup failures never fail a chat. The worst case is a warning logged and
  one or more siblings left behind for the next run to retry.
- All 14 tests above pass. Full suite stays green.
- `CLAUDE.md` documents the new flag and default behaviour.

## Out of Scope (future work)

- Pipeline-only path support.
- Retroactive historical cleanup (a `whatsapp drive prune` subcommand).
- TUI surface.
- CI-gated real-Drive integration test (deferred alongside F4 from the
  thread-safety spec).
