---
title: "Pipeline throughput + delete-from-drive — design spec"
type: design
status: approved
date: 2026-04-17
source-report: docs/failure-reports/2026-04-16-full-run-pause.md
fixes: [4, 5]
---

# Pipeline throughput + delete-from-drive — design spec

## Context

The 2026-04-16 full run of 956 chats was paused at 280/956 after ~3 hours. Fixes 1–3 (verify race, community skip, failure visibility) landed on `main` in PR #18. This spec addresses Fixes 4 and 5 from the failure report, which are tightly coupled:

- **Fix 4 — `--delete-from-drive` never fires.** The flag is on, but the delete code path is never reached in practice.
- **Fix 5 — pipeline throughput.** Over ~3 hours of exports (282 zips produced), the pipeline completed ~3 chats. Root cause: pipeline worker pool is size 2, and each worker serializes per-PTT transcription; heavy chats (148 PTTs × 2s each) block a worker for 5+ minutes.

Investigation during brainstorming confirmed that Fix 4 is a downstream symptom of Fix 5: the Drive download call that triggers delete only runs after `wait_for_new_export()` succeeds, and that polling uses a 5-minute `createdTime` filter. When the pipeline queue backs up, files become older than 5 minutes before a worker polls for them, polling times out, download never runs, delete never runs. Fixing throughput fixes the delete behavior for free.

## Goals & success criteria

Two concrete outcomes signed off during brainstorming:

1. **Pipeline keeps pace with exports.** During the next 956-chat run, the Drive file count should stay flat or shrink over time — not monotonically grow.
2. **Resumable across sessions.** A mid-run Ctrl-C can be resumed by re-running the same command. Already-transcribed files are skipped (~5 min saved per heavy chat).

Definition of done for this spec:
- Drive polling logic replaced with discovery-based file listing.
- Pipeline worker pool bumped from 2 → 4.
- Transcription goes from serial → 8-wide parallel with bounded retry.
- Transcriptions land in a durable cache dir outside the temp hierarchy.
- `--delete-from-drive` fires as expected on the next run.

## Non-goals

- No changes to `chat_exporter.py`, `export_pane.py`, `foreground_wait.py`, `whatsapp_driver.py`, or `chat_list.py` (the Fix 1–3 surface).
- No new CLI flags. No TUI changes.
- No Fix 6 (retry-failed TUI button) — separate plan.
- No changes to `legacy/` or `whatsapp_export.py`.
- No adaptive concurrency (simple bounded retry only).
- No 5-min → 24-hour window extension on the old polling — the polling itself is being removed.
- No local manifest / SQLite / JSON pipeline-state file. Drive is the queue. Transcription cache is the only durable intermediate.

## Architecture

Two changes produce the entire outcome:

### Change 1 — Discovery-based Drive work queue

**Current:** `poll_for_new_export(chat_name, ...)` loops for up to 5 minutes looking for a *specific* file created in the last 5 minutes. One worker, one file, one poll loop at a time.

**New:** `list_whatsapp_exports_in_folder(folder)` returns ALL matching files regardless of age, sorted oldest-first by `createdTime`. The pipeline queries this once at start, then re-queries after each new export completes. Workers submit immediately using the pre-fetched file metadata, so no per-chat poll loop exists. When a submitted chat's file hasn't landed on Drive yet (export still in progress), the worker re-discovers the folder every 2s for up to 30s before giving up — a tight feedback loop, not the old 5-min cliff.

**Why this removes Fix 4 as a class:** the 5-min `createdTime` filter is gone. A file dropped on Drive at 10:00 and not processed until 10:47 is still findable.

### Change 2 — Two-level parallelism + retry

**Pipeline level:** `ParallelPipeline.max_workers` goes from 2 → 4. Four chats' download+extract+transcribe+output runs interleaved, bounded by a single `ThreadPoolExecutor`.

**Transcription level:** Inside each chat's transcribe phase, per-file transcription moves from a serial `for media_file in ...` loop to a `ThreadPoolExecutor(max_workers=8)`. Each submission is wrapped in a retry helper that attempts up to 3 times with 1s/2s/4s exponential backoff on retriable errors (network blips, 429 rate-limits). Non-retriable errors (402 quota, 401 auth, malformed audio) fail immediately.

**Peak concurrency:** 4 pipeline workers × 8 transcriptions = up to **32 concurrent API calls**. Well within Whisper's and ElevenLabs' documented rate limits. Hard-coded, not configurable (noted in README).

### Durable transcription cache

New cache location: `~/.whatsapp_exports_cache/<chat-name>/transcriptions/<media_filename>_transcription.txt`.

