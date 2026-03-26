---
title: "feat: MCP Incremental Sync + New Transcript Format"
type: feat
status: active
date: 2026-03-26
origin: ~/Journal/docs/brainstorms/2026-03-25-whatsapp-incremental-sync-requirements.md
---

# feat: MCP Incremental Sync + New Transcript Format

## Overview

Extend the exporter to support the WhatsApp MCP bridge as a second data source (alongside Appium), and refactor the output to produce a new standardised transcript format with companion notes. This makes the exporter the unified data pipeline for all WhatsApp transcript management.

**Three things are changing:**
1. **New data source:** MCP bridge (incremental sync via SQLite/API)
2. **New output format:** Companion notes (index.md + transcript.md) with day headers, typed media, integrity hashing — defined in `docs/specs/transcript-format-spec.md`
3. **New CLI commands:** `sync`, `ingest`, `migrate`, `rebuild`

The existing Appium export pipeline is unchanged. New functionality is additive.

## Context

This project currently has one data path: Appium → Google Drive → ZIP → process → output. The WhatsApp MCP bridge (`lharries/whatsapp-mcp`) provides direct access to message data via a Go bridge that stores messages in SQLite. However, the MCP bridge only has messages from when it's running (~2 weeks of history sync on initial auth), so Appium remains the source for historical completeness.

The new output format is defined in `docs/specs/transcript-format-spec.md` (canonical copy in the journal vault at `Atlas/WhatsApp Transcript Format Spec.md`). Both the existing Appium pipeline and the new MCP sync must produce output conforming to this spec.

A thin journal skill (in the vault, not this project) will invoke these CLI commands and handle vault-side orchestration. This project is the data pipeline — it gets messages, formats them, and writes files.

## Scope

**In scope:**
- `sources/` module — data source abstraction layer
- `mcp/` module — MCP bridge reader, incremental state, contact resolution
- `processing/dedup.py` — cross-source deduplication
- Refactored `output/` — new format spec output (SpecFormatter, IndexBuilder)
- New CLI commands: `sync`, `ingest`, `migrate`, `rebuild`
- Backward compatibility via `--legacy-format` flag

**Not in scope:**
- Changes to the Appium export workflow (whatsapp_driver.py, chat_exporter.py)
- Changes to the TUI
- Journal vault skill (separate project)
- Cron scheduling

## Key Technical Decisions

- **Data source abstraction:** Introduce `MessageSource` interface so the pipeline treats Appium and MCP identically. The existing `TranscriptParser` gets wrapped as `AppiumSource`.
- **MCP access method:** Import the MCP server's Python query functions directly (they're just SQLite queries wrapped in Python). The MCP server at `~/GitHub/claude/mcps/third_party/whatsapp/repo/whatsapp-mcp-server/whatsapp.py` is a single file — its query functions can be called from this project. Alternatively, read SQLite directly with a known schema.
- **Dedup key:** WhatsApp message ID (from MCP) when available, else compound key (timestamp_minute + sender_hash + content_hash).
- **Output format:** `SpecFormatter` is a new module that produces the spec format. The existing `OutputBuilder` delegates to it (or to the legacy formatter via flag). This preserves backward compatibility.
- **State management:** Per-chat watermarks + contact cache + voice retry queue in a versioned JSON file. Path configurable (defaults to `~/.whatsapp-sync/state.json` or specified by the journal skill).
- **Voice transcription:** Reuses the existing `TranscriptionManager` and `ElevenLabsTranscriber`. For MCP sync, audio is downloaded via the bridge's REST API or `download_media` function, then transcribed with the same pipeline.

## Implementation Units

### Phase 1: Data Source Abstraction

- [ ] **Unit 1: MessageSource interface + AppiumSource adapter**

**Goal:** Abstract the data source so the pipeline can accept messages from Appium, MCP, or existing transcripts without coupling.

