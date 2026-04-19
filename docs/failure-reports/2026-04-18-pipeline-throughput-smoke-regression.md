---
date: 2026-04-18
topic: pipeline-throughput-smoke-test-regression
status: merge-reverted
source-plan: docs/plans/2026-04-17-002-fix-pipeline-throughput-plan.md
source-spec: docs/specs/2026-04-17-pipeline-throughput-design.md
---

# Pipeline Throughput Smoke-Test Regression Report — 2026-04-18

## Executive Summary

Merged Fixes 4+5 into local `main` (commit `44d2fb2`) after all 15 plan tasks passed (831 unit tests + 1 integration test). A 5-chat smoke test on the real phone crashed with a segmentation fault after ~30 seconds, following a cascade of Google Drive SSL errors. Merge was reverted locally before pushing. Remote `origin/main` remains at `340b864` (Fix 1–3).

Three distinct new bugs surfaced that the plan did not anticipate:

1. **Google Drive client is not thread-safe.**
2. **Discovery sweep has no scope control** — picks up the entire Drive-root backlog regardless of `--limit`.
3. **Segmentation fault** after the SSL error cascade.

The design direction remains sound — the transcription cache, retry wrapper, and discovery-based listing are all genuinely useful. But the concurrency design needs a rework before it can ship.

## What Actually Happened

### The test

```bash
poetry run whatsapp --headless \
  --output ~/whatsapp_exports_test \
  --auto-select \
  --limit 5 \
  --no-output-media \
  --delete-from-drive
```

Fresh `~/whatsapp_exports_test/`; empty `~/.whatsapp_exports_cache/`. Phone USB-connected, unlocked.

### Observed sequence

1. Appium starts cleanly. Headless mode initializes.
2. `Discovery sweep at pipeline start...` fires (correct — per plan).
3. Sweep output: `discovery_sweep_now: discovered 320 file(s); submitted 284 new task(s)`.
4. `Processing chat 1/5: 'Helicopter PILOTS & operators  Worldwide community  🚁'` — export phase begins.
5. In parallel, pipeline workers start downloading the 284 discovered files at concurrency=4.
6. Download errors cascade: `SSL: WRONG_VERSION_NUMBER`, `SSL: UNEXPECTED_RECORD`, `read operation timed out`, `IncompleteRead(89 bytes read)`.
7. 11 pipeline tasks attempted. 8 failed with Drive SSL/timeout errors. **0 completed successfully.**
8. Process dies: `[1]    46611 segmentation fault  poetry run whatsapp --headless …`.

Total wall time before crash: ~30 seconds from Enter.

## The Three Bugs

### Bug 1 — Google Drive client is not thread-safe (P0)

**Evidence:**
```
Error downloading file: [SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:2648)
Error downloading file: [SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:2648)
Error downloading file: The read operation timed out
Error downloading file: IncompleteRead(89 bytes read)
Error downloading file: [SSL: UNEXPECTED_RECORD] unexpected record (_ssl.c:2648)
```

**Root cause:** `google-api-python-client`'s `service` object and the underlying `httplib2.Http` connection are not thread-safe. When multiple `ParallelPipeline` workers call `self.drive_manager.client.download_file(...)` concurrently, they share one `Http` instance and corrupt each other's SSL streams.

The plan's design assumed "4 concurrent downloads … comfortable for the 1 Mbps or so each download takes" without flagging that the underlying library requires one `service` per thread. Neither the spec's Risks section nor the plan's Data Flow section mentioned thread-safety.

**What needs to change:** Each `ParallelPipeline` worker needs its own `GoogleDriveManager` instance (or its own `httplib2.Http` via the `http=` kwarg on `build(...)`), constructed inside the worker thread. The current design's `pipeline.drive_manager` singleton is the root of the problem.

### Bug 2 — Discovery sweep has no scope control (P1)

**Evidence:** User asked for `--limit 5` on the command line. First sweep discovered 320 files and submitted 284 tasks.

**Root cause:** `WhatsAppPipeline.discovery_sweep_now()` calls `list_whatsapp_exports_in_folder(folder_id="root")` unconditionally — no filtering by the chat list the export phase is about to produce, no respect for `--limit`, no prior-run detection.

The plan's design-time intent was: "Sweep 1 at pipeline start picks up files left on Drive from a previous run." That's correct — but when the previous run left 320 files, the behavior becomes "process an unrelated backlog whenever the user starts any new run." The user's `--limit 5` is violated silently.

**Options for the fix:**
- **(a)** Discovery sweep is skipped unless the user explicitly opts in via a new flag (`--discover-backlog`).
- **(b)** Discovery sweep filters against `PipelineConfig.chat_names` when supplied; runs only on `--resume` mode otherwise.
- **(c)** Discovery sweep respects `--limit` and stops after that many files.

Option (a) is the most surprising-behavior-free. Option (b) preserves the "pick up what the export loop is producing" intent. Both deserve discussion.

### Bug 3 — Segmentation fault (P0)