Transcription writes land here (not in the worker's temp dir). The output builder at phase 5 copies from this cache into the final `~/whatsapp_exports/<chat>/transcriptions/` directory. On resume, the existing "skip if transcription file exists" logic checks the cache path — so previously-transcribed files are reused, not re-transcribed. The cache is safe to delete; deleting it only means next run re-transcribes.

Override via env var `WHATSAPP_TRANSCRIPTION_CACHE_DIR` (for tests only).

## File structure

**Modified:**

- `whatsapp_chat_autoexport/pipeline.py` — adds `run_discovery_driven()` method; `process_single_export(chat_name, file_metadata=None)` accepts a pre-fetched file dict so workers skip polling.
- `whatsapp_chat_autoexport/google_drive/drive_client.py` — removes `poll_for_new_export()`; adds `list_whatsapp_exports_in_folder(folder_id_or_root)` returning all matches sorted `createdTime asc`.
- `whatsapp_chat_autoexport/google_drive/drive_manager.py` — removes `wait_for_new_export()` wrapper. Callers move to `list_whatsapp_exports_in_folder()`.
- `whatsapp_chat_autoexport/export/parallel_pipeline.py` — default `max_workers` 2 → 4; `submit()` accepts optional `file_metadata`; adds `submit_if_not_in_flight(chat_name, file_metadata)`.
- `whatsapp_chat_autoexport/transcription/transcription_manager.py::batch_transcribe` — serial loop → `ThreadPoolExecutor(max_workers=8)`; adds private `_transcribe_with_retry(media_file, attempts=3)`; transcriptions written to cache path instead of alongside the media file.
- `whatsapp_chat_autoexport/output/output_builder.py` — transcription source path comes from the cache resolver, not the temp dir.
- `README.md` — one section documenting the hard-coded concurrency, cache location, and resume semantics.

**New:**

- `whatsapp_chat_autoexport/transcription/transcription_cache.py` — module containing: `get_cache_dir(chat_name) -> Path`, `transcription_exists(media_filename, chat_name) -> bool`, `transcription_path(media_filename, chat_name) -> Path`. Single owner of cache layout.
- `docs/plans/2026-04-17-002-fix-pipeline-throughput-plan.md` — implementation plan that follows this spec.

**Tests new:**

- `tests/unit/test_transcription_cache.py`
- `tests/unit/test_transcription_parallel.py`
- `tests/unit/test_transcription_retry.py`
- `tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py`
- `tests/unit/test_drive_client_list_exports.py`
- `tests/unit/test_pipeline_discovery.py`
- `tests/unit/test_output_builder_cache_source.py`
- `tests/integration/test_pipeline_resume.py`

**Removed:**

- `poll_for_new_export()` method body in `drive_client.py`
- `wait_for_new_export()` method body in `drive_manager.py`
- `created_within_seconds` / `initial_interval` / `max_interval` / `poll_timeout` fields in `PipelineConfig` (no callers after the refactor)

## Data flow

Single-chat lifecycle:

```
Export phase (unchanged)
  WhatsApp UI → Share sheet → Drive upload → zip on Drive
                                                  │
                                                  ▼
Pipeline phase (new)
  Discovery sweep    ─▶ ParallelPipeline.submit_if_not_in_flight(chat, file_metadata)
                                         │
                             (1 of 4 worker threads)
                                         │
                                         ▼
  [worker]  download zip → /tmp/whatsapp_<chat>_xxx/downloads/
            delete from Drive (if --delete-from-drive)           ← fires here
            extract zip → temp/media + temp/transcripts
            transcribe: for each PTT, submit to 8-wide pool
                        wrapped in _transcribe_with_retry (3 attempts, 1/2/4s)
                        writes to ~/.whatsapp_exports_cache/<chat>/transcriptions/
                        skips if already in cache
            build output: copies from cache into ~/whatsapp_exports/<chat>/
            cleanup temp dir
```

Two distinct mechanisms work together:

**A. Per-chat submission (existing hook).** The export phase already calls `pipeline.submit(chat_name)` as each chat finishes exporting. After the refactor, this routes to `ParallelPipeline.submit_if_not_in_flight(chat_name, file_metadata=None)`. The worker that picks up the task performs a small targeted discovery (list Drive, filter by `chat_name`). If the file isn't on Drive yet (upload still in flight), the worker retries the targeted discovery every 2s for up to 30s before erroring.

**B. Full-folder discovery sweeps (new).**

1. **Sweep 1:** at pipeline start. Lists all matching files in Drive. Submits any that aren't already in flight. Handles files that were left on Drive from a previous run.
2. **Final sweep:** after the export phase's `export_chats_with_new_workflow()` (or the TUI's `_run_export`) returns, the caller invokes `pipeline.discovery_sweep_now()` once. This catches any file that landed between mechanism A's submissions and this moment. The pipeline then shuts down after its internal work queue drains.