**Files:**
- Create: `whatsapp_chat_autoexport/sources/__init__.py`
- Create: `whatsapp_chat_autoexport/sources/base.py`
- Create: `whatsapp_chat_autoexport/sources/appium_source.py`
- Create: `whatsapp_chat_autoexport/sources/transcript_source.py`
- Modify: `whatsapp_chat_autoexport/processing/transcript_parser.py` — extend `Message` dataclass with optional `message_id` and `source` fields
- Test: `tests/unit/test_sources.py`

**Approach:**
- `MessageSource` abstract class with methods: `get_chats() → List[ChatInfo]`, `get_messages(chat_id, after=None, limit=None) → List[Message]`, `get_media(message_id) → Path`
- `ChatInfo` dataclass: `jid`, `name`, `last_message_time`, `message_count`
- `AppiumSource` wraps `TranscriptParser` — takes a directory of Appium export output, returns `Message` objects via the existing parser
- `TranscriptSource` reads existing vault transcripts (both old `.txt` and new `.md` format) into `Message` objects
- Extend `Message` dataclass: add `message_id: Optional[str] = None` and `source: str = "unknown"`

**Patterns to follow:**
- `BaseTranscriber` pattern (abstract base with concrete implementations)
- `TranscriptParser.parse_transcript()` return signature

**Test scenarios:**
- `AppiumSource` produces same messages as `TranscriptParser` directly
- `TranscriptSource` reads old format correctly
- `Message` dataclass backward compatible (new fields optional)

---

- [ ] **Unit 2: MCPSource + bridge reader**

**Goal:** Data source that reads from the WhatsApp MCP bridge, with incremental state management.

**Files:**
- Create: `whatsapp_chat_autoexport/sources/mcp_source.py`
- Create: `whatsapp_chat_autoexport/mcp/__init__.py`
- Create: `whatsapp_chat_autoexport/mcp/bridge_reader.py`
- Create: `whatsapp_chat_autoexport/mcp/state.py`
- Test: `tests/unit/test_mcp_source.py`
- Test: `tests/unit/test_bridge_reader.py`
- Test: `tests/unit/test_mcp_state.py`

**Approach:**
- `BridgeReader` — reads the MCP bridge's SQLite database directly. Configurable DB path. Methods: `list_chats()`, `get_messages(jid, after=, limit=)`, `get_sender_name(jid)`, `download_media(message_id, chat_jid)`
- `MCPSource` implements `MessageSource` — uses `BridgeReader`, translates to `Message` objects with `source="mcp"` and `message_id` populated from WhatsApp's internal IDs
- `MCPState` — manages per-chat watermarks (keyed by JID), contact name cache, voice retry queue. Versioned JSON. Atomic writes. Graceful degradation on corruption.
- 10-minute overlap window: `get_messages(after=watermark - 10min)` to handle boundary edge cases
- Pagination: iterate with increasing `page` until empty results

**SQLite schema (from MCP bridge):**
```
messages: id, chat_jid, sender, content, timestamp, is_from_me, media_type, filename, url, media_key, ...
chats: jid, name, last_message_time
```

