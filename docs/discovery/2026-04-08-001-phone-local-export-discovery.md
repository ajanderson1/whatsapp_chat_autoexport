---
title: "discovery: Phone-local export feasibility"
type: discovery
status: not started
date: 2026-04-08
target_version: 0.4.0
roadmap: docs/plans/2026-04-08-001-feat-v1.0.0-public-release-roadmap.md
---

# discovery: Phone-local export feasibility

## Purpose

Establish whether WhatsApp chat export ZIPs can reliably be saved to **phone-local storage** (instead of Google Drive) and then **ADB-pulled** off the device, across the range of Android versions and devices a public release would need to support.

This is a **research and prototyping document**, not an implementation plan. Its job is to surface the unknowns so a real plan can be written for **v0.5.0**.

## Why this matters

Today, the tool's only export path is: WhatsApp → Google Drive → tool downloads from Drive → tool processes locally. Drive is **on the critical path** even though it's just a transit medium — the exported data has to leave the phone, sit in Drive, and come back to the user's machine.

The user has stated that what they actually want is: WhatsApp → some local share target on the phone → tool ADB-pulls from phone storage → tool processes locally. **Drive is removed from the critical path entirely.**

This is **not** the same as the existing `--pipeline-only` "manual local files" mode (that mode operates on ZIPs the user has already extracted to their computer, typically by having downloaded them from Drive manually). Phone-local export is a *new export path* that requires changes to the `ChatExporter` driver code, which currently hardcodes the Drive selection step.

Per the roadmap, phone-local export is a **v1.0.0 blocker**, and this discovery is the **single biggest risk to the v1.0 timeline** (Risk R1 in the roadmap). If this discovery surfaces blockers, the v0.4.0 checkpoint at the end of this work decides one of:

- **(a) Proceed** to v0.5.0 implementation as planned. Phone-local export ships in v1.0 across the documented device range.
- **(b) Re-scope v0.5.0** to a narrower device range. Phone-local ships in v1.0 with documented limitations.
- **(c) Defer phone-local out of v1.0**. v1.0 ships with Drive only, plus the existing manual local-files mode in the Source picker. Phone-local becomes a v1.x feature.

## Scope

**In scope for this discovery:**

- Identifying which non-Drive share targets WhatsApp's export flow exposes on real Android devices.
- Identifying where each share target writes the resulting ZIP file on the phone filesystem.
- Identifying any permission, scoped storage, or file size issues that would prevent ADB pull.
- Producing a **working prototype** that exercises one viable share target end-to-end on at least the primary test device.
- Writing up findings against the questions below so a v0.5.0 plan can be written.

**Out of scope:**

- A polished UX for picking the share target.
- Automatic device-specific share target selection.
- Falling back from phone-local to Drive automatically.
- Any TUI work — this is a research cycle that may or may not even involve modifying the TUI.

## Background

### Current export flow

`ChatExporter.export_chat_to_google_drive()` (in `whatsapp_chat_autoexport/export/chat_exporter.py:798`) currently:

1. Opens the chat.
2. Taps the menu (three dots).
3. Taps "More".
4. Taps "Export chat".
5. Picks media option (with/without media).
6. **Selects "Drive" / "My Drive" from the share sheet.** (This is the hardcoded step.)
7. Waits for upload to complete.

The Drive selection at step 6 is the binding constraint. WhatsApp's "share" intent at that step exposes whatever share targets the user's device has installed: typically Drive, Gmail, Bluetooth, sometimes "Files", "Save to phone", file manager apps, third-party storage apps, etc. The available targets depend on the device, the Android version, and which apps the user has installed.

### What "phone-local" means concretely

The user wants the share sheet step to pick **a target that writes the ZIP to the phone's local filesystem**, not to a cloud service. The tool then ADB-pulls the ZIP from that local location and processes it normally. The pipeline's existing extract → transcribe → build phases are unchanged — only the *acquisition* of the ZIP changes.

## Discovery Questions

These are the questions the v0.4.0 work needs to answer. Each question has space for findings; this document is filled in *during* the discovery cycle, not before.

### Q1. Which share targets are available?

