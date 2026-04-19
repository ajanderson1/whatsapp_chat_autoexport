# WhatsApp Sync Service — Design Spec

**Date:** 2026-04-19
**Status:** approved
**Origin:** Brainstorm session refining the 2026-03-26 unified sync tool plan
**Supersedes:** `docs/plans/2026-03-26-001-feat-whatsapp-unified-sync-tool-plan.md` (in Journal)

## Problem

Updating WhatsApp transcripts in the Obsidian vault requires a full batch re-export via Appium Android automation. This takes hours, requires a physical Android device, and overwrites every transcript. The WhatsApp MCP bridge (lharries/whatsapp-mcp) is a wrapper around whatsmeow with an inactive upstream (July 2025) and an unauthenticated REST API.

## Solution

A continuously-running service on Raspberry Pi 5 that maintains a complete, append-only WhatsApp chat archive in the Obsidian journal. Uses whatsmeow directly (not the lharries MCP wrapper).

## Architecture

Three components, two repos, one vault:

```
+------------------------- Pi 5 ---------------------------+
|                                                           |
|  +----------------+    SQLite     +--------------------+  |
|  |  Go Bridge     |-------------->|  Python Daemon     |  |
|  |  (whatsmeow)   |  + voice/    |  (sync loop)       |  |
|  |                 |  audio files |                    |  |
|  +--------+--------+             +----------+---------+  |
|           |                                 |             |
|           |                                 +--git commit |
|           |                                 |             |
|           v                                 v             |
|                      Kuma :3001                           |
|                     (4 monitors)                          |
|           ^                                 ^             |
|           |                                 |             |
|      Go pushes:                      Python pushes:       |
|      - bridge_connection             - sync_loop          |
|                                      - transcription      |
|                                      - gap_detector       |
+-----------------------------------------------------------+

+------------- Mac (occasional) ----------------------------+
|                                                           |
|  whatsapp_chat_autoexport                                 |
|  --format spec --output ~/Journal/People/Corresp/WA/     |
|  (batch export for initial seed + rare reseed)            |
|                                                           |
+-----------------------------------------------------------+
```

### Repos

- **`~/GitHub/projects/whatsapp_sync/`** — new repo. Go bridge + Python daemon.
- **`~/GitHub/projects/whatsapp_chat_autoexport/`** — existing repo. Gets `--format spec` output option.

### Contract

SQLite is the only interface between Go and Python. They share no code, no IPC, no sockets. If either process dies, the other is unaffected.

### Deployment

Both processes run as systemd services on Pi 5. Poetry virtualenv for Python (matching voicenotes pipeline pattern). Go binary compiled once, rarely updated.

### Git

Python daemon commits to `~/Journal` with author `whatsapp_sync <whatsapp_sync@pi5>`. Mac pulls to receive updates.

Commit messages: `sync: {N} chats, {M} msgs, {T} transcriptions` for regular cycles. `sync: voice transcription catch-up ({N} files)` for queue drain batches.

---

## Go Bridge

Minimal, stable binary. Rarely touched after initial build.

### Responsibilities

- Connect to WhatsApp Web via whatsmeow
- Handle QR code auth on first run (print to terminal), auto-reconnect thereafter
- Listen for message events, write every message to SQLite
- Download voice/audio media to disk (`data/voice/{messageID}.ogg`)
- Log connection state changes to SQLite (`connection_log` table)
- Push `bridge_connection` heartbeat to Kuma every 60s
- Serve `/health` HTTP endpoint (JSON: connected, last_message_at, uptime)

### Does NOT do

- Transcript formatting
- Vault interaction
- Transcription
- Contact resolution beyond what whatsmeow provides natively
- Media download except voice/audio

### SQLite Schema

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    chat_jid TEXT NOT NULL,
    sender_jid TEXT NOT NULL,
    sender_name TEXT,
    content TEXT,
    timestamp INTEGER NOT NULL,
    is_from_me BOOLEAN NOT NULL,
    media_type TEXT,
    media_path TEXT,
    raw_proto BLOB
);

CREATE TABLE connection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    detail TEXT
);

