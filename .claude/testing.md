---
version: 1
---

# Testing — WhatsApp Chat AutoExport

Read by `/aj-flow flow` Step 9 (Verify) and `/aj-flow review` Step 5 (Re-verify).
See `aj-flow/PREFERENCES.md` → "Per-project testing conventions" for the contract.

For human-friendly running instructions, see [`tests/README.md`](../tests/README.md).

## Tiers — what each one is for

| Tier | Where | Time budget | Catches | Doesn't catch |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | ~30s focused, ~3min full | Logic regressions, mode dispatch, parsers, output builders. Mocks device + Drive + transcription. | Real Appium / Drive / API behaviour, real Textual UI rendering. |
| **Integration (host-only)** | `tests/integration/` | ~1–2min | Textual `pilot` screen flow, CLI subprocess wiring, multi-component plumbing. Still mocks device + Drive + transcription. | Real device interaction, real upload, real transcription provider. |
| **Manual (device-required)** | `tests/manual/` + the playbook below | 5–15min per pass | Appium UI scraping fragility, wireless-ADB pairing, real WhatsApp UI changes, Drive upload, `verify_whatsapp_is_open()` safety. | Anything not in the playbook (community chats, locked phone, expired pairing codes — documented as known limits). |

## Surface coverage

| Surface | Unit | Integration | Manual |
|---|---|---|---|
| **CLI** | `tests/unit/test_cli_entry.py`, `test_headless.py`, `test_pipeline_only.py`, `test_deprecated_entry.py` | `tests/integration/test_cli.py` + `whatsapp --help` smoke | `manual-device-export` |
| **TUI** | `tests/unit/test_main_screen.py`, `test_connect_pane.py`, `test_export_pane.py`, … | `tests/integration/test_textual_tui.py`, `test_tab_navigation.py`, `test_connect_pane_preflight.py` | `manual-device-tui` |

## Dev rig

**Make available on PATH:**

```bash
poetry install --with dev
```

**Smoke-check binary is reachable:**

```bash
which whatsapp >/dev/null || { echo "whatsapp not on PATH"; exit 1; }
```

**Tear down:** nothing — no long-running services. The Textual pilot tests spin up the TUI in-process and tear it down per-test.

## Recipes

### `unit-fast`

```yaml
trigger:
  - "whatsapp_chat_autoexport/**"
  - "tests/unit/**"
  - "tests/integration/**"
  - "pyproject.toml"
  - ".claude/testing.md"
tool: terminal
artifacts:
  - pytest.log
pass: exit 0, all collected tests passed
```

**Steps:**

1. `poetry run pytest tests/unit/ -m "not slow and not requires_api and not requires_device and not requires_drive" -q --tb=short --no-cov > assets/verification/<N>/unit-fast/pytest.log 2>&1`
2. Pass iff exit 0.

### `integration-cli`

```yaml
trigger:
  - "whatsapp_chat_autoexport/cli_entry.py"
  - "whatsapp_chat_autoexport/headless.py"
  - "whatsapp_chat_autoexport/pipeline.py"
  - "whatsapp_chat_autoexport/deprecated_entry.py"
  - "tests/integration/test_cli.py"
tool: terminal
artifacts:
  - pytest.log
  - help.log
pass: exit 0 and `--headless` appears in help output
```

**Steps:**

1. `poetry run pytest tests/integration/test_cli.py -q --tb=short --no-cov > assets/verification/<N>/integration-cli/pytest.log 2>&1`
2. `poetry run whatsapp --help > assets/verification/<N>/integration-cli/help.log 2>&1`
3. Pass iff (1) exit 0 and `grep -q -- '--headless' assets/verification/<N>/integration-cli/help.log`.

### `integration-tui`

```yaml
trigger:
  - "whatsapp_chat_autoexport/tui/**"
  - "tests/integration/test_textual_tui.py"
  - "tests/integration/test_tab_navigation.py"
  - "tests/integration/test_connect_pane_preflight.py"
tool: terminal
artifacts:
  - pytest.log
pass: exit 0
```

**Steps:**

1. `poetry run pytest tests/integration/test_textual_tui.py tests/integration/test_tab_navigation.py tests/integration/test_connect_pane_preflight.py -q --tb=short --no-cov > assets/verification/<N>/integration-tui/pytest.log 2>&1`
2. Pass iff exit 0.

### `pipeline-on-fixtures`

```yaml
trigger:
  - "whatsapp_chat_autoexport/pipeline.py"
  - "whatsapp_chat_autoexport/output/**"
  - "whatsapp_chat_autoexport/export/archive_extractor.py"
  - "whatsapp_chat_autoexport/transcription/**"
tool: terminal
artifacts:
  - pipeline.log
  - output-tree.txt
pass: exit 0 and at least one non-empty file under <out>/transcripts/
```

**Steps:**

1. Create a temp output dir under the verification artifacts root:
   `OUT=assets/verification/<N>/pipeline-on-fixtures/out && mkdir -p "$OUT"`
2. `poetry run whatsapp --pipeline-only sample_data "$OUT" --no-transcribe --no-output-media --skip-drive-download > assets/verification/<N>/pipeline-on-fixtures/pipeline.log 2>&1`
3. `find "$OUT" > assets/verification/<N>/pipeline-on-fixtures/output-tree.txt`
4. Pass iff (2) exit 0 and `find "$OUT/transcripts" -type f -size +0c -name "*.txt" | grep -q .`.