On the primary test device, what share targets does WhatsApp's "Export chat" share sheet expose? Capture this with screenshots if useful.

- Device model:
- Android version:
- WhatsApp version:
- Share targets visible in the export share sheet (full list):

Repeat on at least one secondary test device if available.

**Findings**: _to be filled in during discovery_

### Q2. Which share targets are reliable file-system writes?

Of the targets in Q1, which ones actually write a ZIP to a known location on the phone filesystem (as opposed to consuming the file as an intent and forwarding it to a cloud service)? Candidates to investigate:

- "Files" / "Files by Google"
- The system file picker / "Save to" dialog
- Stock manufacturer file manager (Samsung My Files, Pixel default, etc.)
- "Save to phone" / "Save to device" if present
- Third-party file manager apps (Solid Explorer, etc.) — only if widely installed enough to matter

For each candidate, capture:
- Target name as it appears in the share sheet:
- Where the ZIP is written on the filesystem:
- Whether the user is prompted to pick a folder, or it goes to a default:
- Whether the operation is synchronous (returns control to WhatsApp) or backgrounded:
- Any UI confirmation step the user has to interact with:

**Findings**: _to be filled in during discovery_

### Q3. Where do the ZIPs land?

For each viable target from Q2, document the **exact path** on the device filesystem and whether it's accessible to ADB:

- Path:
- Accessible via `adb shell ls`?
- Accessible via `adb pull`?
- Owned by which UID?
- Affected by Android scoped storage?

**Findings**: _to be filled in during discovery_

### Q4. Does it work for "with media" exports?

WhatsApp's "with media" export creates a single ZIP that may be hundreds of MB or even multiple GB. Some share targets reject large files; some chunk them. Test:

- A small chat (text only).
- A medium chat (~50 MB).
- A large chat (~500 MB).
- A very large chat (~2 GB) if available.

For each, does the share target accept the file? Where does it write? Does WhatsApp split the export into chunks, and if so, how?

**Findings**: _to be filled in during discovery_

### Q5. Permissions and scoped storage

Android 11+ introduced scoped storage, which restricts what apps and ADB can access on `/sdcard`. Specifically:

- Can ADB read the directory the share target wrote to without root?
- Does the file have permissions that allow `adb pull` to read it?
- Does WhatsApp itself need any new permissions for the share to succeed (storage, etc.)?
- Does the test device have any manufacturer-specific permission UI that affects this?

**Findings**: _to be filled in during discovery_

### Q6. UI automation reliability

The current `ChatExporter` clicks share targets by text matching. For phone-local mode, the script needs to:

- Identify the right share target by some stable identifier (resource ID, accessibility label, text).
- Tap it reliably across devices.
- Handle any subsequent picker dialogs (folder selection, confirmation).

Are share targets identified by stable resource IDs in the Appium page source, or only by text? Does the resource ID differ across devices for the same target? Is there a folder picker dialog after selecting the target, and if so, can it be automated?

**Findings**: _to be filled in during discovery_

### Q7. Cross-device reliability

If the primary test device is the only device tested, the v1.0 release will only support that one device's flow. To support more devices, we need to know:

- Which target is *most likely* to be available across Pixel, Samsung, and stock Android builds?
- Is there a "lowest common denominator" target that exists on essentially every Android device?
- If not, is a per-device-family share target chooser acceptable?

**Findings**: _to be filled in during discovery_

### Q8. Edge cases and failure modes

- What happens if the share target dialog is cancelled mid-flow?
- What happens if the disk is full?
- What happens if WhatsApp's share sheet is empty (no targets)?
- What happens if the chosen target writes to a path that ADB can't read?
- What happens if a previous export with the same name already exists at the target location?

**Findings**: _to be filled in during discovery_

### Q9. Cleanup

After ADB-pulling the ZIP off the phone, should the script delete the original from phone storage (analogous to `delete_from_drive`)? If so:

- Does ADB have permission to delete from the target location?
- Is there a `delete_from_phone` setting we need on the Settings panel?
- Should this be opt-in or default-on?

**Findings**: _to be filled in during discovery_

### Q10. End-to-end timing

