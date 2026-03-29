---
date: 2026-03-28
topic: export-speed-optimization
---

# Export Speed Optimization

## Problem Frame

A full batch export of ~417 WhatsApp chats takes hours. The two main time sinks are:

1. **Hardcoded UI sleeps** (~6.5s per chat, ~45 min total) — every export step uses unconditional `time.sleep()` calls even when the UI is already ready.
2. **Sequential Drive polling** (~8-300s per chat) — after triggering each export, the system polls Google Drive every 8s waiting for the zip to appear, blocking all other work.

These are sequential: the next chat doesn't start until the current chat's export is fully downloaded and processed. Even cutting a few seconds per chat compounds across 417 chats.

## Requirements

**Smart UI Waits**

- R1. Replace all hardcoded `time.sleep()` calls in export step files (`whatsapp/export/steps/*.py`) with condition-based waits (WebDriverWait or equivalent) that complete as soon as the UI condition is met.
- R2. Each smart wait must have a reasonable timeout ceiling so a stuck UI doesn't hang forever (use the existing timeout profile values as ceilings).
- R3. The existing timeout profile system (`FAST`/`NORMAL`/`SLOW`/`DEBUG` in `config/timeouts.py`) must be consistently wired through all steps — no step should ignore the active profile.

**Adaptive Drive Polling**

- R4. Replace the fixed 8-second polling interval with adaptive polling: start at 2s, back off progressively (e.g. 2s, 2s, 4s, 8s, 8s...) up to a configurable ceiling.
- R5. Auto-detect export mode (with/without media) and set an appropriate default timeout — shorter for text-only exports, longer for media exports.

**Parallel Pipeline (Overlap)**

- R6. After triggering a chat's export and starting Drive polling, begin navigating to and triggering the next chat's export concurrently. Drive polling, download, extraction, and processing for chat N must happen in a background thread while UI automation proceeds for chat N+1.
- R7. The background pipeline thread must be fully isolated from the Appium/UI thread — no shared mutable state beyond a thread-safe results queue.
- R8. Errors in the background pipeline (download failure, extraction error, processing error) must not crash the UI automation thread. Errors are captured and reported in the final summary.
- R9. A configurable concurrency limit controls how many background pipeline tasks can be in-flight simultaneously (default: 2, to avoid overwhelming Drive API or local disk I/O).

**Observability**

- R10. The export summary must report per-chat timing breakdown (UI time, poll time, download time, process time) so future optimizations can be data-driven.

## Success Criteria

- Full batch export (417 chats, without media) completes at least 30% faster than the current sequential flow.
- No increase in export failure rate — the optimization must not introduce flakiness.
- Per-chat timing data is available in the export summary for validation.

## Scope Boundaries

- Not changing the transfer mechanism (Drive stays as the intermediary).
- Not changing the Appium/Selenium driver layer or element-finding strategy.
- Not adding new CLI flags for end users beyond what's needed for concurrency tuning.
- Voice transcription and output formatting are untouched.

## Key Decisions

- **Smart waits over reduced sleeps**: Rather than just lowering sleep values, replace them with condition-based waits. Higher upside, and the WebDriverWait pattern is already used for element finding.
- **Thread-based parallelism over async**: The Appium driver is synchronous and not async-safe. A background thread for the pipeline work (polling + download + processing) is the natural fit. The UI thread stays single-threaded.
- **Adaptive polling over fixed interval**: Small exports appear on Drive quickly (~5-15s). Starting with short intervals avoids unnecessary waiting while backing off prevents API abuse on large uploads.

## Dependencies / Assumptions

- Google Drive API rate limits are not a concern at 2s polling intervals for a single user.
- The Appium driver is not thread-safe — all UI automation must stay on the main thread.
- WhatsApp does not throttle or queue exports when they're triggered in rapid succession.

## Outstanding Questions

### Deferred to Planning

- [Affects R6][Technical] What's the cleanest threading model — `concurrent.futures.ThreadPoolExecutor` or raw `threading.Thread` with a queue?
- [Affects R1][Needs research] Which specific UI conditions should each step wait for? (e.g. "More" menu visible, export dialog loaded, Drive picker ready). Requires inspecting each step's post-action state.
- [Affects R5][Needs research] What's the typical Drive upload latency for text-only vs media exports? May need empirical measurement during implementation.
- [Affects R9][Technical] Should the concurrency limit be a CLI flag or just a config constant? Leaning toward config constant since most users won't need to tune it.

## Next Steps

-> `/ce:plan` for structured implementation planning