**Test scenarios:**
- Bridge not running (DB doesn't exist) → clear error
- Normal query → `Message` objects with correct fields
- Overlap window → messages before watermark included
- Pagination → all messages retrieved for large chats
- State read/write → round-trips correctly
- State corruption → reinitialises with warning
- Contact resolution → JID → display name

---

- [ ] **Unit 3: Deduplication engine**

**Goal:** Deduplicate messages across multiple sources deterministically.

**Files:**
- Create: `whatsapp_chat_autoexport/processing/dedup.py`
- Test: `tests/unit/test_dedup.py`

**Approach:**
- Input: list of `Message` objects from any combination of sources
- Dedup key: `message_id` when available (MCP), else compound key `hash(timestamp_minute + sender + content[:80])`
- Incremental mode: compare against tail of existing transcript (for sync speed)
- Full mode: merge all sources (for ingest/reconciliation)
- Conflict resolution: prefer MCP version (has second-precision timestamp + message_id)
- Output: deduplicated, chronologically sorted `Message` list

**Test scenarios:**
- No overlap → all retained
- Full overlap → no duplicates
- Same content same minute → deduplicated
- MCP vs Appium conflict → MCP preferred
- Idempotent: twice produces identical output
- `[Transcription]` travels with parent message

---

### Phase 2: New Format Output

- [ ] **Unit 4: SpecFormatter + IndexBuilder**

**Goal:** Output modules that produce the new transcript format defined in `docs/specs/transcript-format-spec.md`.

**Files:**
- Create: `whatsapp_chat_autoexport/output/spec_formatter.py`
- Create: `whatsapp_chat_autoexport/output/index_builder.py`
- Test: `tests/unit/test_spec_formatter.py`
- Test: `tests/unit/test_index_builder.py`

**Approach:**

`SpecFormatter` — pure function: `Message` list → formatted transcript content:
- Groups messages by date → `## YYYY-MM-DD` headers
- Formats each message: `[HH:MM] Sender: content`
- Typed media: `<photo>`, `<video>`, `<voice>`, `<document>`, `<sticker>` (from `Message.media_type`)
- Voice with transcription: `  [Transcription]: text` on next line
- System events: `[HH:MM] event text` (no sender prefix)
- Multi-line: continuation lines (no prefix)
- Integrity: computes `body_sha256` of the formatted body
- Minimal frontmatter: `cssclasses: [whatsapp-transcript, exclude-from-graph]`
- Integrity header comment block with chat_jid, message_count, date_range, body_sha256

`IndexBuilder` — generates `index.md` companion note:
- YAML frontmatter: type, description, tags, cssclasses, chat_type, contact WikiLink, JID, phone, stats, sources, timezone, languages, summary placeholder
- Body: one-liner with WikiLink + transcript link
- Group chat variant: `participants:` list instead of `contact:`
- Updates existing index.md: increments stats, updates last_synced, appends to sources list

**Patterns to follow:**
- Existing `OutputBuilder._build_merged_transcript()` structure
- Spec examples from `docs/specs/transcript-format-spec.md`

**Test scenarios:**
- Text message → `[HH:MM] Sender: content` under correct day header
- Media → typed tag (not `<Media omitted>`)
- Voice + transcription → inline `[Transcription]:`
- Day boundary → new header
- `is_from_me` → configured user display name
- `body_sha256` matches content
- `index.md` → valid YAML, correct WikiLinks
- Group chat index → participants list

---

- [ ] **Unit 5: Refactor OutputBuilder**

**Goal:** Wire `SpecFormatter` and `IndexBuilder` into the existing `OutputBuilder`, with backward compatibility.

**Files:**
- Modify: `whatsapp_chat_autoexport/output/output_builder.py`
- Test: `tests/unit/test_output_builder.py` (extend existing tests)

**Approach:**
- Add `format_version` parameter to `build_output()`: `"legacy"` (default) or `"v2"`
- `"legacy"` → existing `_build_merged_transcript()` logic, unchanged
- `"v2"` → delegates to `SpecFormatter` for transcript + `IndexBuilder` for index.md
- Output structure changes for v2:
  - `transcript.txt` → `transcript.md`
  - New `index.md` alongside transcript
- Atomic write for v2: `.tmp` → validate → rename
- `batch_build_outputs()` passes format_version through

**Test scenarios:**
- Legacy format → identical to current output (regression test)
- V2 format → spec-conformant companion notes
- Atomic write failure → original preserved
- Batch operation → all chats formatted consistently

---

### Phase 3: New CLI Commands

- [ ] **Unit 6: `whatsapp sync` command**

**Goal:** Incremental sync from MCP bridge — the primary way to keep transcripts current.

**Files:**
- Create: `whatsapp_chat_autoexport/cli/commands/sync.py`
- Modify: `whatsapp_chat_autoexport/cli/main.py` — register new command
- Modify: `pyproject.toml` — add `whatsapp-sync` script entry point
- Test: `tests/integration/test_sync_command.py`

**Approach:**
- Uses `MCPSource` + `SpecFormatter` + `OutputBuilder(format_version="v2")`
- Flow: load state → preflight (query chats, compare watermarks) → retry voice queue → per-chat sync → save state → JSON summary
- Per-chat isolation: one failure doesn't block others
- `--output DIR`: vault output path (required)
- `--state-file PATH`: state file path (default `~/.whatsapp-sync/state.json`)
- `--dry-run`: report without writing
- `--chat NAME`: sync specific chat only
- `--legacy-format`: produce old format (escape hatch)
- Stdout: JSON summary (for journal skill). Stderr: progress logging.
- Voice transcription: uses existing `TranscriptionManager` with `ElevenLabsTranscriber`

**Test scenarios:**
- First run → creates companion notes for all MCP chats
- Normal run → skips unchanged, appends to changed
- MCP unavailable → clean abort with JSON error
- One chat fails → others succeed, failure in summary
- Re-run → idempotent
- `--dry-run` → no files written

---

- [ ] **Unit 7: `whatsapp ingest`, `whatsapp migrate`, `whatsapp rebuild` commands**

**Goal:** Supporting commands for reconciliation, migration, and recovery.

**Files:**
- Create: `whatsapp_chat_autoexport/cli/commands/ingest.py`
- Create: `whatsapp_chat_autoexport/cli/commands/migrate.py`
- Create: `whatsapp_chat_autoexport/cli/commands/rebuild.py`
- Modify: `whatsapp_chat_autoexport/cli/main.py` — register commands
- Modify: `pyproject.toml` — add script entry points
- Test: `tests/integration/test_ingest_command.py`
- Test: `tests/integration/test_migrate_command.py`

**Approach:**

`whatsapp ingest <export-dir> --output <vault-dir>`:
- Reads Appium export via `AppiumSource`
- For each chat: loads existing transcript via `TranscriptSource`
- Dedup + merge → write v2 format
- Reports gap fills

`whatsapp migrate --input <vault-dir>`:
- Reads all existing `transcript.txt` via `TranscriptSource`
- Writes new `transcript.md` + `index.md` per chat
- Keeps original as backup
- Validates message counts match

`whatsapp rebuild <chat-name> --output <vault-dir>`:
- Fetches full history from `MCPSource` (no watermark filter)
- Writes fresh transcript + index
- Resets watermark in state

All commands output JSON summary to stdout.

**Test scenarios:**
- Ingest fills gaps from bridge downtime
- Migrate preserves message counts
- Rebuild from MCP produces spec-conformant output
- All idempotent

---

## Risks

| Risk | Mitigation |
|------|-----------|
| MCP bridge SQLite schema changes | `BridgeReader` is the single coupling point. Schema queries isolated in one file. |
| OutputBuilder refactor breaks Appium pipeline | `format_version="legacy"` is default. Existing tests serve as regression suite. |
| Large transcripts slow to migrate | Pagination. Progress reporting. Test with Tim Cocking's 18K-line transcript. |
| Voice transcription during sync is slow | Retry queue absorbs failures. Text sync is never blocked by transcription. |
| State file corruption | Graceful degradation to transcript-based watermarks. Atomic writes. |

## Sources

- **Format spec:** `docs/specs/transcript-format-spec.md`
- **Journal plan:** `~/Journal/docs/plans/2026-03-26-001-feat-whatsapp-unified-sync-tool-plan.md`
- **MCP bridge source:** `~/GitHub/claude/mcps/third_party/whatsapp/repo/whatsapp-bridge/main.go`
- **MCP Python server:** `~/GitHub/claude/mcps/third_party/whatsapp/repo/whatsapp-mcp-server/whatsapp.py`
