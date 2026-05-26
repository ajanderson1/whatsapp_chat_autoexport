# Testing

Two kinds of testing live here:

1. **Standard suite** — `uv run pytest` (unit + integration, no device). See
   `docs/internals/architecture.md` for the full strategy.
2. **Self-verification loop** — layered checks an agent (or you) runs against a
   **real Android device** over Wi-Fi ADB. Documented below.

Design: `docs/superpowers/specs/2026-05-26-self-verification-loop-design.md`.
Plan: `docs/superpowers/plans/2026-05-26-self-verification-loop.md`.

## Self-verification loop

A coding agent verifies its own changes against real hardware using **two halves
that meet at the device**:

- **Half A — device control (raw `adb`):** reach and read the phone. This is the
  out-of-band **oracle** — it confirms what the app *claims* actually happened.
- **Half B — the app:** the headless CLI (a real process) and the TUI (Textual
  `run_test()` pilot).

The property that makes this self-verification and not just two test suites:
**Half A is the oracle for Half B.** When the app says "connected" or "export
complete," you confirm it independently with `adb devices` + `screencap`. The app
cannot lie, because you have a direct channel to the hardware.

Layers run **CLI-first**. `L0 + C1 + C2` must be green before the TUI layers.
`L0/C1/T1/T2` are safe to repeat every iteration; `C2/T3` are **on-demand only —
never unattended** (they drive a real export of a real chat to real Drive).

Evidence (screenshots, UI dumps, captured logs) lands in the gitignored
`test-evidence/` directory.

### Prerequisites

- `adb` on PATH (Android platform-tools). Verified with `adb version`.
- Appium reachable on `127.0.0.1:4723`. In `--headless` mode the app's
  `AppiumManager` starts and stops its own Appium server; for the standalone C1
  harness, start one yourself: `appium server --address 127.0.0.1 --port 4723`.
- Phone with Wireless debugging enabled, or a USB-connected authorized device you
  promote to Wi-Fi (see L0).
- Google Drive credentials in `~/.whatsapp_export/` (`client_secrets.json` +
  `google_credentials.json`) for the C2 export capstone. Not needed for L0/C1.
- Run long-lived processes (headless CLI, live TUI) so they don't block your main
  session; run the ADB oracle from a separate shell.

### Realtime watch (optional)

Stream activity to a log and watch it colourised with `grc`:

```bash
# In the working shell, append timestamped lines to test-evidence/activity.log
# In a second pane:
tail -F test-evidence/activity.log | grcat scripts/selfverify_activity.grc
```

`scripts/selfverify_activity.grc` colours OK/passed green, errors red,
safety-gate/warnings yellow, oracle/adb actions cyan, phase markers magenta.

---

### L0 — ADB reachability (the oracle)

Proves Half A: you can reach and read the real phone. **Repeatable.**

If the device is connected over USB and authorised, promote it to Wi-Fi (no
pairing code needed — USB authorisation carries over):

```bash
adb devices -l                      # find the USB serial + confirm "device" state
adb -s <USB_SERIAL> shell ip addr show wlan0 | grep "inet "   # phone Wi-Fi IP
adb -s <USB_SERIAL> tcpip 5555
adb connect <PHONE_IP>:5555
adb devices -l                      # now shows <PHONE_IP>:5555  device
```

> **Gotcha (observed):** after `tcpip`, `adb connect` can report
> `failed to connect ... No route to host` even when the port is open (verify with
> `nc -z <PHONE_IP> 5555`). The cause is a stale adb server, not the network. Fix:
> `adb kill-server && adb start-server`, then `adb connect` again.

For a cold device with no USB, use full wireless pairing instead: enable
**Developer options → Wireless debugging → Pair device with pairing code**, then
`adb pair <PAIR_IP>:<PAIR_PORT> <CODE>` followed by `adb connect <CONN_IP>:<CONN_PORT>`.

Read device state and capture oracle evidence:

