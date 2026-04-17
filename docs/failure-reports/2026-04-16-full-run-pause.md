---
date: 2026-04-16
topic: full-run-failures-2026-04-16
status: resolved-partial
---

# Full Run Failure Report — 2026-04-16

## Executive Summary

Paused full export of 956 chats at **280/956 (29%)** after ~3 hours of runtime. The run has three distinct failure modes, one of which is systemic and responsible for ~90% of lost chats. This report documents what failed, why, and what must change before the next attempt.

| Metric | Value |
|---|---|
| Chats discovered | 956 |
| Exports attempted (WhatsApp → Drive) | ~315 (280 success + 35 failed) |
| Zips successfully landed on Drive | 282 |
| Pipeline (Drive → local output) completed | 3 fresh chats (Innebandy, Peter Cocking, +1) |
| Unique chats that failed export | 38 (visible in activity log) |
| Chat-list markers showing `[✗]` | 6 (badly under-counted) |
| Discovery time | ~36 min |
| Export time so far | ~3 hrs for 280 chats ≈ 38s/chat average |
| Estimated remaining time if resumed as-is | 7–8 more hours |

## What Went Wrong

### Failure Mode 1 — Post-Drive-Upload Verification Race (SEVERE, ~32 chats)

**Signature in activity log:**
```
HH:MM:SS → Google Drive should now be handling
HH:MM:SS OK ✓ [previous chat] exported
HH:MM:SS X WhatsApp verification failed
HH:MM:SS X ✗ [next chat]: Export failed
```

All four timestamps are in the **same second**. The sequence is:
1. Previous chat's Drive upload completes.
2. `ChatExporter` immediately moves to the next chat and calls `driver.verify_whatsapp_is_open()` (line 468 in `chat_exporter.py`).
3. Verification fails because Android hasn't finished returning to WhatsApp's foreground after the Drive share intent — transient state (Drive activity still focused, or com.whatsapp package not yet foreground).
4. The chat is marked failed **without any actual export attempt**.
5. `_attempt_session_recovery()` runs (reconnect + re-verify), succeeds by the time it re-checks, and the run continues to the chat *after* the skipped one.

**This is a race condition between Drive share return and the verify guard.** There is no wait/retry/settle before the first `verify_whatsapp_is_open()` call per chat.

**Affected chats (from activity log, not exhaustive):**
Alastair McClung, Alex Goldobin, Amanda Lenzi, Andy's Sept Sailing 2017, AHF training, Anna, Chris Gulland, Christopher Long, Elaine Mattheson, Fri, Gaëlle, Gary Hart, Giorgio Campini, Joel Olofsson, Julia, Lily, New Slovenia group, Raheema, Security System disc, Segling Västervik ⛵️, Stuart Forsyth, Suraj Krishnan, T Deck, Hampus&Simone, Stuart McNeill, +27 78 875 7185, +39 335 845 5476, +44 7411 301645, +44 7470 465906, +44 7547 807691, +44 7570 744795, +44 7733 263728, +44 7760 471813, +44 7766 755137, +48 574 243 293, +49 160 96696586, +64 210 225 5144.

### Failure Mode 2 — Community Chats (EXPECTED, 2 chats)

**Signature:** Chat list shows `[✗]` for:
- `Helicopter PILOTS & operators  Worldwide community  🚁`
- `Dance Vida Community`

WhatsApp does not allow export of community chats. The existing code acknowledges this (chat_exporter.py:551: `if "community" in error_msg.lower(): Skipped …`) but is **marking them as failed instead of skipped**. The marker should be `[⊘]` (skipped), not `[✗]` (failed).

### Failure Mode 3 — Chat-List UI Doesn't Reflect Failures (SEVERE, display bug)

The activity log recorded **38 unique export failures** but the chat-list panel (`ChatListWidget`) only shows **6 with `[✗]` markers**. The left panel is the authoritative list the user references, so 32 failures were invisible.

Looking at the code: failures go through `results[chat_name] = False` and `state_manager.fail_chat(...)`, but the `chat_list.set_status(chat_name, FAILED)` bridge isn't being called for Mode 1 failures (verification-failed path). The user cannot know which chats to re-run without scraping scrollback.

## What Actually Got Done vs. Reported

**Reported "280/956 chats (29%)":** this counts WhatsApp-side export attempts (successes + failures both advance the counter).

**Actual state of each chat:**