### `manual-device-export` *(advisory — never auto-run)*

```yaml
trigger: []
tool: manual
artifacts: []
pass: human-confirmed per the playbook below
```

**Why empty triggers:** the dispatcher only auto-runs recipes whose triggers match changed files. An empty trigger list guarantees this recipe is never auto-fired. The recipe exists so the doc surfaces the playbook in a single place; a contributor changing `export/`, `google_drive/`, or anything in the Appium path **must** read this and run it by hand.

**Preconditions** (all required):

- Phone unlocked, screen on, kept awake during the run.
- WhatsApp installed and signed in on the phone.
- USB debugging *or* wireless debugging paired with this Mac (`adb devices` shows the device).
- Appium installed (`npm install -g appium`) and reachable on port 4723.
- `OPENAI_API_KEY` *or* `ELEVENLABS_API_KEY` exported in the shell.
- Google Drive signed in on the device.
- Expected chat-list count ≈ 700+ (confirms WhatsApp UI is healthy on the device).

**Command** (limited 2-chat smoke):

```bash
poetry run whatsapp --headless \
  --output ~/whatsapp_test \
  --auto-select \
  --limit 2 \
  --no-output-media
```

**Expected screen-by-screen** (terminal output highlights):

1. **Preflight** — three probe lines (Whisper / ElevenLabs / Drive); none HARD FAIL.
2. **Connect** — Appium starts; `WhatsApp connected` appears; `verify_whatsapp_is_open()` reports OK.
3. **Discover** — chat-list collection runs (logs show pass 1, pass 2, ContactsContract reconciliation).
4. **Select** — `--auto-select --limit 2` chooses the top 2 chats; their names print.
5. **Export** — for each of the 2 chats: open chat → menu → Export chat → media option → Drive upload → success.
6. **Process** — Drive download → archive extraction → transcript files appear.
7. **Summary** — exit code 0; `~/whatsapp_test/transcripts/` contains 2 transcript files.

**Pass criteria:**

- Exit code 0.
- `~/whatsapp_test/transcripts/` contains exactly 2 `.txt` files matching the chosen chat names.
- No traceback in the terminal.
- No `verify_whatsapp_is_open()` failure messages.

**Teardown:**

- `adb disconnect` (wireless) or unplug USB cable.
- `rm -rf ~/whatsapp_test` if you don't want to keep the output.
- Optionally remove the just-exported files from Drive (`WhatsApp Chat with <name>` zips at Drive root).

### `manual-device-tui` *(advisory — never auto-run)*

```yaml
trigger: []
tool: manual
artifacts: []
pass: human-confirmed per the playbook below
```

Same preconditions as `manual-device-export`. The difference is that the contributor walks the full Textual TUI by hand to confirm the on-screen flow has not regressed.

**Command:**

```bash
poetry run whatsapp
```

**Expected screen-by-screen:**

1. **Connect tab** — `PreflightPanel` is visible at the top with three probe rows; pressing `p` re-runs preflight.
2. **Connect tab** — selecting the device (USB or wireless) connects; status row updates to `Connected`.
3. **Discover tab** — chat list populates; count visible bottom-right (~700+).
4. **Select tab** — checkbox-select 1–2 chats; export button enables.
5. **Export tab** — progress bars advance; per-chat status updates live.
6. **Process tab** — pipeline progress visible; transcripts populate.
7. **Summary tab** — final counts; output path clickable.

**Pass criteria:**

- No traceback in the TUI's footer.
- All seven steps above are reachable without keyboard fight.
- The output directory matches what the Summary tab claims.

**Teardown:** quit the TUI with `q`. Same artifact cleanup as `manual-device-export`.

## Escalation

- `terminal` covers every auto-run recipe. No browser tools are needed because there is no web surface in this repo.
- The two `manual-*` recipes are *advisory only* — they document a human playbook. The dispatcher must never execute them; their empty triggers enforce that.
- Tests gated by `@pytest.mark.requires_device`, `@pytest.mark.requires_api`, `@pytest.mark.requires_drive`, `@pytest.mark.manual`, and `@pytest.mark.slow` are excluded from every auto-run recipe (`-m "not …"`). They run only on explicit human invocation.

## PR review hook

```bash
gh pr checkout <N>
poetry install --with dev

poetry run pytest tests/unit/ -m "not slow and not requires_api and not requires_device and not requires_drive" -q --no-cov
poetry run pytest tests/integration/test_cli.py -q --no-cov
poetry run pytest tests/integration/test_textual_tui.py tests/integration/test_tab_navigation.py tests/integration/test_connect_pane_preflight.py -q --no-cov
poetry run whatsapp --help | grep -q -- '--headless' && echo "help ✓"

OUT=$(mktemp -d)
poetry run whatsapp --pipeline-only sample_data "$OUT" --no-transcribe --no-output-media --skip-drive-download
find "$OUT/transcripts" -type f -size +0c -name "*.txt" | grep -q . && echo "pipeline-on-fixtures ✓"
rm -rf "$OUT"

gh pr comment <N> --body "Verification re-run on PR branch: unit-fast ✓ · integration-cli ✓ · integration-tui ✓ · pipeline-on-fixtures ✓"
```

This script intentionally runs the full host-only suite at PR time (not gated by changed files), because the reviewer wants to know everything still works — not just what was touched.