```bash
SERIAL=<PHONE_IP>:5555
adb -s "$SERIAL" shell wm size                                   # e.g. Physical size: 1080x2410
adb -s "$SERIAL" shell dumpsys window | grep mCurrentFocus       # foreground app
TS=$(date +%Y%m%d-%H%M%S)
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/L0-$TS-screen.png"
adb -s "$SERIAL" shell uiautomator dump /sdcard/l0.xml && \
  adb -s "$SERIAL" pull /sdcard/l0.xml "test-evidence/L0-$TS-ui.xml"
```

**L0 is proven** when `adb devices -l` shows `device` and the screenshot renders
the phone's live screen.

---

### C1 — headless connect-verify (repeatable)

Proves the agent can run the **driver's real connection path**
(`check_device_connection()` → `connect()`) and stop before any export. Uses the
standalone harness `scripts/selfverify_connect.py`.

Prerequisites: Appium running (`appium server --address 127.0.0.1 --port 4723`),
the phone **unlocked with WhatsApp open** on the chat list. (If WhatsApp isn't
foregrounded, launch it: `adb -s "$SERIAL" shell monkey -p com.whatsapp -c android.intent.category.LAUNCHER 1`.)

```bash
uv run python -m scripts.selfverify_connect --wireless-adb <PHONE_IP>:5555
```

Expected (exit 0):

```
Driver connected successfully!
WhatsApp auto-launched successfully
✅ VERIFICATION PASSED: WhatsApp is open and accessible
C1 OK: connected to device <SERIAL>
✓ Restored 2 device setting(s) to original values
Driver session closed
```

The run exercises the driver's `verify_whatsapp_is_open()` safety gate — it
confirms package `com.whatsapp`, a safe activity, and that the phone is unlocked
before reporting success.

**Confirm out-of-band (the oracle):** from a *separate* shell, while/after the run:

```bash
adb devices -l                                                   # <SERIAL> = device
adb -s "$SERIAL" shell dumpsys window | grep mCurrentFocus       # com.whatsapp/.home.ui.HomeActivity
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/C1-$(date +%H%M%S)-oracle.png"
```

**C1 is proven** when the harness exits 0 and the oracle shows WhatsApp
foregrounded — the harness's claim matches the hardware.

> **Note:** the harness must build the project's `whatsapp_chat_autoexport.utils.logger.Logger`
> (it has `debug_msg`, `step`, `success`, …), exactly as `headless.py` does — *not*
> a stdlib `logging.Logger`. Passing a stdlib logger crashes the driver on its first
> `self.logger.debug_msg(...)` call. The unit test
> `test_build_driver_passes_project_logger_with_debug_msg` pins this contract.

---

### C2 — headless export capstone (ON-DEMAND ONLY)

> ⚠️ **This drives a REAL export of a REAL chat to REAL Google Drive.** Never run
> unattended. It targets the chat **at the top of the list** (`--limit 1` +
> `--auto-select`, list order). **Confirm the top chat is safe to export before
> running** — pin a low-stakes chat (self-chat / test group / archived chat) to the
> top first (long-press → pin). The driver's `verify_whatsapp_is_open()` gate must
> pass; if the phone is locked or WhatsApp isn't foregrounded, the run refuses —
> that refusal is the safety net.

Pre-flight the target with the oracle (do NOT skip this):

```bash
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/C2-pretarget-$(date +%H%M%S).png"
# Open the screenshot and confirm the TOP chat is the one you intend to export.
```

Run the bounded capstone:

```bash
mkdir -p test-evidence/C2-output
uv run whatsapp --headless --wireless-adb <PHONE_IP>:5555 \
  --auto-select --limit 1 --no-transcribe \
  --output test-evidence/C2-output
```

`--limit 1` bounds it to the single top chat (`headless.py` calls
`collect_all_chats(limit=limit, sort_alphabetical=False)`, so list order is used).
`--no-transcribe` skips Whisper/ElevenLabs (no API keys needed).