| Chat group | Count | State |
|---|---|---|
| Exported + pipeline complete | 3 (smoke test) | transcript.txt + media/ + transcriptions/ in `~/whatsapp_exports/` |
| Exported zip on Drive, pipeline backlog | ~279 | zip in `My Drive/WhatsApp Chat with <name>.zip` (282 zips created today) |
| Mode 1 failures (verification race) | ~32 | no zip, no output, **would need re-export** |
| Mode 2 failures (community chats) | 2 | cannot be exported, **permanent** |
| Not yet attempted | ~640 | still in the queue |

The pipeline (download from Drive → extract → transcribe → build output) was running but only produced ~1 output folder for every 93 Drive uploads. It is massively behind the export loop. `--delete-from-drive` never fired because the pipeline never caught up to the downloads.

## Current Safe State for Resume

- **Google Drive:** 282 zips from today (1.21 GB) preserved. Nothing has been deleted. The run's `--delete-from-drive` flag never activated.
- **Drive for Desktop mirror:** 283 zips visible as placeholders under `~/Library/CloudStorage/GoogleDrive-ajanderson1@gmail.com/My Drive/`. Files are stream-on-demand.
- **Local exports folder:** 7 chat folders (4 pre-existing, 3 fresh from today's smoke test). No in-flight processing left.
- **Journal backup:** `~/Journal/People/Correspondence/_backups/Whatsapp_2026-04-16_1115/` (1.6 GB, 447 chat folders) — prior state preserved.
- **Appium & TUI:** Cleanly shut down. Phone can be disconnected now (and has been).
- **No corrupt state:** no interrupted zips, no half-written output folders.

## Required Fixes (Ranked by Impact)

### Fix 1 — Add Settle Period Before `verify_whatsapp_is_open()` (HIGH)

**File:** `whatsapp_chat_autoexport/export/chat_exporter.py`, line 468.

Before calling `self.driver.verify_whatsapp_is_open()` at the top of each chat iteration, wait for WhatsApp to become foreground again (with timeout):

```python
# Current:
if not self.driver.verify_whatsapp_is_open():

# Proposed:
if not self.driver.wait_for_whatsapp_foreground(timeout=8.0):
    # Existing recovery path
```

Implementation: poll `driver.current_package == "com.whatsapp"` every 250ms up to 8s before running the full verification. This directly targets the race where Drive's share activity hasn't yet handed focus back.

### Fix 2 — Mark Community Chats as Skipped, Not Failed (MEDIUM)

**File:** `whatsapp_chat_autoexport/export/chat_exporter.py`, around the community-chat detection.

Community-chat detection exists but only when an exception is raised (line 551). Add up-front detection when opening the chat (check for the community badge on the chat toolbar) and mark with `ChatDisplayStatus.SKIPPED` + reason "Community chat — export unsupported". These should not block the batch, not count toward the consecutive-failure limit, and must not retry.

### Fix 3 — Wire Per-Chat Failures into ChatListWidget (MEDIUM)

**Files:** `chat_exporter.py` (emitters) + `tui/textual_widgets/chat_list.py` (consumer) + `tui/textual_panes/export_pane.py` (bridge).

Every failure path in `ChatExporter.export_all_chats()` must trigger `ChatListWidget.set_chat_status(chat_name, FAILED)`. The activity log records it; the chat list does not. After this fix, users can see the full failure picture in the left panel and select failed-only for retry.

### Fix 4 — Fix `--delete-from-drive` Behaviour (MEDIUM)

The flag was on but never fired because pipeline processing never caught up. Either:
- **(a)** Only delete after pipeline confirms successful local output (current design, never reached); or
- **(b)** Decouple: let Drive deletion happen per-chat after local `transcript.txt` exists, regardless of pipeline backlog state.

Investigation needed in `pipeline.py` around why Phase 1 (Drive download) is the bottleneck, and whether pipeline work must be serialized or can run fully concurrent with exports.

### Fix 5 — Increase Pipeline Throughput (MEDIUM)

`ThreadPoolExecutor(max_workers=2)` is under-provisioned for a 956-chat run. Over ~3 hours of exports producing 282 zips, the pipeline completed ~1 chat. Possible reasons:
- Transcription serialises per-chat (148 PTTs in Innebandy took 15 min just transcribing).
- Pipeline blocks on Drive polling/download for each chat before starting the next.

Change probably needs two levels of parallelism: pipeline-level (multiple chats in flight) **and** transcription-level (multiple PTTs per chat in parallel using ElevenLabs batched calls).

### Fix 6 — Failure-Retry Mode in TUI (LOW, quality-of-life)

After a run ends, offer a "Retry failed" button that re-selects only `[✗]` chats and restarts. Currently re-running failed chats requires either manual selection or a headless re-invocation.

## Recommended Resume Strategy (no code changes)

If user wants to resume **without** fixing anything first:

```bash
cd ~/GitHub/projects/whatsapp_chat_autoexport/

# Step 1: Process the 282 zips already on Drive
# (This avoids re-running WhatsApp export for them.)
# Requires the Drive-for-Desktop local mirror to be fully populated.
# Force-sync first by opening each file once, or use Drive API downloader.

poetry run whatsapp --pipeline-only \
  "/Users/ajanderson/Library/CloudStorage/GoogleDrive-ajanderson1@gmail.com/My Drive" \
  ~/whatsapp_exports

# Step 2: Resume WhatsApp export for the remaining ~640 chats
# --resume scans the Drive folder and skips chats whose zips already exist there.
poetry run whatsapp --output ~/whatsapp_exports \
  --transcription-provider elevenlabs \
  --resume "/Users/ajanderson/Library/CloudStorage/GoogleDrive-ajanderson1@gmail.com/My Drive"
```

Caveats without fixes:
- Still expect ~10% of remaining chats to hit Mode 1 (verification race) and fail.
- Community chats (~2 more may be in the remaining 640) will still fail loudly.
- Chat list won't reflect the full failure picture — keep scraping activity log.

## Recommended Resume Strategy (with Fix 1)

Fix 1 alone should take Mode 1 from ~10% failure rate to near-zero. Fixes 2 and 3 are about observability and can wait. Fixes 4–5 are about speed but not correctness.

1. Implement Fix 1 (small, low-risk change in `chat_exporter.py`).
2. Run the two-step resume strategy above.
3. Review the activity log after completion for any new failure signatures.

## Artefacts

- Snapshot trail: `/tmp/whatsapp_full_run_2026-04-16/tui_*.txt` (10 snapshots, every 10 min)
- Failed-chat list (activity-log derived): `/tmp/all_failures.txt` (38 names)
- Failed-chat list (left-panel derived): `/tmp/failed_from_list.txt` (6 names)
- Final TUI state: `/tmp/whatsapp_full_run_2026-04-16/final_state_before_pause.txt`
- Run meta: `/tmp/whatsapp_full_run_2026-04-16/run_meta.txt`
- Journal backup (pre-run): `~/Journal/People/Correspondence/_backups/Whatsapp_2026-04-16_1115/`

## Outstanding Questions

1. **[Needs investigation]** Why did the pipeline only complete 3 chats in 3 hours while exports reached 282? Is it the transcription stage, Drive download, or serialisation of phases?
2. **[User decision]** Do we prioritise Fix 1 (correctness) before resuming, or accept ~10% re-runs and power through?
3. **[Needs investigation]** What is the actual WhatsApp/Android state 1–3 seconds after the Drive share activity returns? A targeted experiment (pause exports for 2s, log `current_package` and `current_activity`) would confirm whether a simple settle-wait fully solves Mode 1.
4. **[Needs investigation]** The chat-list widget showed 6 failures vs. 38 in the log. Is this a missed event-wire, or is the widget filtering based on a state the code never sets?

## Next Steps

- **Resolve-before-resume:** Fix 1 (settle period) recommended. Other fixes can wait.
- **→ Decide:** implement Fix 1 now, resume without fixes, or both.

## Resolution

Implemented in plan `docs/plans/2026-04-17-001-fix-full-run-failures-plan.md`.

- **Fix 1 (verify-race):** `WhatsAppDriver.wait_for_whatsapp_foreground()` now
  runs before every `verify_whatsapp_is_open()` call at pre-export checkpoints
  in both the batch loop (`chat_exporter.py`) and the TUI path
  (`export_pane.py:_export_single_chat`). Timeout falls through to the
  existing recovery path, so genuine non-WhatsApp states are still caught.
- **Fix 2 (community skip):** `ChatExporter.export_chat_to_google_drive()`
  now probes `driver.is_community_chat()` up front and returns
  `ExportOutcome(kind=SKIPPED_COMMUNITY)`. The TUI routes that through
  `_skip_chat_export`, which does not increment the consecutive-failure
  counter.
- **Fix 3 (visibility):** Every failure and skip in the TUI carries a reason
  string through to `ChatListWidget.update_chat_status(..., reason=...)`, and
  a reconcile pass at the end of the run re-asserts the chat-list panel's
  per-chat state from `_export_results`. The left panel is now the
  authoritative failure record.

Fixes 4, 5, and 6 from this report remain open.