CREATE TABLE chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    is_group BOOLEAN NOT NULL,
    last_message_at INTEGER,
    participant_jids TEXT
);
```

### Config

Single YAML file: SQLite path, voice download dir, Kuma push URL, health port, log level.

---

## Python Daemon

The brain. Polls SQLite, formats transcripts, transcribes voice, writes to vault, monitors health.

### Main Loop (every 60s)

```
1. PREFLIGHT
   - Check SQLite is accessible
   - Check bridge health (read connection_log)
   - Load state.json (per-chat watermarks, voice queue)
   - If bridge disconnected >7 days -> Kuma gap_detector DOWN

2. SYNC CYCLE
   - Query chats table for last_message_at > stored watermark
   - For each changed chat:
     - Fetch new messages from SQLite (after=watermark - 10min overlap)
     - Dedup against tail of existing transcript.md
     - Format new messages to spec (day headers, typed media, etc.)
     - Append to transcript.md (atomic write via .tmp + rename)
     - Update index.md frontmatter (message_count, last_synced, etc.)
     - Voice messages: add <voice> tag now, queue for transcription
     - Advance watermark only on success
   - Push Kuma sync_loop (up + summary msg)

3. VOICE TRANSCRIPTION DRAIN
   - Pop N items from queue (rate-limited, e.g., 5 per cycle)
   - For each: read audio from disk -> ElevenLabs -> write [Transcription]: line
   - On failure: increment retry count, leave in queue
   - Push Kuma transcription (up if any succeeded, down if all failed)
   - Save updated queue to state.json

4. GIT COMMIT
   - If any files changed:
     - git add People/Correspondence/Whatsapp/
     - git commit --author="whatsapp_sync <whatsapp_sync@pi5>"
   - git push

5. SAVE STATE
   - Write state.json atomically
```

### Modules

| Module | Responsibility |
|--------|---------------|
| `daemon.py` | Main loop, signal handling, systemd integration |
| `bridge_reader.py` | Reads SQLite, returns normalised Message objects |
| `formatter.py` | Messages -> spec format (day headers, typed media, `[Transcription]:`) |
| `vault_writer.py` | Atomic transcript.md append, index.md update, integrity hash |
| `dedup.py` | Message dedup by ID, fallback to timestamp+sender+content hash |
| `transcriber.py` | ElevenLabs wrapper (extracted from exporter, ~200 lines) |
| `voice_queue.py` | Persistent queue with retry counts, rate limiting |
| `gap_detector.py` | Reads connection_log, computes gap duration, alert thresholds |
| `health.py` | Kuma push client (4 monitors), status/msg/ping per heartbeat |
| `config.py` | YAML config: paths, intervals, thresholds, Kuma URLs |
| `state.py` | state.json read/write: watermarks, voice queue, contact cache |

### Dedup Strategy

- Primary key: WhatsApp message ID (from SQLite `messages.id`)
- Fallback (for Appium-originated messages without IDs): `sha256(timestamp_minute + sender + content[:100])`
- On each sync, load last 50 lines of existing transcript.md, compute hashes, skip any incoming message that matches
- Append-only: never modify or remove existing lines

### Atomic Writes

- Write to `transcript.md.tmp`
- Validate: existing content preserved (byte-compare prefix)
- Rename `.tmp` -> `transcript.md`
- If validation fails: log error, skip chat, Kuma sync_loop reports the failure

### Config

```yaml
sqlite_path: /home/ajanderson/whatsapp_sync/data/messages.db
voice_dir: /home/ajanderson/whatsapp_sync/data/voice/
journal_path: /home/ajanderson/Journal
output_path: People/Correspondence/Whatsapp
state_path: /home/ajanderson/whatsapp_sync/state.json
poll_interval_seconds: 60
voice_drain_per_cycle: 5
elevenlabs_api_key_env: ELEVENLABS_API_KEY
git_author: "whatsapp_sync <whatsapp_sync@pi5>"

kuma:
  bridge_connection: https://kuma.pi5:3001/api/push/xxx
  sync_loop: https://kuma.pi5:3001/api/push/yyy
  transcription: https://kuma.pi5:3001/api/push/zzz
  gap_detector: https://kuma.pi5:3001/api/push/www

thresholds:
  gap_warning_days: 3
  gap_alarm_days: 7
  gap_critical_days: 14
  voice_max_retries: 5
```

---

## Appium Exporter Changes

Minimal change to the existing repo. New output format option.

### New Flag

`--format spec` (alongside default `--format legacy`)

### What `--format spec` Produces

```
<Contact Name>/
  index.md
  transcript.md
  transcriptions/