Mechanism A is the hot path during the run; mechanism B covers resume-from-previous-run and end-of-run catch-all. There are no periodic "every N chats" sweeps — mechanism A is per-chat already.

Peak resource envelope:

- 4 simultaneous temp dirs (worst case ~500 MB each for media-heavy chats) → ~2 GB peak disk.
- 32 concurrent API calls (network-bound, negligible memory).
- Drive API: ~1 list call per sweep + 1 download per chat + 1 delete per chat.

## Error handling

**Transcription:**
- 3 attempts with 1/2/4s exponential backoff.
- Retriable: 429 rate-limit, network errors, timeouts.
- Non-retriable: 402 quota, 401 auth, 400 malformed input, file-not-found.
- After all attempts fail, the chat's pipeline still completes with partial transcriptions; the merged transcript shows empty slots for the failures. Errors aggregated and reported in summary.

**Download:**
- One attempt (existing behavior preserved). On failure, the zip stays on Drive, delete does not fire, `pipeline_result['success'] = False`.

**Discovery:**
- On Drive API error, retry the sweep up to 3 times with 5s backoff. If all 3 fail, log the error and abort this sweep only — the pipeline keeps running on whatever it's already working on; next sweep may succeed.

**Worker crash:**
- Captured by `ParallelPipeline._run_task` try/except (existing behavior). The chat is marked failed, other workers continue.

## Testing

### Unit tests (~25 new)

- **`test_transcription_cache.py`** — cache dir shape, exists/path helpers, env var override.
- **`test_transcription_parallel.py`** — `batch_transcribe` fans out to 8 concurrent calls via mock transcriber; total wall time < 2× single-file time; results preserve per-file accuracy; `skip_existing` honors cache.
- **`test_transcription_retry.py`** — 429 retries 3×; 402 no retry; backoff delays verified via `monkeypatch` on `time.sleep`; 3rd attempt success returns success; all 3 fail returns last error.
- **`test_parallel_pipeline_submit_if_not_in_flight.py`** — double-submit doesn't double-queue; already-completed chat does requeue (fresh work); worker count = 4 default.
- **`test_drive_client_list_exports.py`** — returns all matches; no `createdTime` filter; sort order is `createdTime asc`; empty folder returns empty list.
- **`test_pipeline_discovery.py`** — mock Drive client with pre-seeded file list; sweep 1 submits N tasks; sweep 2 submits only new ones; final sweep idempotent.
- **`test_output_builder_cache_source.py`** — output build reads transcriptions from cache path, not temp path.

### Integration tests (1 new)

- **`test_pipeline_resume.py`** — full pipeline run with mocked Drive + mock transcriber that errors on chat #3. Kill. Re-run on same cache. Assert: chats #1, #2 transcriptions reused; #3 re-attempted; output dirs complete for #1, #2; #3 has partial output.

### Manual verification (user-run)

```
poetry run whatsapp --headless --output ~/whatsapp_exports --auto-select --limit 30 --delete-from-drive
```

1. Monitor Drive folder file count during the run — must stay flat or shrink, not monotonically grow.
2. Kill process partway (Ctrl-C around chat 20). Re-run same command.
3. Confirm cache-hit logs for chats 1–N; fresh transcription only for remaining; Drive empty by end.

### Regression guards

- `test_pipeline_progress.py`, `test_pipeline_only.py`, `test_parallel_pipeline.py` must continue to pass — they assert aggregate counts, not orderings, so interleaved per-file transcribe events remain compatible.
- `test_export_progress.py` and the new Fix 1–3 tests untouched.

## Risks

1. **Rate limit saturation.** 32 concurrent API calls may hit Whisper free-tier limits sooner than 1 serial call did. Mitigation: retry+backoff absorbs transient 429s. If sustained 429s are observed on the real run, a follow-up could introduce adaptive concurrency (explicitly out of scope here).
2. **Disk pressure.** 4 × ~500 MB temp dirs = ~2 GB peak. Acceptable on modern machines, noted in README.
3. **Resume surprises.** Users who expect "retry from scratch" may be confused when cache hits skip transcription. Mitigation: `rm -rf ~/.whatsapp_exports_cache` is documented as the reset.
4. **Cache corruption.** An interrupted transcription could leave a partial/empty `.txt` file in the cache. Mitigation: existing `is_transcribed` check already validates non-empty; zero-byte cache hits are treated as miss and retried.

## Open questions

None — all locked during brainstorming.

## References

- Failure report: `docs/failure-reports/2026-04-16-full-run-pause.md` (Fixes 4 and 5)
- Fix 1–3 implementation: PR #18 merged to `main` on 2026-04-17
