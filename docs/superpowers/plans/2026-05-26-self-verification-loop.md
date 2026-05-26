# Agent Self-Verification Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up and prove a layered self-verification loop where a coding agent drives a real Android device over Wi-Fi ADB (out-of-band oracle) and drives/observes the app (CLI first, TUI second), then document every proven layer in `TESTING.md`.

**Architecture:** Two halves meet at the device. Half A is raw `adb` (reach + read the phone). Half B is the app (headless CLI as a real process; TUI via Textual `run_test()` pilot). Half A is the oracle that confirms Half B's claims. Layers run CLI-first: `L0` ADB reachability → `C1` headless connect-verify → `C2` headless export capstone (gate), then `T1`/`T2`/`T3` for the TUI. Long-running processes run in a dedicated cmux pane; the ADB oracle runs from the agent's tool shell. Each layer drops timestamped evidence into a gitignored `test-evidence/`.

**Tech Stack:** Python 3.13, `adb` (Android platform-tools), Appium + UiAutomator2 (already in the driver), Textual `run_test()` pilot, cmux for the execution surface. The unified `whatsapp` CLI (`--headless`, `--wireless-adb`, `--auto-select`, `--limit`, `--skip-drive-download`, `--no-transcribe`).

**Nature of this plan:** This is a verification-and-documentation deliverable, not a feature build. Most "tests" are real-device observations. Some steps are **human-in-the-loop (HITL)** — they need the user to read a code off the phone or confirm a target. Those are marked **[HITL]**. The plan produces two committed artifacts (the C1 connect-verify harness script + `TESTING.md`) and proves the live layers.

---

## File structure

| Path | Responsibility | Created/Modified |
|------|----------------|------------------|
| `.gitignore` | Ignore `test-evidence/` | Modify |
| `scripts/selfverify_connect.py` | C1 primitive: connect to device via `WhatsAppDriver`, print connected device, exit before any export. Reused by the loop. | Create |
| `TESTING.md` | Repo-root context note documenting L0→C1→C2→T1→T2→T3 as copy-pasteable recipes. | Create |
| `AGENTS.md` | Add a `## Testing` section pointing to `TESTING.md`. | Modify |
| `test-evidence/` | Gitignored evidence dir (screenshots, UI dumps, captured output). Created at runtime, never committed. | Runtime only |

---

## Task 1: Evidence directory + gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `test-evidence/` to `.gitignore`**

Append to `.gitignore`:

```gitignore

# Self-verification loop evidence (screenshots, UI dumps, captured CLI output)
test-evidence/
```

- [ ] **Step 2: Verify it's ignored**

