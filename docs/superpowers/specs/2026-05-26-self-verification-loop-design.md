# Agent Self-Verification Loop — Design

> Status: approved (design phase). Date: 2026-05-26.
> Deliverables: a working self-verification loop against a real Android device, a `TESTING.md` context note at repo root, and an `AGENTS.md` reference to it.

## Problem

There is no way for a coding agent to verify its own changes against real hardware. The
device-touching tests (`@pytest.mark.requires_device`) are skipped in CI and run manually,
and the export flow only proves out when a human babysits a phone. We want a loop where the
agent can drive the real phone over Wi-Fi ADB and drive/observe the app, closing the dev
loop without supervision for the cheap layers and with a deliberate on-demand capstone for
the expensive one.

## Goal

A layered self-verification loop the agent runs while developing:

- Cheap, safe, read-only layers run every iteration unattended.
- An end-to-end real export ("capstone") runs on-demand only.
- The **CLI/headless path is the priority and the gate**; the **TUI path is built on top**
  and only verified once the CLI loop is green.

Non-goals: CI wiring (these layers are device-gated and manual by nature), new pytest
infrastructure beyond the existing `requires_device` marker, any abstraction layer over ADB
or cmux, or chat-selection machinery.

## The two-halves model

The loop has two independently-provable halves that meet at the device:

- **Half A — Device control (via `/android-adb`).** Raw `adb`: `pair`/`connect`,
  `screencap`, `uiautomator dump`, `wm size`, lock-state detection. Independent of the app.
- **Half B — App drive/observe.** For the CLI path: run the real `whatsapp --headless`
  binary and read its output. For the TUI path: Textual `run_test()` pilot, in-process,
  deterministic.

The key property that makes this *self-verification* and not just two test suites:
**Half A is the out-of-band oracle for Half B.** When the app claims "connected to device X"
or "export complete," the agent independently confirms via `adb devices`, `screencap`, and
`uiautomator dump`. The app cannot lie, because the agent has a direct channel to the
hardware.

```
AGENT (process on the Mac)
  Half A: DEVICE CONTROL (/android-adb)      Half B: APP DRIVE/OBSERVE
    adb connect/pair                           CLI: run `whatsapp --headless`, read output
    screencap / uiautomator dump               TUI: app.run_test() pilot, assert, snapshot
    wm size / lock state
        |                                            |
        v                                            v
   Real phone (Wi-Fi ADB) <----- Appium :4723 ----- WhatsAppDriver / ChatExporter
   WhatsApp + Google Drive
```

## Two parallel paths

The app exposes two entry paths over the same `WhatsAppDriver` + `ChatExporter`:

- **Path 1 — Headless CLI** (`whatsapp --headless`): non-interactive orchestrator.
  **Priority. The gate.**
- **Path 2 — TUI** (`whatsapp`, Textual): interactive. **Built on top, verified only after
  the CLI loop is solid.**

## Layers

| Phase | # | Layer | Path | Proves | Repeatable | Touches |
|-------|---|-------|------|--------|-----------|---------|
| Foundation | **L0** | ADB reachability | — | `adb pair`/`connect`, `screencap`, UI dump, `wm size`, lock state | every cycle | device (read-only) |
| CLI (priority) | **C1** | Headless launch + discovery | CLI | `whatsapp --headless` connects to the live Wi-Fi device — verified out-of-band via L0 | every cycle | device (read-only) + Appium session |
| CLI (priority) | **C2** | Headless full export capstone | CLI | end-to-end CLI export to Drive, chat at known position, safety gate mandatory | on-demand only | WhatsApp, Drive, real data |
| TUI (after CLI green) | **T1** | TUI pilot drive | TUI | `run_test()` pilot navigates screens, asserts widget state, snapshots | every cycle | nothing (in-process) |
| TUI (after CLI green) | **T2** | TUI live discovery | TUI | TUI discovery screen connects to real device — verified via L0 | every cycle | device (read-only) + Appium session |
| TUI (after CLI green) | **T3** | TUI full export capstone | TUI | TUI-driven end-to-end export, safety gate mandatory | on-demand only | WhatsApp, Drive, real data |

**The gate is explicit:** T1–T3 do not begin until **L0 + C1 + C2 are green**.

**The repeatable loop** is L0 + C1 (then later + T1 + T2): fast, safe, read-only against the
device. **The capstones** (C2, T3) are deliberate on-demand runs, never unattended.

## Execution surface — cmux

The agent must not clobber its own session by running long-lived processes in its main tool
shell. Instead:

- Spin up a **dedicated cmux pane** (`cmux new-split` / `cmux new-workspace`) as the
  execution surface. Long-running processes — `whatsapp --headless`, the Appium server, a
  live TUI — run **there**, so the main session stays responsive and the user can watch.
- **CLI layers (C1/C2):** run the actual `whatsapp --headless` binary in the cmux pane
  (takeover), drive via its real args/stdin, read its output. There is no Textual pilot on
  the CLI path — the headless orchestrator is a real process, driven and observed as one.
  The ADB oracle (L0) runs from the agent's tool shell in parallel to confirm device state.
- **TUI layers (T1):** Textual `run_test()` pilot, in-process, deterministic — the scriptable
  driver. For **T2/T3**, the live TUI runs in the cmux pane when a human-watchable run is
  wanted.

## Evidence

Each layer writes a timestamped artifact into a **gitignored `test-evidence/`** directory so
a run is reviewable after the fact:

- ADB screenshots (`screencap`) and `uiautomator` XML dumps (Half A oracle records).
- Captured CLI stdout/stderr for C1/C2.
- Pilot snapshots / asserted screen state for T1.

## Device connection (one-time)

The phone needs **full Wi-Fi pairing** (wireless debugging not yet paired). This is an
interactive one-time step performed during the proof: the user reads the pairing code/port
from the phone's Developer Options, the agent runs `adb pair <ip>:<port>` then
`adb connect <ip>:<port>`, and confirms the device appears in `adb devices`. Subsequent runs
only need `adb connect`.

## Safety

- The capstone exports drive **real WhatsApp exports of real chats to real Google Drive**
  via blind UI automation. The existing `verify_whatsapp_is_open()` CRITICAL safety gate is
  **mandatory** before any export action and is documented as such in TESTING.md.
- Capstone targets a chat **by known position** in the chat list. This is the simplest to
  script and acceptable on the user's own device with the user present, but it is the
  riskiest targeting strategy: position changes break it and it could land on a sensitive
  chat. TESTING.md must call this out explicitly and instruct the runner to confirm the
  target chat before triggering an export.
- Capstones (C2, T3) are **on-demand only** — never part of an unattended loop.

## Deliverables

1. A demonstrably-working loop: L0, C1, C2 proven against the real device this session; T1–T3
   proven after the CLI path is green.
2. **`TESTING.md`** at repo root documenting L0 → C1 → C2 → T1 → T2 → T3 as copy-pasteable
   recipes: prerequisites, exact commands, expected output, the out-of-band verification
   step, and the safety gate.
3. An **`AGENTS.md`** `## Testing` reference pointing to `TESTING.md`.
4. `test-evidence/` added to `.gitignore`.

## Open risks

- **Position-based targeting** (see Safety) — accepted, documented, mitigated by mandatory
  confirmation + safety gate.
- **Appium/device flakiness** — wireless ADB exec timeouts are already tuned higher (120s) in
  the driver; the loop inherits the driver's `safe_driver_call()` retry/reconnect behavior.
- **cmux pane lifecycle** — panes must be cleaned up or reused across runs; TESTING.md
  documents the pane setup/teardown.
