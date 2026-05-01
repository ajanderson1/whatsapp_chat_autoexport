# Three-tier testing protocol — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current minimal `.claude/testing.md` with a three-tier protocol (unit / integration / manual device-required) that covers both the CLI (`whatsapp --headless`, `--pipeline-only`) and TUI (`whatsapp` Textual app) surfaces, and that drives `/aj-flow flow` Step 9 dispatch sensibly.

**Architecture:** A single markdown file (`.claude/testing.md`) with `version: 1` frontmatter and four sections (Dev rig, Recipes, Escalation, PR review hook). Five recipes total: `unit-fast`, `integration-cli`, `integration-tui`, `pipeline-on-fixtures`, `manual-device-export` (and a sibling `manual-device-tui`). Manual recipes use `trigger: []` so dispatch never auto-runs them; the prose surfaces the playbook to a human reader. No new test infrastructure — every recipe runs against existing pytest tests, the existing `whatsapp` CLI, and the bundled `sample_data/WhatsApp Chat with Example/`.

**Tech Stack:** Markdown (YAML frontmatter), pytest with markers (`unit`, `integration`, `manual`, `requires_device`, `requires_api`, `requires_drive`, `slow`), Textual `pilot`, `whatsapp` Poetry-installed binary.

---

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `.claude/testing.md` | **rewrite** | The dispatch contract. Replaces existing two-recipe file with five-recipe three-tier protocol. |
| `docs/superpowers/specs/2026-04-29-define-realistic-testing-protocols-design.md` | already committed | The spec this plan implements. |
| `docs/superpowers/plans/2026-04-29-define-realistic-testing-protocols.md` | this file | The plan. |
| `tests/README.md` | **add one link line** | Cross-reference to `.claude/testing.md` so the two docs don't drift. |

No code files are touched. No `verify.sh` is added. No new pytest config.

---

## Task 1: Rewrite `.claude/testing.md`

**Files:**
- Modify: `.claude/testing.md` (full rewrite)

- [ ] **Step 1: Replace the file content with the three-tier protocol**

Write this exact content to `.claude/testing.md`:

````markdown
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
````

- [ ] **Step 2: Run the existing test suites against the new file**

The doc itself is not executable, but the recipes it declares must work end-to-end. Run each auto-run recipe **once, by hand**, capturing its log into the verification artifact directory expected by `flow` Step 9:

```bash
N=21
mkdir -p assets/verification/$N/{unit-fast,integration-cli,integration-tui,pipeline-on-fixtures}

# unit-fast
poetry run pytest tests/unit/ -m "not slow and not requires_api and not requires_device and not requires_drive" -q --tb=short --no-cov \
  > assets/verification/$N/unit-fast/pytest.log 2>&1
echo "unit-fast exit: $?"

# integration-cli
poetry run pytest tests/integration/test_cli.py -q --tb=short --no-cov \
  > assets/verification/$N/integration-cli/pytest.log 2>&1
echo "integration-cli pytest exit: $?"
poetry run whatsapp --help > assets/verification/$N/integration-cli/help.log 2>&1
grep -q -- '--headless' assets/verification/$N/integration-cli/help.log && echo "help ✓"

# integration-tui
poetry run pytest tests/integration/test_textual_tui.py tests/integration/test_tab_navigation.py tests/integration/test_connect_pane_preflight.py -q --tb=short --no-cov \
  > assets/verification/$N/integration-tui/pytest.log 2>&1
echo "integration-tui exit: $?"

# pipeline-on-fixtures
OUT=assets/verification/$N/pipeline-on-fixtures/out
mkdir -p "$OUT"
poetry run whatsapp --pipeline-only sample_data "$OUT" --no-transcribe --no-output-media --skip-drive-download \
  > assets/verification/$N/pipeline-on-fixtures/pipeline.log 2>&1
echo "pipeline-on-fixtures exit: $?"
find "$OUT" > assets/verification/$N/pipeline-on-fixtures/output-tree.txt
find "$OUT/transcripts" -type f -size +0c -name "*.txt" | grep -q . && echo "transcripts ✓"
```

Expected: every recipe exits 0. If any recipe fails, fix the recipe definition (paths, flags) **before** committing — the doc is the contract; a failing recipe is a doc bug.

- [ ] **Step 3: Verify the trigger globs would match this PR's diff**

A quick sanity check that `flow` Step 9's dispatcher (when it runs against this PR) would fire `unit-fast` (the only recipe whose triggers match a change to `.claude/testing.md`):

```bash
git diff --name-only origin/main...HEAD
```

Expected output (subset of):

```
.claude/testing.md
docs/superpowers/specs/2026-04-29-define-realistic-testing-protocols-design.md
docs/superpowers/plans/2026-04-29-define-realistic-testing-protocols.md
tests/README.md
```

`unit-fast` lists `.claude/testing.md` in its triggers, so dispatch will pick it up. The other two recipes (`integration-cli`, `integration-tui`, `pipeline-on-fixtures`) won't match — that is correct, because this PR doesn't touch CLI, TUI, or pipeline source. Document this expectation in the commit message of Step 5.

- [ ] **Step 4: Stage and commit the rewrite**