Run: `mkdir -p test-evidence && touch test-evidence/probe && git status --short test-evidence/`
Expected: no output (directory is ignored, `probe` not shown).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore(testing): gitignore test-evidence/ for self-verification loop"
```

---

## Task 2: L0 — ADB reachability (live device, HITL pairing)

Proves Half A: the agent can pair, connect, and read the real phone. This is the out-of-band oracle for every later layer. **Runs every loop iteration once paired.**

**Files:** none created — this task proves a procedure and captures evidence. The proven commands are written into `TESTING.md` in Task 7.

- [ ] **Step 1: Confirm adb is present**

Run: `adb version`
Expected: prints `Android Debug Bridge version ...`. If missing, stop and install platform-tools.

- [ ] **Step 2: [HITL] Pair over Wi-Fi**

Ask the user to open the phone: **Developer options → Wireless debugging → Pair device with pairing code**. They read out the **pairing `IP:PORT`** and the **6-digit code**. Then run:

Run: `adb pair <PAIR_IP>:<PAIR_PORT> <CODE>`
Expected: `Successfully paired to <PAIR_IP>:<PAIR_PORT> ...`

- [ ] **Step 3: [HITL] Connect over Wi-Fi**

The Wireless debugging main screen shows a *different* `IP:PORT` (the connect address). Ask the user for it, then run:

Run: `adb connect <CONN_IP>:<CONN_PORT>`
Expected: `connected to <CONN_IP>:<CONN_PORT>`

- [ ] **Step 4: Confirm device is visible and online**

Run: `adb devices -l`
Expected: a line containing `<CONN_IP>:<CONN_PORT>   device` (state `device`, not `offline`/`unauthorized`). Record this serial — it is `$SERIAL` for all later steps.

- [ ] **Step 5: Read device state (oracle baseline)**

Run:
```bash
adb -s "$SERIAL" shell wm size
adb -s "$SERIAL" shell dumpsys window | grep -E 'mCurrentFocus'
```
Expected: a resolution line (e.g. `Physical size: 1080x2400`) and the current foreground app focus.

- [ ] **Step 6: Capture evidence (screenshot + UI dump)**

Run:
```bash
TS=$(date +%Y%m%d-%H%M%S)
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/L0-$TS-screen.png"
adb -s "$SERIAL" shell uiautomator dump /sdcard/l0.xml && adb -s "$SERIAL" pull /sdcard/l0.xml "test-evidence/L0-$TS-ui.xml"
ls -la test-evidence/
```
Expected: a non-zero-byte PNG and an XML file in `test-evidence/`.

- [ ] **Step 7: Confirm with the user**

Show the user the screenshot path and the foreground-app line. **L0 is proven** when `adb devices -l` shows `device` and the screenshot renders the phone's current screen. No commit (no code changed yet — evidence is gitignored).

---

## Task 3: C1 connect-verify harness (TDD)

The C1 primitive: a script that runs the driver's real connection path (`check_device_connection()` → `connect()`) and exits **before** any export. This is the repeatable CLI-loop layer. Built test-first against a mocked driver so the harness logic is correct independent of hardware.

**Files:**
- Create: `scripts/selfverify_connect.py`
- Test: `tests/integration/test_selfverify_connect.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_selfverify_connect.py`:

```python
"""Tests for the C1 connect-verify harness (scripts/selfverify_connect.py).

The harness must exercise the driver's real connection path and STOP before
any export. We mock WhatsAppDriver so this runs without a device.
"""
from unittest.mock import MagicMock, patch

import pytest

from scripts.selfverify_connect import connect_and_verify


@pytest.mark.integration
def test_connect_and_verify_returns_zero_and_never_exports():
    driver = MagicMock()
    driver.check_device_connection.return_value = True
    driver.connect.return_value = True
    driver.device_id = "192.168.1.50:5555"

    rc = connect_and_verify(driver)

    assert rc == 0
    driver.check_device_connection.assert_called_once()
    driver.connect.assert_called_once()
    # The whole point of C1: it must never trigger an export.
    assert not hasattr(driver, "export_chats") or not driver.export_chats.called


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_device_absent():
    driver = MagicMock()
    driver.check_device_connection.return_value = False

    rc = connect_and_verify(driver)

    assert rc != 0
    driver.connect.assert_not_called()


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_connect_fails():
    driver = MagicMock()
    driver.check_device_connection.return_value = True
    driver.connect.return_value = False

    rc = connect_and_verify(driver)

    assert rc != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_selfverify_connect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.selfverify_connect'` (or import error).

- [ ] **Step 3: Write minimal implementation**

Create `scripts/__init__.py` (empty file, so `scripts` is importable as a package):

```python
```

Create `scripts/selfverify_connect.py`:

```python
"""C1 self-verification primitive: connect to the device, verify, exit.

Exercises the exact connection path used by headless export
(WhatsAppDriver.check_device_connection -> connect) and STOPS before any
export. Run this in the cmux pane during the self-verification loop; confirm
its claims out-of-band with `adb devices` / screencap (L0 oracle).

Usage:
    uv run python -m scripts.selfverify_connect [--wireless-adb IP:PORT]
"""
from __future__ import annotations

import argparse
import logging
import sys
from logging import Logger


def connect_and_verify(driver) -> int:
    """Run the driver's connection path and return a shell exit code.

    Returns 0 on a verified connection, non-zero otherwise. Never exports.
    """
    if not driver.check_device_connection():
        return 2
    if not driver.connect():
        return 3
    print(f"C1 OK: connected to device {driver.device_id}")
    return 0


def _build_driver(args: argparse.Namespace, logger: Logger):
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

    return WhatsAppDriver(logger=logger, wireless_adb=args.wireless_adb)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C1 connect-verify harness")
    parser.add_argument(
        "--wireless-adb",
        nargs="?",
        const=True,
        default=None,
        metavar="IP:PORT",
        help="Use wireless ADB (optionally IP:PORT)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger = logging.getLogger("selfverify_connect")

    driver = _build_driver(args, logger)
    try:
        return connect_and_verify(driver)
    finally:
        disconnect = getattr(driver, "disconnect", None)
        if callable(disconnect):
            disconnect()


if __name__ == "__main__":
    sys.exit(main())
```

> **Note for implementer:** Verify the `WhatsAppDriver.__init__` signature in `whatsapp_chat_autoexport/export/whatsapp_driver.py` before finalizing `_build_driver`. The constructor takes a logger and wireless-ADB configuration; adjust the keyword names in `_build_driver` to match the actual signature (the harness logic in `connect_and_verify` is what the tests pin, and it is signature-independent). If `disconnect` is not the teardown method name, match the real one.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_selfverify_connect.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check scripts/ tests/integration/test_selfverify_connect.py && uv run ruff format scripts/ tests/integration/test_selfverify_connect.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/selfverify_connect.py tests/integration/test_selfverify_connect.py
git commit -m "feat(testing): C1 connect-verify harness for self-verification loop"
```

---

## Task 4: C1 — prove headless connect against the live device (cmux pane)

Run the C1 primitive against the real phone in a dedicated cmux pane, confirm out-of-band via L0. **Repeatable loop layer.** Requires L0 (Task 2) green and Appium reachable.

**Files:** none — proves a procedure, captures evidence (written into TESTING.md in Task 7).

- [ ] **Step 1: Create the cmux execution pane**

Run: `cmux new-split right --panel pane:1` (or `cmux new-workspace`). Record the new `surface:N` / `pane:N`. This pane is the execution surface for all live runs.

- [ ] **Step 2: Ensure Appium is running**

In the cmux pane (or let `AppiumManager` start it): confirm `curl -s http://127.0.0.1:4723/status` returns JSON with `"ready"`. If not running, start it: `appium` (the driver's `AppiumManager` also auto-starts it).

- [ ] **Step 3: [HITL] Confirm WhatsApp is open + unlocked**

