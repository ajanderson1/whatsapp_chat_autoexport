# Spec — Three-tier testing protocol (`.claude/testing.md`)

**Issue:** [#21](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/21) — Define realistic testing protocols across unit, integration, and manual tiers
**Date:** 2026-04-29
**Branch:** `docs/21-define-realistic-testing-protocols`
**Mode:** `--auto`

---

## 1. Problem

The repo has three real testing tiers but no single document that says **which tier catches what, when each tier runs, or what the manual playbook is** for the device-required scenarios. The current `.claude/testing.md` is minimal (two recipes: `unit-tests`, `help-flag`) and does not surface:

- The real split between `tests/unit/`, `tests/integration/`, and `tests/manual/`.
- That **TUI integration** (Textual pilot) is part of `tests/integration/test_textual_tui.py` and worth its own targeted recipe so a TUI-only diff exercises it cleanly.
- The fact that the **CLI surface is exercised in two places** — fast `tests/unit/test_cli_entry.py` (mode dispatch) and slower `tests/integration/test_cli.py` (subprocess) — and what each tier actually proves.
- The **device-required** Appium playbook (phone unlocked, wireless ADB paired, Appium running) which is intentionally never run in CI (gated by `requires_device`).
- The escalation rule from terminal → `claude-in-chrome` (already declared in `aj-flow/PREFERENCES.md`) and where it might bite us here (it doesn't, today — and the doc should say so).

The DoD lists four conditions; this spec satisfies all four.

## 2. Goal

Codify the three tiers in one place so:

- A contributor reading the file knows **what to run before claiming a change is safe**, in less than two minutes.
- `/aj-flow flow` Step 9 (Verify) and `/aj-flow review` Step 5 (Re-verify) both pick up the *right* recipes for whatever was changed — not "all tests" and not "nothing".
- Manual device-required runs have an explicit playbook (preconditions, command, expected screen-by-screen outcomes, teardown) that is **executable from the doc alone** without grepping CLAUDE.md.

## 3. Non-goals

- **No new test infrastructure.** No new pytest plugins, no new GHA workflows, no playwright. Document protocols against what already exists (pytest, Textual pilot, `sample_data/WhatsApp Chat with Example/`, `requires_device` marker).
- **No CI changes.** Manual recipes stay manual; the `requires_device` marker already excludes them from CI by convention. We don't add a `pytest -m manual` step to GHA.
- **No replacement of `tests/README.md`.** That file is for humans reading the repo; `.claude/testing.md` is for the dispatch contract. They link at each other but live separately.
- **No new sample fixtures.** The existing `sample_data/WhatsApp Chat with Example/` (3,151 messages, 191 media files) is sufficient for every recipe except `manual-device-export`.

## 4. Tiers — what each one is for

| Tier | Where | Time budget | Catches | Doesn't catch |
|---|---|---|---|---|
| **Unit** | `tests/unit/` | < 30s for a focused subset, ~3min for full suite | Logic bugs, regression in pure functions, mode dispatch, parsers, output builders. Mocks the whole device + Drive + transcription stack. | Anything involving Appium, Drive, real APIs, or the Textual UI rendering correctly under user input. |
| **Integration (host-only)** | `tests/integration/` | ~1–2min | TUI screen flow under Textual `pilot`, CLI subprocess argument parsing, multi-component wiring. Still mocks device + Drive + transcription. | The actual Appium ↔ WhatsApp interaction; the actual Drive upload; the actual transcription provider response. |
| **Manual (device-required)** | `tests/manual/` + a written playbook | 5–15min per pass | Appium UI scraping fragility, wireless-ADB pairing, real WhatsApp UI changes, Drive upload mechanics, `verify_whatsapp_is_open()` safety logic. | Anything not exercised in the playbook (community chats, locked phone, expired pairing codes — those are documented as known limits, not retested each time). |

## 5. Surface coverage

Both **CLI** and **TUI** must have at least one recipe per *applicable* tier:

| Surface | Unit | Integration | Manual |
|---|---|---|---|
| **CLI** (`whatsapp --headless`, `--pipeline-only`) | `tests/unit/test_cli_entry.py`, `test_headless.py`, `test_pipeline_only.py`, `test_deprecated_entry.py` (≈82 tests) | `tests/integration/test_cli.py` (subprocess + `--help`) | `manual-device-export` playbook (real phone, headless mode) |
| **TUI** (`whatsapp` Textual app) | `tests/unit/test_main_screen.py`, `test_connect_pane.py`, `test_export_pane.py`, etc. (TUI-specific unit tests with Textual mocks) | `tests/integration/test_textual_tui.py` (Textual pilot, ~28 tests) | `manual-device-tui` playbook (real phone, full TUI walkthrough) |

"*Applicable*" means: the manual tier is required for both, but the unit/integration recipes are not split per surface — they share triggers via path globs. A change touching only TUI files runs the TUI recipes; a CLI-only diff runs CLI recipes; a touch to anything in `whatsapp_chat_autoexport/` runs the broad unit-suite recipe.

## 6. Recipes — names and intent

The `recipes` section will define **five** recipes (replacing today's two):

1. **`unit-fast`** — `pytest tests/unit/ -m "not slow and not requires_api and not requires_device and not requires_drive"`. Triggers on any source file or test file. Time budget: ~1min.
2. **`integration-cli`** — `pytest tests/integration/test_cli.py` plus a `whatsapp --help` smoke. Triggers on `cli_entry.py`, `headless.py`, `pipeline.py`. Time budget: ~30s.
3. **`integration-tui`** — `pytest tests/integration/test_textual_tui.py tests/integration/test_tab_navigation.py tests/integration/test_connect_pane_preflight.py`. Triggers on `tui/**`. Time budget: ~1min.
4. **`pipeline-on-fixtures`** — `whatsapp --pipeline-only sample_data/ <tmp>/ --no-transcribe --no-output-media`, asserts a non-empty transcript appears at `<tmp>/transcripts/`. Triggers on `pipeline.py`, `output/**`, `export/archive_extractor.py`, `transcription/**`. Time budget: ~10s. Proves the pipeline-only mode works end-to-end against the bundled real export.
5. **`manual-device-export`** *(declared but not auto-run)* — recipe with `tool: manual` to flag itself as a human playbook. Trigger globs: `export/**`, `google_drive/**`, anything that touches Appium/ADB. Steps are written for a human; the recipe's "pass" line documents what success looks like (e.g., "≥1 chat exported and visible in `<output>/transcripts/`"). The dispatch logic prints the playbook to stdout instead of executing it, so a contributor sees: *"This change requires a manual device run. Steps follow:"* and never has a green tick they didn't earn.

## 7. Manual playbook — what it must contain

The `manual-device-export` recipe (and a sibling `manual-device-tui` for the TUI surface) embeds an executable-by-human checklist with these required fields:

- **Preconditions** — phone unlocked; USB debugging or wireless debugging paired; Appium reachable; `OPENAI_API_KEY` *or* `ELEVENLABS_API_KEY` exported; Google Drive signed in on the device; chat-list count expected (~700+).
- **Command** — exact one-liner (`poetry run whatsapp --headless --output ~/whatsapp_test --auto-select --limit 2 --no-output-media`) so the contributor can copy-paste.
- **Expected screen-by-screen** — what should appear in the terminal at each phase (preflight → connect → discover → select → export → process → summary). Bullet-pointed; not full output.
- **Teardown** — disconnect ADB, delete `~/whatsapp_test`, optionally remove from Drive.
- **Pass criteria** — exact files that must exist at the end.

The playbook lives **inside** `.claude/testing.md` (not a separate file) so the dispatch contract and the prose-for-humans stay together — a contributor reading the doc sees both at once.

## 8. PR review hook

The `## PR review hook` section is **what a reviewer (or `/aj-flow review` Step 5) re-runs against the PR branch**. It must:

- Match the recipes — same `unit-fast` + `integration-cli` + `integration-tui` + `pipeline-on-fixtures` invocations, run unconditionally (not gated by changed files, because at PR time you want the full host-only suite green).
- Skip manual recipes (the reviewer doesn't run a phone test on a glance review).
- Post a single `gh pr comment` summarising which recipes passed, mirroring the existing pattern.

## 9. Definition of done — restated

| DoD item | How this spec satisfies it |
|---|---|
| `.claude/testing.md` exists with `version: 1` frontmatter and the four required sections | Existing file is overwritten with new content; frontmatter preserved; sections: Dev rig (= Dev server), Recipes, Escalation, PR review hook |
| Recipes cover three tiers | `unit-fast` (unit) · `integration-cli` + `integration-tui` + `pipeline-on-fixtures` (integration) · `manual-device-export` + `manual-device-tui` (manual) |
| CLI and TUI surfaces each addressed by ≥1 recipe per applicable tier | See §5 surface-coverage matrix |
| `/aj-flow flow` Step 9 dispatch picks up matching recipes | Verified in this branch's own Step 9: a no-op diff to `cli_entry.py` (e.g., a single-line comment touch in a throwaway test branch — *not* in this PR) would fire `unit-fast` + `integration-cli` + `pipeline-on-fixtures`. **In-flow proof:** the change in this PR (only `.claude/testing.md` and `docs/superpowers/**`) intentionally does *not* match any recipe trigger except via a special trigger pattern we add: the testing-doc itself triggers `unit-fast` so doc edits don't ship without at least running the unit suite. This is the smallest credible proof that dispatch fires. |

## 10. Risks and assumptions

- **Risk:** A trigger-glob mismatch silently skips a recipe. *Mitigation:* the `unit-fast` recipe has a broad trigger (`whatsapp_chat_autoexport/**`, `tests/**`, `pyproject.toml`, `.claude/testing.md`) so almost any meaningful change fires it.
- **Risk:** `pipeline-on-fixtures` is sensitive to changes in the bundled `sample_data/` content. *Mitigation:* assertions are minimal (transcript file exists, non-empty) — not byte-exact.
- **Assumption:** `tools: manual` is recognised as "print the playbook, don't try to execute it" by the flow Step 9 dispatcher. **Open question for plan:** the dispatcher currently only handles `tool: terminal`. The plan must specify whether to (a) add `tool: manual` handling to the skill, or (b) document `manual-*` recipes as advisory-only inside `.claude/testing.md` — relying on naming to keep dispatch from auto-running them. **Recommended:** option (b), since changing the skill is out of scope for this issue. The recipe trigger is left empty (`trigger: []`) so dispatch never matches it; the prose surfaces the playbook to a human reader.
- **Assumption:** No `verify.sh` exists at the repo root and we don't add one — the `.claude/testing.md` path is the contract from now on.

## 11. Out-of-band notes for the human reviewer

- The existing `tests/README.md` is left untouched. A short link added at the top of `.claude/testing.md` ("For human-friendly running instructions, see `tests/README.md`") keeps the two docs from drifting.
- `manual-*` recipes use `trigger: []` (empty list). This is the explicit signal "this recipe is advisory; never auto-run." The plan will codify this convention in the doc itself so future readers don't wonder.
- The retry budget (1) and safety-stop semantics described in `aj-flow/PREFERENCES.md` are unchanged — `.claude/testing.md` only adds recipe definitions, not new flow semantics.