```bash
git add .claude/testing.md
git commit -m "docs(testing): three-tier protocol with five recipes (#21)

Replaces the previous two-recipe minimal contract with three tiers
(unit / integration / manual device-required) and five recipes:
unit-fast, integration-cli, integration-tui, pipeline-on-fixtures,
manual-device-export, manual-device-tui.

Manual recipes use trigger: [] so dispatch never auto-runs them; the
prose surfaces the playbook for a human reader. Both CLI and TUI
surfaces are addressed by at least one recipe per applicable tier.

PR review hook runs the full host-only suite (not diff-gated) so a
reviewer sees everything is green at PR time.

Closes #21"
```

---

## Task 2: Cross-reference link from `tests/README.md`

**Files:**
- Modify: `tests/README.md` (one line near the top, after the H1)

- [ ] **Step 1: Read the current top of `tests/README.md`**

Run: `head -10 tests/README.md`

Expected: file starts with `# Testing Guide` and a one-paragraph intro.

- [ ] **Step 2: Insert the cross-reference under the H1**

Use the Edit tool to insert this line immediately after `# Testing Guide`:

```markdown

> **For the agentic dispatch contract used by `/aj-flow flow` Step 9, see [`.claude/testing.md`](../.claude/testing.md).**
```

The Edit replaces the first H1 + immediately following blank line block with the H1 + blockquote + blank line, leaving the rest of the file untouched.

- [ ] **Step 3: Confirm the file still parses sensibly**

Run: `head -5 tests/README.md`

Expected: H1 followed by the new blockquote, then the original intro paragraph.

- [ ] **Step 4: Stage and commit**

```bash
git add tests/README.md
git commit -m "docs(tests): link tests/README.md to .claude/testing.md (#21)

Keeps the human-friendly running guide and the agent dispatch contract
cross-referenced so they don't drift."
```

---

## Task 3: Capture verification artifacts for the PR body

**Files:**
- Read-only — uses `assets/verification/21/` produced by Task 1 Step 2.

- [ ] **Step 1: Confirm artifacts exist**

Run:

```bash
ls -la assets/verification/21/
ls -la assets/verification/21/unit-fast/
ls -la assets/verification/21/integration-cli/
ls -la assets/verification/21/integration-tui/
ls -la assets/verification/21/pipeline-on-fixtures/
```

Expected: each directory contains the logs listed in the recipe `artifacts:` blocks (`pytest.log`, `help.log`, `pipeline.log`, `output-tree.txt`).

- [ ] **Step 2: Confirm `assets/verification/` is gitignored**

Run: `git check-ignore -v assets/verification/21/unit-fast/pytest.log`

Expected: a line like `.gitignore:N:assets/verification/    assets/verification/21/unit-fast/pytest.log` confirming the path is ignored.

If the file is **not** ignored (no output from `git check-ignore`), append `assets/verification/` to `.gitignore` and commit:

```bash
echo "assets/verification/" >> .gitignore
git add .gitignore
git commit -m "chore: ignore assets/verification/ (aj-flow trail)"
```

(Likely no-op — `aj-flow bootstrap`'s previous run already added this. Check first.)

- [ ] **Step 3: Append a one-line summary to `flow.log`**

```bash
echo "$(date '+%H:%M:%S') step 8/9 done — unit-fast ✓ · integration-cli ✓ · integration-tui ✓ · pipeline-on-fixtures ✓" \
  >> assets/verification/21/flow.log
```

This is the entry that the PR body's `## Agent ran` section points to.

---

## Self-review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| §4 Tiers | Task 1 — "Tiers" table in the new doc |
| §5 Surface coverage | Task 1 — "Surface coverage" table |
| §6 Recipes (5 of them) | Task 1 — five recipe blocks |
| §7 Manual playbook fields | Task 1 — `manual-device-export` and `manual-device-tui` recipe blocks |
| §8 PR review hook | Task 1 — `## PR review hook` section |
| §9 DoD: file with frontmatter + 4 sections | Task 1 |
| §9 DoD: three tiers covered | Task 1 — five recipes split across three tiers |
| §9 DoD: CLI + TUI per applicable tier | Task 1 — surface-coverage table + recipe triggers |
| §9 DoD: dispatch picks up matching recipes | Task 1 Step 3 — diff vs `unit-fast` triggers |
| §10 Risk: glob mismatch | `unit-fast` has broad triggers including `.claude/testing.md` |
| §10 Open question on `tool: manual` | Resolved with `trigger: []` convention; documented in the recipe block + Escalation section |
| §11 `tests/README.md` link | Task 2 |

**Placeholder scan:** none. Every recipe has full YAML, full steps, and exact pass criteria. Every command has explicit paths and expected outputs.

**Type consistency:** recipe names are spelled identically in the doc, the verification commands, and the PR review hook (`unit-fast`, `integration-cli`, `integration-tui`, `pipeline-on-fixtures`, `manual-device-export`, `manual-device-tui`). The artifact directory names match the recipe names.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-29-define-realistic-testing-protocols.md`.

This plan is small (3 tasks, all doc + verification) so **inline execution via `superpowers:executing-plans`** is more appropriate than spinning up a subagent per task. The flow Step 6 dispatcher should pick `executing-plans`, not `subagent-driven-development`, for this size of change.