```

Identical format to what the Python daemon writes. Same day headers, same `[HH:MM]` timestamps, same `<voice>` + `[Transcription]:` pattern, same `index.md` frontmatter schema.

### Implementation

- New `SpecFormatter` class as a parallel path alongside existing `OutputBuilder`
- Reuses existing `TranscriptParser` and `TranscriptionManager`
- The format spec document (`Atlas/WhatsApp Transcript Format Spec.md`) is the contract

### What Does NOT Change

- Default behaviour (`--format legacy`)
- Export workflow (Appium, Google Drive, pipeline phases 1-3)
- Transcription logic
- Any existing tests

---

## Kuma Monitoring

Four independent push monitors on the existing Kuma instance at Pi 5 (:3001).

| Monitor | Pushed by | Interval | Goes DOWN when |
|---------|-----------|----------|----------------|
| `bridge_connection` | Go bridge | every 60s | WhatsApp Web disconnected, QR re-auth needed, process crashed |
| `sync_loop` | Python daemon | after each poll cycle | Poll cycle failed, Python crashed, SQLite unreachable |
| `transcription` | Python daemon | after each transcription batch | ElevenLabs unreachable, API key invalid, repeated failures |
| `gap_detector` | Python daemon | after each poll cycle | Last bridge message >7 days old |

Push payload follows the existing Ryanair Fares pattern:
```
GET /api/push/:pushToken?status=up|down&msg=<summary>&ping=<duration_ms>
```

---

## Gap Detection & Reseed Protocol

Three layers prevent silent data loss.

### Layer 1: Bridge Connection Monitoring (Go)

Go bridge pushes `bridge_connection` heartbeat every 60s. If the bridge crashes or WhatsApp Web disconnects, heartbeat stops and Kuma alerts within ~2-3 minutes.

### Layer 2: Gap Duration Tracking (Python)

Every poll cycle, Python reads `connection_log` to compute total disconnected time.

| Condition | Action |
|-----------|--------|
| Bridge disconnected 0-3 days | Kuma `gap_detector` UP, msg includes warning |
| Bridge disconnected 3-7 days | Kuma `gap_detector` UP, msg: "WARNING: bridge down Nd, reseed window closing" |
| Bridge disconnected >7 days | Kuma `gap_detector` DOWN, msg: "ALARM: bridge down Nd, reseed recommended" |
| Bridge disconnected >14 days | Kuma `gap_detector` DOWN, msg: "CRITICAL: history sync window expired, reseed REQUIRED" |

### Layer 3: Per-Chat Continuity Check (Python)

On each sync, for each chat: compare the timestamp of the newest message in SQLite vs the last watermark. If the gap exceeds the bridge's total uptime since last sync, messages were likely missed.

Flagged in state.json:
```json
{
  "suspected_gaps": [
    {
      "chat": "Brothers",
      "gap_start": "2026-04-10",
      "gap_end": "2026-04-15",
      "reason": "bridge downtime exceeded gap"
    }
  ]
}
```

### Reseed Protocol

1. Kuma is DOWN and stays DOWN (no auto-acknowledge)
2. state.json records which chats have gaps and affected date ranges
3. User runs Appium exporter on Mac with `--format spec`
4. Both tools produce identical format, so exporter output overwrites transcript.md with complete history. This is the ONE exception to the daemon's append-only rule — reseed is a manual, human-initiated recovery that replaces the file entirely.
5. User runs `whatsapp-sync reseed-complete` to clear gap flags
6. Kuma returns to UP on next successful poll cycle

The system never silently accepts gaps. It fails loudly and stays failed until human intervention confirms the gap is resolved.

---

## File Layout on Pi 5

```
/home/ajanderson/whatsapp_sync/
+-- bridge/
|   +-- whatsapp-bridge         # compiled Go binary
|   +-- config.yaml
|   +-- store/                  # whatsmeow auth state
+-- daemon/
|   +-- pyproject.toml
|   +-- whatsapp_sync/          # Python package
|   |   +-- daemon.py
|   |   +-- bridge_reader.py
|   |   +-- formatter.py
|   |   +-- vault_writer.py
|   |   +-- dedup.py
|   |   +-- transcriber.py
|   |   +-- voice_queue.py
|   |   +-- gap_detector.py
|   |   +-- health.py
|   |   +-- config.py
|   |   +-- state.py
|   +-- tests/
+-- data/
|   +-- messages.db             # SQLite (Go writes, Python reads)
|   +-- voice/                  # voice files (Go writes, Python reads)
+-- state.json                  # sync state
+-- config.yaml                 # Python daemon config
+-- .env                        # API keys, Kuma URLs
+-- logs/
    +-- bridge.log
    +-- sync.log