Expected tail (exit 0):

```
📤 EXPORTING CHAT: '<chat>' (with media)
STEP 5: Selecting 'Drive' (Google Drive)...
STEP 6: Clicking 'Upload' button in Google Drive window...
Export Summary
Total chats:  1
Succeeded:    1
Failed:       0
Output:       test-evidence/C2-output
```

**Confirm out-of-band during the run:** capture screenshots while it drives the UI.
The oracle should show WhatsApp's export menu and then Google Drive's upload sheet
(`com.google.android.apps.docs/...UploadMenuActivity`, "Upload to Drive — WhatsApp
Chat with <chat>"):

```bash
adb -s "$SERIAL" shell dumpsys window | grep mCurrentFocus
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/C2-run-$(date +%H%M%S).png"
```

**C2 is proven** when the export completes (Succeeded: 1), the oracle screenshots
corroborate the on-device export→Drive flow, and `test-evidence/C2-output/<chat>/`
contains the built output (`index.md` + `transcript.md`).

> **`--skip-drive-download` does NOT skip the download in `--headless` mode.** It is
> read only for the preflight Drive-capacity check (`headless.py:330`,
> `run_preflight(skip_drive=...)`); the headless export pipeline still uploads to
> Drive, polls, downloads, and builds output regardless. The flag honours "skip
> download" only in the legacy `process` / `--pipeline-only` paths
> (`legacy/cli/commands/process.py:149`). So a `--headless` capstone always runs the
> full export→upload→poll→download→process flow and produces local output. (Latent
> flag-wiring asymmetry; out of scope for the loop work.)

> **A chat that looks trivial in the list can be large.** The list preview shows
> only the last message; the capstone export of a chat that previewed as a single
> "Hello" actually contained 109 messages and 12 media files. Factor this into the
> "is the top chat safe to export" judgement.

---

### T1 — TUI pilot drive (repeatable)

Proves Half B for the TUI: drive the real app object in-process via Textual's
`run_test()` pilot, assert on screen state, capture a rendered snapshot. No device.

```bash
uv run pytest tests/integration/test_selfverify_tui.py -v
```

Expected: 2 passed. One test asserts the app reaches `MainScreen`; the other
captures a rendered SVG snapshot via `app.export_screenshot()`.

---

### T2 — TUI live discovery (repeatable, on-device) — NOT YET EXECUTED

Procedure (run once to capture real output, then update this section): launch the
TUI so it's watchable, point its Connect/Discover tab at the live Wi-Fi device, and
confirm connection out-of-band via L0.

```bash
uv run whatsapp        # launch the TUI; on the Connect/Discover tab, discover the
                       # wireless device <PHONE_IP>:5555 and connect
# In a separate shell, confirm the device the TUI shows matches the oracle:
adb devices -l
adb -s "$SERIAL" exec-out screencap -p > "test-evidence/T2-$(date +%H%M%S)-oracle.png"
```

**T2 is proven** when the TUI reports the same connected device the oracle sees.

---

### T3 — TUI export capstone (ON-DEMAND ONLY) — NOT YET EXECUTED

> ⚠️ Same real-data warning as C2. Pin a safe chat to the top; confirm with the
> oracle first; the `verify_whatsapp_is_open()` gate is mandatory.

Procedure: from the live TUI, select chats and trigger an export; confirm the
on-device export→Drive flow via the L0 oracle. Update this section with captured
output once executed.

---

### Safety summary

- Capstones (C2, T3) are **on-demand only** — never part of an unattended loop.
- **Top-of-list targeting is the simplest and the riskiest.** Always confirm the
  target chat with the oracle before exporting, and remember a small-looking chat
  can hold a large history.
- `verify_whatsapp_is_open()` is mandatory and must never be bypassed — its refusal
  to act when the phone is locked or WhatsApp isn't foregrounded is the safety net,
  not a bug.