How long does the phone-local flow take per chat compared to the Drive flow for a comparable-sized export? Drive's current bottleneck is the upload + poll loop (typically minutes for large media chats). Phone-local should be much faster but the share-sheet automation is unproven.

**Findings**: _to be filled in during discovery_

## Prototype

The deliverable of v0.4.0 is **not just answers to the questions above** but also a working prototype. The prototype is:

- A standalone script (or modified `ChatExporter` method) that exports one chat using one phone-local share target end-to-end.
- ADB-pulls the resulting ZIP to a known location on the host machine.
- Verifies the ZIP is valid (`zipfile.is_zipfile()`).
- Documents the exact button taps, share target, and pull command in this discovery document.

The prototype does **not** need to be production-quality. It just needs to *prove the path exists*.

### Prototype scope

- **One device** (the primary test device — Pixel_10_Pro per recent sessions).
- **One share target** (the one identified as most viable in Q2).
- **One chat** of moderate size with a mix of text and media.
- **One ADB pull command**.

If the prototype works on the primary device, the next question is whether it generalizes. If it doesn't generalize, see the v0.4.0 checkpoint decision below.

## Checkpoint Decision Framework

At the end of v0.4.0, this document should contain:

1. **Filled-in answers** to Q1–Q10 for at least the primary test device.
2. **A working prototype** demonstrating end-to-end phone-local export on the primary test device.
3. **A generalization assessment**: based on Q1–Q9 findings, what is the likelihood that this works on:
   - Pixel devices on the latest two Android versions?
   - Samsung devices on the latest two Android versions?
   - Other Android devices on the latest two Android versions?
4. **A recommendation** on which checkpoint outcome to pick:
   - **(a) Proceed full-scope.** Discovery surfaced no major blockers; phone-local works reliably across the device range. v0.5.0 implements as planned.
   - **(b) Proceed narrow-scope.** Phone-local works on some devices/Android versions but not others. v0.5.0 ships with documented limitations and a clear list of supported configurations.
   - **(c) Defer.** Phone-local has hard blockers we cannot work around without root or device-specific code. v1.0 ships with Drive only.

The recommendation is then discussed and the actual decision is made — this discovery doc captures the analysis, not the final decision.

## Process

The v0.4.0 cycle is structured as:

1. **Day 1**: Q1–Q3 (which targets exist, where they write, what's accessible). Output: a list of viable candidates.
2. **Day 2**: Q4–Q6 (do they work for real exports). Output: a chosen target and a working prototype.
3. **Day 3**: Q7–Q10 + write up findings + checkpoint recommendation.

This is a rough estimate. The cycle is research, so it may go faster or slower. The hard deadline is the next minor version.

## Tools needed

- Primary test device with USB debugging and the latest WhatsApp version installed.
- A secondary test device (different manufacturer if possible — even just an emulator or a borrowed device).
- ADB tools available on the host.
- Appium running (for automating the share sheet taps).
- This document, updated in real time as findings arrive.

## Success criteria for v0.4.0

The v0.4.0 release is considered successful when:

1. All Q1–Q10 answers are filled in for the primary test device.
2. A working prototype exists and is committed to a branch (or to a discovery folder in the repo).
3. A clear (a)/(b)/(c) recommendation is documented in this file.
4. The recommendation has been reviewed and the v0.5.0 scope locked accordingly.

## Out of scope (will NOT be done in v0.4.0)

- Production-quality implementation of phone-local export (that's v0.5.0).
- TUI work (also v0.5.0).
- Source picker design (also v0.5.0).
- Documentation for end users (v0.7.0).
- Any work on devices we don't physically have access to.

## References

- Roadmap: `docs/plans/2026-04-08-001-feat-v1.0.0-public-release-roadmap.md`
- v0.3.0 plan: `docs/plans/2026-04-08-002-feat-v0.3.0-drive-integration-plan.md`
- Existing chat export driver: `whatsapp_chat_autoexport/export/chat_exporter.py:798`
- Existing WhatsApp driver (for ADB primitives): `whatsapp_chat_autoexport/export/whatsapp_driver.py`
- WhatsApp version handling (planned for v0.3.0): see v0.3.0 plan task T1.2