**Evidence:** `[1]    46611 segmentation fault` after the SSL error cascade. The process was still "processing export: 'Jason Cormack'" when it died.

**Root cause:** unknown without more instrumentation. Three plausible hypotheses:

1. **ffmpeg concurrency.** The Opus-to-M4A conversion spawns `ffmpeg` subprocesses. With 4 pipeline workers each holding up to 8 transcription slots = up to 32 concurrent `ffmpeg` processes. ffmpeg does not play well with certain macOS conditions (signal handling, open-file limits).
2. **SSL corruption cascade.** Once the `httplib2` connection got into a bad state (Bug 1), subsequent calls may have dereferenced corrupt state in OpenSSL's native library and crashed.
3. **Thread local issues in `TranscriberFactory`.** The transcriber is a shared object across worker threads; if it uses thread-local storage that gets corrupted, native calls could segfault.

**What needs to change:** Need a reproducer with instrumentation (`faulthandler.enable()`, Python's `-X dev`) to narrow down. Without a reproducer, we're guessing.

## Plan Retrospective

The plan (`docs/plans/2026-04-17-002-fix-pipeline-throughput-plan.md`) and spec (`docs/specs/2026-04-17-pipeline-throughput-design.md`) both missed these issues because:

1. **No concurrency test at the actual boundary.** All 35 unit tests use `MagicMock()` for the Drive client. The real `google-api-python-client` was never exercised under concurrent pressure in the test suite. Thread-safety is invisible to mocks.
2. **The integration test (`test_pipeline_resume.py`) uses a fake Drive manager.** Good for testing cache durability; useless for testing Drive concurrency.
3. **Discovery sweep scope was under-specified.** The spec said "at pipeline start, list all matching files in Drive. That list is the queue." The edge case of "what if the list is 320 files from an unrelated previous failure" was not raised during brainstorming.
4. **No segfault-safety thinking.** Mixing native libraries (ffmpeg via subprocess, OpenSSL via httplib2, pyobjc indirectly via the OpenAI SDK) under thread-level concurrency is a known minefield. No test or design review flagged the risk.

## Current State

- **Local `main`:** reset to `5d6d4bf` (the plan doc, post-spec). Three local-only commits retained on `main`:
  - `5d6d4bf` docs(plan): implementation plan for pipeline throughput
  - `0a16ca2` docs(spec): clarify discovery sweep vs per-chat submission
  - `8a656d7` docs(spec): pipeline throughput design
- **Remote `origin/main`:** `340b864` — Fix 1–3 merge. Unchanged.
- **Reverted merge commit `44d2fb2`:** gone from local main. The 15 fix-branch commits are still recoverable via `git reflog` if needed.
- **Reverted branch `fix/pipeline-throughput`:** already deleted. Commits are reachable from the reflog only.
- **Worktree `.worktrees/fix-pipeline-throughput`:** removed.
- **`~/.whatsapp_exports_cache/`:** may have partial content from the aborted smoke test — safe to delete before the next attempt.
- **Google Drive:** 320 `WhatsApp Chat with …` files still present (the backlog from the 2026-04-16 failure). Several were downloaded and deleted during the 30-second smoke window. Count unknown — would need to query Drive to confirm current state.

## Required Before Next Attempt

The plan needs to be revised before any re-implementation:

### Must-fix before merge

- **F1. Thread-safe Drive access.** Either one `GoogleDriveManager` per worker thread, or synchronise all Drive calls with a lock (simpler, trades throughput for safety). The lock option should be considered first — Drive API calls are network-bound, and serializing them still allows transcription/extract/output-build to run in parallel.
- **F2. Discovery-sweep scope control.** Discussion needed on whether the sweep should filter, require opt-in, or respect limit.
- **F3. Segfault reproducer + root cause.** Before adding retry logic or concurrency tuning, we need to know what crashed. `faulthandler`, `python -X dev`, `ulimit -n`, subprocess accounting.

### Should-fix before merge

- **F4. A real-concurrency integration test.** Spins up an actual `googleapiclient.discovery.build()` against a mock HTTP server (or `httplib2.http.Mock`) and exercises 4 concurrent downloads. Proves the thread-safety fix before a real phone run.
- **F5. Resource limits.** Document/enforce maximum open files, subprocess count, and temp-dir disk usage so that N-concurrent-workers can't exhaust the system.

### Nice to have

- **F6. Graceful shutdown on error cascade.** If 8/11 pipeline tasks fail with the same error signature in a short window, the pipeline should back off (exponential) and surface a clear "I think Drive is sick" error rather than pushing through.

## Next Steps

1. **Preserve artifacts.** The spec at `docs/specs/2026-04-17-pipeline-throughput-design.md` and the plan at `docs/plans/2026-04-17-002-fix-pipeline-throughput-plan.md` stay on main — the design intent is still good.
2. **Commit this failure report.** Same pattern as 2026-04-16 report.
3. **Brainstorm the revision.** F1–F3 are specific enough to go straight to planning; F4–F6 need a short conversation.
4. **Do not push anything to `origin/main`.** The remote is clean; keep it that way until we ship something that works.
