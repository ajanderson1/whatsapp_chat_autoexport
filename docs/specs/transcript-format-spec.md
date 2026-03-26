---
type: reference
description: Canonical format specification for WhatsApp chat transcripts in the vault. Anchored on RSMF (eDiscovery), EDRM (metadata fields), and CHILDES CHAT (readability). Both the Appium exporter and MCP sync engine must conform to this spec.
tags:
  - whatsapp
  - specification
  - data_format
---

# WhatsApp Transcript Format Spec

Canonical format for WhatsApp chat transcripts in the Obsidian vault. Both the batch exporter and the incremental MCP sync engine must produce output conforming to this spec.

**Design anchors:**
- **RSMF** (Relativity Short Message Format) — structural model: participants, conversations, typed events
- **EDRM Short Message Metadata Primer** — metadata field checklist (40+ fields for chat messages)
- **CHILDES CHAT** — human-readable conversation transcription conventions (40+ years academic use)
- **OAIS** (ISO 14721) — separation of Content Information from Preservation Description Information

## File Structure

Each chat occupies a folder under `People/Correspondence/Whatsapp/<Chat Name>/`:

```
People/Correspondence/Whatsapp/
  Tim Cocking/
    index.md              # Companion note: metadata, summary, links (small, fast)
    transcript.md         # Raw messages (large, excluded from graph)
    media/                # Media files (optional)
    transcriptions/       # Voice transcription files (optional)
```

### Rationale

The **companion note pattern** separates metadata from content:
- `index.md` is the vault-native interface: queryable by Dataview, linked in the knowledge graph, safe for LLM context (no message content)
- `transcript.md` is the archive: large, raw, excluded from the graph but fully searchable

This follows the OAIS principle of separating Preservation Description Information (index.md) from Content Information (transcript.md), and mitigates the lethal trifecta by ensuring an LLM can read metadata without ingesting untrusted message content.

---

## index.md (Companion Note)

### Frontmatter Schema

```yaml
---
type: note
description: "WhatsApp correspondence with Tim Cocking"
tags:
  - whatsapp
  - correspondence
cssclasses:
  - whatsapp-chat

# Identity
chat_type: direct                           # direct | group
contact: "[[Tim Cocking]]"                  # WikiLink to person note (direct chats)
phone: "+44 7956 173473"                    # E.164 format
jid: "447956173473@s.whatsapp.net"          # WhatsApp JID (stable identifier)

# For group chats, replace contact/phone with:
# chat_name: "Brothers"
# participants:
#   - "[[Tim Cocking]]"
#   - "[[Peter Cocking]]"
#   - "+49 174 9580928"                     # unresolved contact

# Message Stats (updated on each sync)
message_count: 16950
media_count: 1259
voice_count: 47
date_first: 2015-07-29
date_last: 2026-03-25
last_synced: 2026-03-26T00:33:07

# Source Provenance
sources:
  - type: appium_export
    date: 2026-03-26
    messages: 16950
  - type: mcp_bridge
    date: 2026-03-26
    messages: 312
coverage_gaps: 0

# LLM Context (safe to expose without message content)
timezone: Europe/Stockholm
languages:
  - en
summary: >-
  Close personal friendship spanning 11 years. Frequent topics: sailing,
  skiing, aviation, Raspberry Pi, family events, career planning.
---
```

### Body

```markdown
> WhatsApp correspondence with [[Tim Cocking]]
> Period: 2015-07-29 to 2026-03-25 | 16,950 messages

[[People/Correspondence/Whatsapp/Tim Cocking/transcript|Full Transcript]]
```

The body is minimal — just a human-readable summary line and a link to the transcript. Dataview queries target the frontmatter fields. Smart Connections embeds this small file efficiently.

### Group Chat Variant