```

Development repo: `/Users/ajanderson/GitHub/projects/whatsapp_sync`

### Systemd Services

Two units, both `Type=simple`, `Restart=always`:

**`whatsapp-bridge.service`** — starts Go binary, `RestartSec=10`

**`whatsapp-sync.service`** — starts Python daemon, `After=whatsapp-bridge.service`, `RestartSec=30`

---

## Initial Seeding

1. Build Go bridge, run manually once for QR code auth
2. Install Python daemon via Poetry
3. Configure `.env` and `config.yaml`
4. Set up 4 Kuma push monitors
5. Run Appium exporter on Mac with `--format spec --output ~/Journal/People/Correspondence/Whatsapp/` to produce the baseline
6. Enable both systemd services
7. Daemon picks up from the seed and begins incremental sync

---

## Testing Strategy

### Go Bridge

- SQLite write correctness (message inserted with all fields)
- connection_log entries on connect/disconnect
- Voice media saved to correct path
- Kuma push fires on interval

### Python Daemon

| Area | Approach |
|------|----------|
| `bridge_reader.py` | Unit tests with pre-populated SQLite fixture |
| `formatter.py` | Unit tests: known Messages -> exact spec-format output |
| `vault_writer.py` | Unit tests: atomic write, append-only, index.md updates, integrity hash |
| `dedup.py` | Unit tests: no overlap, full overlap, partial overlap, idempotent |
| `voice_queue.py` | Unit tests: enqueue, drain, retry, max retries |
| `gap_detector.py` | Unit tests: synthetic connection_log, threshold transitions |
| `health.py` | Unit tests: mocked httpx, push payloads, failure handling |
| `daemon.py` | Integration: seed SQLite + vault, run one cycle, verify output |

### Shared Format Compliance

A test fixture of known messages with expected spec-format output. Both the Python daemon's `formatter.py` and the exporter's `SpecFormatter` must produce identical output for the same input. The format spec is the contract.

### Coverage Target

90% (matching exporter).

---

## Scope Boundaries

**In scope:**
- Go bridge (whatsmeow -> SQLite)
- Python daemon (sync loop, transcription, vault writer, Kuma)
- Exporter `--format spec` output option
- 4 Kuma push monitors
- Gap detection and reseed protocol
- Initial seed via batch export

**Not in scope:**
- Contact folder renaming (deferred to contact overhaul)
- Non-voice media download or storage
- Cron scheduling (this is a long-running daemon, not cron)
- Modifications to the Appium export workflow itself
- Pi 5 Kuma deployment (already running)

---

## Risks

| Risk | Mitigation |
|------|-----------|
| whatsmeow API changes | Pin version, monitor tulir/whatsmeow releases |
| QR re-auth every ~20 days | Kuma `bridge_connection` alerts immediately on disconnect |
| ElevenLabs rate limits | Voice queue with rate limiting (5/cycle), exponential backoff on 429 |
| Large SQLite on Pi SD card | Store data/ on 4TB HDD at /mnt/ext4TB_HDD if needed |
| Git conflicts on Journal repo | Sync only writes to People/Correspondence/Whatsapp/ — user never edits transcript.md |
| Bridge down >14 days | Gap detector CRITICAL, reseed protocol |

---

## References

- **Format spec:** `Atlas/WhatsApp Transcript Format Spec.md`
- **whatsmeow:** https://github.com/tulir/whatsmeow
- **Existing exporter:** `~/GitHub/projects/whatsapp_chat_autoexport/`
- **Pi 5 server note:** `Atlas/pi5 Server.md`
- **Previous plan (superseded):** `Journal/docs/plans/2026-03-26-001-feat-whatsapp-unified-sync-tool-plan.md`
- **Requirements:** `Journal/docs/brainstorms/2026-03-25-whatsapp-incremental-sync-requirements.md`