Connection verification in the driver expects the phone reachable. Ask the user to unlock the phone and open WhatsApp to the chat list (the driver's safety gate checks this on the export path; for C1 we just need the device reachable, but an unlocked phone makes the oracle screenshot meaningful).

- [ ] **Step 4: Run C1 in the cmux pane, capture output**

In the cmux pane run:
```bash
uv run python -m scripts.selfverify_connect --wireless-adb 2>&1 | tee "test-evidence/C1-$(date +%Y%m%d-%H%M%S).log"
```
Expected: exit 0 and a line `C1 OK: connected to device <SERIAL>`.

- [ ] **Step 5: Confirm out-of-band (the oracle)**

From the agent's tool shell (NOT the cmux pane), independently confirm the device the harness claimed:
```bash
adb devices -l
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/C1-$(date +%Y%m%d-%H%M%S)-oracle.png"
```
Expected: `$SERIAL` shows state `device`; screenshot shows WhatsApp. **C1 is proven** when the harness's claimed device matches the ADB oracle.

- [ ] **Step 6: Confirm with user, no commit (evidence gitignored)**

---

## Task 5: C2 — headless full export capstone (live, on-demand, HITL)

The end-to-end CLI proof: `whatsapp --headless` drives a real export. **On-demand only — never unattended.** Gated behind L0 + C1 green. Bounded to a single chat with the pipeline trimmed so the proof is fast and the blast radius small. The `verify_whatsapp_is_open()` safety gate is mandatory and lives inside the driver.

**Files:** none — proves a procedure, captures evidence (written into TESTING.md in Task 7).

- [ ] **Step 1: [HITL] Confirm the target chat by position**

The capstone exports a chat **by its position in the list** (per design — simplest to script, riskiest). Ask the user to confirm the chat at the top position (position 1) is **safe to export** (a self-chat / test group / archived chat is ideal). The user must explicitly confirm before proceeding. If position 1 is sensitive, the user moves a safe chat to the top or aborts.

- [ ] **Step 2: [HITL] Confirm phone unlocked + WhatsApp on chat list**

Ask the user to unlock the phone and leave WhatsApp on the main chat list. The driver's `verify_whatsapp_is_open()` gate will refuse to proceed otherwise — that refusal is the safety net, not a bug.

- [ ] **Step 3: Run the bounded capstone in the cmux pane**

In the cmux pane:
```bash
mkdir -p test-evidence/C2-output
uv run whatsapp --headless \
  --wireless-adb \
  --auto-select \
  --limit 1 \
  --skip-drive-download \
  --no-transcribe \
  --output test-evidence/C2-output \
  2>&1 | tee "test-evidence/C2-$(date +%Y%m%d-%H%M%S).log"
```
Expected: the orchestrator runs preflight, connects, and drives the WhatsApp UI to trigger **one** chat export to Drive. `--limit 1` bounds it to a single chat. Exit code 0 means success.

> **Corrected during execution (2026-05-26):** `--skip-drive-download` is a **no-op on the `--headless` path** — `run_headless` runs the full pipeline (download/process); the flag is only read for the preflight Drive check (`headless.py:330`) and honored in the legacy `process` / `--pipeline-only` paths. So the headless capstone always runs export→upload→poll→download→process and produces local `index.md`/`transcript.md`. `--limit 1` and `--no-transcribe` are the effective bounds. The flag was dropped from the TESTING.md command since it does nothing here. See `TESTING.md` § C2.

> **Note for implementer:** Confirm `--limit` is honored on the headless path and that `--auto-select --limit 1` exports exactly one chat (read `run_headless` in `whatsapp_chat_autoexport/headless.py` and `export_chats` in the exporter). If `--limit` is not wired to headless, fall back to documenting the smallest available real export and note the limitation in TESTING.md. Do not invent a flag.

- [ ] **Step 4: Confirm out-of-band during the run (oracle)**

While the export runs, from the agent tool shell capture what the phone is actually doing:
```bash
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/C2-$(date +%Y%m%d-%H%M%S)-oracle.png"
adb -s "$SERIAL" shell dumpsys window | grep mCurrentFocus
```
Expected: screenshots show WhatsApp driving the export menu / Drive share sheet — confirming the CLI's claims correspond to real on-device actions.

- [ ] **Step 5: Confirm the export landed**

Confirm the chat was exported to Drive (the user checks Drive, or the log shows the Drive upload step succeeded). **C2 is proven** when the bounded export completes with exit 0 and the oracle screenshots corroborate the on-device flow.

- [ ] **Step 6: Confirm with user. CLI GATE PASSED — TUI layers (Tasks 8+) may now begin.**

No commit (evidence gitignored).

---

## Task 6: T1 — TUI pilot drive (TDD-style, in-process)

Proves Half B for the TUI: the agent can launch the app via `run_test()`, navigate tabs, and assert on screen state — the deterministic scriptable driver. Follows the existing pattern in `tests/integration/test_textual_tui.py`. **Repeatable loop layer.** Gated behind the CLI gate (Task 5).

**Files:**
- Test: `tests/integration/test_selfverify_tui.py`

- [ ] **Step 1: Write the pilot test**

Create `tests/integration/test_selfverify_tui.py`:

```python
"""T1 self-verification: drive the real app object via Textual's pilot.

Proves the agent can launch the TUI in-process, navigate, and assert on
screen state deterministically. Mirrors tests/integration/test_textual_tui.py.
"""
import pytest

from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selfverify_tui_launches_and_navigates(tui_app):
    """The loop can launch the TUI and confirm it reaches MainScreen."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(tui_app.screen, MainScreen)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selfverify_tui_snapshot_captures_screen(tui_app, tmp_path):
    """The loop can capture a rendered snapshot as evidence."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        snapshot = tui_app.export_screenshot()  # Textual SVG export
        out = tmp_path / "t1-snapshot.svg"
        out.write_text(snapshot)
        assert out.stat().st_size > 0
```

> **Note for implementer:** Confirm the `tui_app` fixture exists in `tests/conftest.py` (the brief says it does) and that `export_screenshot()` is the current Textual API for capturing a frame (it returns an SVG string in recent Textual). If the method name differs in the installed Textual version, use the correct one (e.g. `save_screenshot`); the assertion just needs a non-empty captured frame.

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_selfverify_tui.py -v`
Expected: PASS (2 passed). If the snapshot API name is wrong, fix per the note and re-run.

- [ ] **Step 3: Lint + format**

Run: `uv run ruff check tests/integration/test_selfverify_tui.py && uv run ruff format tests/integration/test_selfverify_tui.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_selfverify_tui.py
git commit -m "test(testing): T1 TUI pilot drive for self-verification loop"
```

---

## Task 7: Write TESTING.md (all proven layers)

Document every layer proven in Tasks 2–6 (and the on-demand T2/T3 capstone procedures) as copy-pasteable recipes. Written only after the layers are actually run, so commands and expected output are real, not guessed.

**Files:**
- Create: `TESTING.md`

- [ ] **Step 1: Write `TESTING.md`**

Create `TESTING.md` at repo root with this structure (fill expected-output blocks with the *actual* output observed in Tasks 2–6):

```markdown
# Testing

Two kinds of testing live here:

1. **Standard suite** — `uv run pytest` (unit + integration, no device). See
   `docs/internals/architecture.md` for the full strategy.
2. **Self-verification loop** — layered checks an agent (or you) runs against a
   **real Android device** over Wi-Fi ADB. Documented below.

## Self-verification loop

A coding agent verifies its own changes against real hardware using two halves
that meet at the device:

- **Half A — device control (raw `adb`):** reach and read the phone. This is the
  out-of-band **oracle**: it confirms what the app claims actually happened.
- **Half B — the app:** the headless CLI (a real process) and the TUI (Textual
  `run_test()` pilot).

Layers run **CLI-first**. `L0 + C1 + C2` must be green before the TUI layers.
`L0/C1/T1/T2` are safe to repeat every loop iteration; `C2/T3` are **on-demand
only — never unattended** (they drive real exports of real chats to real Drive).

Evidence (screenshots, UI dumps, captured output) lands in the gitignored
`test-evidence/` directory.

### Prerequisites

- `adb` on PATH (Android platform-tools).
- Appium reachable on `127.0.0.1:4723` (the driver's `AppiumManager` auto-starts
  it; or run `appium`).
- Phone with Wireless debugging enabled.
- Run long-lived processes (headless CLI, live TUI) in a dedicated cmux pane so
  the main session stays responsive; run the ADB oracle from a separate shell.

### L0 — ADB reachability (oracle)

<paste the proven Task 2 commands: adb pair, adb connect, adb devices -l,
wm size, screencap + uiautomator dump. Include real expected output.>

### C1 — headless connect-verify (repeatable)

<paste the proven Task 4 command:
`uv run python -m scripts.selfverify_connect --wireless-adb`, expected
`C1 OK: connected to device <SERIAL>`, and the out-of-band oracle confirmation.>

### C2 — headless export capstone (ON-DEMAND ONLY)

> ⚠️ Drives a REAL export of a REAL chat to REAL Google Drive. Never run
> unattended. The capstone targets the chat **at position 1** in the list —
> confirm that chat is safe to export before running. The driver's
> `verify_whatsapp_is_open()` safety gate must pass; if the phone is locked or
> WhatsApp is not foregrounded, the run refuses — that is the safety net.

<paste the proven Task 5 bounded command and expected exit 0, plus the
oracle-during-run screenshots step.>

### T1 — TUI pilot drive (repeatable)

Run: `uv run pytest tests/integration/test_selfverify_tui.py -v`
Expected: PASS. This drives the real app object in-process and captures a
rendered snapshot.

### T2 — TUI live discovery (repeatable, on-device)

Launch the TUI in the cmux pane, point its discovery/connect tab at the live
Wi-Fi device, and confirm connection out-of-band via L0:

<document: launch `uv run whatsapp` in the cmux pane; on the Connect/Discover
tab trigger device discovery with the wireless device; confirm via
`adb devices -l` + screencap that the device the TUI shows matches the oracle.>

### T3 — TUI export capstone (ON-DEMAND ONLY)

> ⚠️ Same real-data warning as C2.

<document: from the live TUI in the cmux pane, select the position-1 chat and
trigger an export; confirm on-device via the L0 oracle; safety gate mandatory.>

### Safety summary

- Capstones (C2, T3) are on-demand only.
- Position-1 targeting is the simplest and the riskiest — always confirm the
  target chat before exporting.
- `verify_whatsapp_is_open()` is mandatory and must never be bypassed.
```

- [ ] **Step 2: Fill in real output**

Replace every `<paste ...>` / `<document ...>` placeholder with the actual commands and observed output from Tasks 2–6. T2/T3 are documented as procedures (run them once to capture real output if proceeding to the TUI capstone; otherwise document the steps clearly and mark them as not-yet-executed).

- [ ] **Step 3: Verify no placeholders remain**

Run: `grep -nE '<paste|<document|TODO|TBD' TESTING.md`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add TESTING.md
git commit -m "docs(testing): TESTING.md context note for self-verification loop"
```

---

## Task 8: Reference TESTING.md from AGENTS.md

**Files:**
- Modify: `AGENTS.md` (the canonical file; `CLAUDE.md` is a symlink → `AGENTS.md`, so editing `AGENTS.md` updates both).

- [ ] **Step 1: Add a Testing reference to AGENTS.md**

Insert a `## Testing` section after the `## Canonical commands` block in `AGENTS.md`:

```markdown
## Testing
- Standard suite: `uv run pytest` (no device).
- Self-verification loop against a real device (ADB oracle + CLI/TUI): see `TESTING.md`.
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(testing): reference TESTING.md from AGENTS.md"
```

---

## Task 9 (optional, on-demand): T2 + T3 TUI on-device layers

Only execute if proceeding past T1 to prove the TUI against the live device. T2 (discovery) is repeatable; T3 (export) is an on-demand capstone with the same safety rules as C2. These are documented as recipes in `TESTING.md` (Task 7); executing them means running those recipes and capturing evidence. No new files — the proof is the live run plus the evidence artifacts.

- [ ] **Step 1: T2 — launch TUI in cmux pane, drive discovery to the live device, confirm via L0 oracle.**
- [ ] **Step 2: T3 — [HITL] confirm position-1 chat safe; trigger export from the TUI; confirm on-device via oracle; safety gate mandatory.**
- [ ] **Step 3: Update `TESTING.md` T2/T3 sections with real captured output; commit.**

---

## Self-review notes

- **Spec coverage:** L0 (Task 2), C1 (Tasks 3–4), C2 (Task 5), T1 (Task 6), T2/T3 (Task 9), `TESTING.md` (Task 7), AGENTS.md reference (Task 8), `test-evidence/` gitignored (Task 1), cmux execution surface (Tasks 4–5), ADB-as-oracle (every live task's out-of-band step), CLI-first gate (explicit in Task 5 Step 6), position-targeting safety (Task 5 Step 1 + TESTING.md warnings). All spec sections map to a task.
- **HITL steps** are explicitly marked — pairing (Task 2), target-chat confirmation + unlock (Task 5), T3 confirmation (Task 9).
- **Implementer notes** flag the three real-codebase unknowns to verify rather than guess: `WhatsAppDriver` constructor signature (Task 3), `--limit` honored on headless (Task 5), Textual snapshot API name (Task 6). Each says "match the real thing, do not invent."
```