```yaml
---
type: note
description: "WhatsApp group chat — Brothers"
tags:
  - whatsapp
  - correspondence
  - group_chat
cssclasses:
  - whatsapp-chat

chat_type: group
chat_name: "Brothers"
participants:
  - "[[Tim Cocking]]"
  - "[[Peter Cocking]]"
  - "[[Paul Ashley Cocking]]"
  - "+49 174 9580928"
jid: "491749580928-1452027796@g.us"

message_count: 2781
media_count: 191
voice_count: 12
date_first: 2016-01-05
date_last: 2026-03-25
last_synced: 2026-03-26T00:29:38

sources:
  - type: appium_export
    date: 2026-03-26
    messages: 2781
coverage_gaps: 0

timezone: Europe/Stockholm
languages:
  - en
summary: >-
  Family group chat with brothers. Topics: event planning (golf, IoM TT,
  Cocking 10K), travel coordination, family logistics.
---
```

---

## transcript.md (Message Archive)

### Minimal Frontmatter

The transcript itself carries only enough frontmatter to be excluded from the graph and identified:

```yaml
---
cssclasses:
  - whatsapp-transcript
  - exclude-from-graph
---
```

### Header Block

Below the frontmatter, a comment-style header records integrity metadata:

```
<!-- TRANSCRIPT METADATA
chat_jid: 447956173473@s.whatsapp.net
contact: Tim Cocking
generated: 2026-03-26T00:33:07Z
generator: wa-sync/1.0.0
message_count: 16950
media_count: 1259
date_range: 2015-07-29..2026-03-25
body_sha256: a3f2c1b9d4e5f6a7b8c9d0e1f2a3b4c5...
-->
```

The `body_sha256` is the SHA-256 hash of everything below the header. If the file is regenerated from the same inputs, this hash must match. A mismatch indicates data corruption or unexpected mutation.

### Message Format

Messages are grouped by day with ISO 8601 date headers:

```markdown
## 2015-07-29

[00:05] AJ Anderson: Do you know Woodville church, Cardiff.
[00:11] Tim Cocking: Wrong. She's a bute.
[00:12] Tim Cocking: Don't know this church.
[00:13] AJ Anderson: Met a couple from that church yesterday. Wouldn't have surprised me.

## 2015-08-02

[16:56] Tim Cocking: <photo IMG-20150802-WA0004.jpg>
[16:56] Tim Cocking: <photo IMG-20150802-WA0005.jpg>
[16:56] Tim Cocking: <photo IMG-20150802-WA0006.jpg>
[16:56] Tim Cocking: <photo IMG-20150802-WA0007.jpg>
[16:56] Tim Cocking: See pics
```

### Timestamp Rules

- Day headers use ISO 8601: `## YYYY-MM-DD`
- Message times use 24-hour format: `[HH:MM]`
- Timezone is not repeated per line — stored once in `index.md` frontmatter (`timezone: Europe/Stockholm`)
- Messages within a day are ordered chronologically
- When second-precision is available (MCP bridge), it is stored in the state file for dedup but not displayed in the transcript (minute precision suffices for human reading)

### Sender Format

- Use the display name as it appears in WhatsApp
- For the vault owner: use "AJ Anderson" consistently (not "Me" or "You")
- For group chats with unresolved phone numbers: use the phone number as sender (e.g., `+49 174 9580928`)
- Sender names must be consistent across the entire transcript — if a contact changes their display name, use the current name throughout

### Message Types

#### Text Messages

```
[HH:MM] Sender: message content here
```

Multi-line messages use continuation lines (no timestamp, no sender prefix):

```
[13:20] AJ Anderson: Could you rifle through my mail.
My credit card expires next month so wondering
if they sent a new one.
```

#### Media (Non-Voice)

Classified by type. Include filename only when it has semantic value (documents, PDFs):

```
[16:56] Tim Cocking: <photo IMG-20150802-WA0004.jpg>
[14:22] AJ Anderson: <video>
[09:30] Tim Cocking: <sticker>
[11:45] AJ Anderson: <document Flight_Booking_Confirmation.pdf>
[16:00] Tim Cocking: <photo>
```

Rules:
- Use `<photo>`, `<video>`, `<audio>`, `<sticker>`, `<gif>`, `<document>` based on media type
- Include the filename when: it's a document/PDF with a descriptive name, or the file exists in `media/`
- Omit the filename for auto-generated names like `IMG-20150802-WA0004.jpg` — they're noise
- `<Media omitted>` is **not used** — always classify the type if known, or use `<media>` if truly unknown

#### Voice Messages with Transcription

```
[10:15] Tim Cocking: <voice>
  [Transcription]: Bring a frying pan, spatula, butter and stuff, and a knife if you want to fry it up with some black pudding.
```

Rules:
- Two-space indent before `[Transcription]:`
- Transcription text is always a single line (no line breaks)
- Filler words (uh, um, eh) are preserved — the raw transcription file is authoritative
- If transcription failed: just `<voice>` with no `[Transcription]:` line
- The separate transcription file in `transcriptions/` is retained as the raw source. The inline version is the clean display copy.

#### System Events

Preserved verbatim, no sender prefix:

```
[17:54] Your security code with Tim Cocking changed. Tap to learn more.
[22:07] +49 174 9580928 was added
[00:00] Messages and calls are end-to-end encrypted.
```

#### View-Once Messages

```
[14:16] AJ Anderson: <view-once voice>
[09:30] Tim Cocking: <view-once photo>
```

---

## Dataview Queries

With the `index.md` companion notes in place, these queries become possible:

### All Direct Chats by Last Activity

```dataview
TABLE WITHOUT ID
  contact AS "Contact",
  message_count AS "Messages",
  date_last AS "Last Active",
  date_first AS "Since"
FROM "People/Correspondence/Whatsapp"
WHERE chat_type = "direct" AND contains(tags, "whatsapp")
SORT date_last DESC
```

### Stale Chats (Not Synced in 30 Days)

```dataview
TABLE contact, last_synced, message_count
FROM "People/Correspondence/Whatsapp"
WHERE contains(tags, "whatsapp") AND last_synced < date(today) - dur(30d)
SORT last_synced ASC
```

### Chats With Coverage Gaps

```dataview
TABLE contact, coverage_gaps, sources
FROM "People/Correspondence/Whatsapp"
WHERE contains(tags, "whatsapp") AND coverage_gaps > 0
```

### Group Chats

```dataview
TABLE chat_name, length(participants) AS "Members", message_count
FROM "People/Correspondence/Whatsapp"
WHERE chat_type = "group"
SORT message_count DESC
```

### Person Note Integration

On a person note (e.g., `People/Contacts/Tim Cocking.md`), add:

```dataview
LIST
FROM "People/Correspondence/Whatsapp"
WHERE contact = [[Tim Cocking]] OR contains(participants, [[Tim Cocking]])
```

---

## Graph View Configuration

To prevent transcript pollution of the knowledge graph:

1. **Exclude transcripts:** In Graph View filters: `-path:People/Correspondence/Whatsapp -file:transcript`
2. **Keep index notes visible:** The `index.md` files participate in the graph, linking person notes to their WhatsApp chats
3. **CSS class filtering:** The `exclude-from-graph` cssclass on transcript.md files provides an additional signal for any plugin-level filtering

---

## Migration Path

### From Current Format

The existing 417 `transcript.txt` files will be migrated by the unified Python tool:

1. Parse existing `transcript.txt` (DD/MM/YYYY format)
2. Generate `index.md` with frontmatter (from parsed header + message statistics)
3. Generate `transcript.md` with new format (ISO day headers + time-only lines)
4. Validate: message count matches, body hash computed
5. Keep original `transcript.txt` as backup until verified

### Ongoing Sync

Both the Appium exporter and MCP sync engine produce output in this format. The Python tool handles:
- Format bridge (MCP timestamps → spec format)
- Dedup across sources
- Voice transcription (inline + raw file)
- Atomic writes with integrity validation
- `index.md` stats update

---

## References

- **RSMF (Relativity Short Message Format)** — structural model for participants, conversations, events
- **EDRM Short Message Metadata Primer 1.0** — metadata field checklist for chat messages
- **CHILDES CHAT** (Carnegie Mellon / TalkBank) — human-readable transcription conventions
- **OAIS** (ISO 14721) — separation of Content from Preservation metadata
- **PREMIS** (Library of Congress) — fixity and integrity metadata (body_sha256)
- **Lethal Trifecta** (Simon Willison) — companion note pattern mitigates by separating metadata from content
