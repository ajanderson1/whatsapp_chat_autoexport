# Convention Alignment Design — whatsapp_chat_autoexport

**Date:** 2026-05-21
**Status:** approved (pending spec review)
**Owner:** AJ Anderson

## What this is

Bring the `whatsapp_chat_autoexport` repository into full alignment with `~/.conventions/CONVENTIONS.md`. The repo predates several conventions (uv adoption, `src/` layout, AGENTS.md template, `.ai/` directory, lefthook hooks, `mypy --strict`, release-please, dependabot, multi-job CI). This work closes those gaps without changing product behavior.

## Goals

- Repo becomes a reference implementation of the conventions (so future-AJ and any agent loading the file finds nothing surprising).
- No regression in tested behavior. Every PR in the train passes the existing pytest suite.
- Each PR is independently mergeable, independently revertible.
- Execution is autonomous: AJ approves the spec, the agent files issues, branches, opens PRs, and merges each on green CI.

## Non-goals

- Restructuring tests beyond what the `src/` move forces.
- Rewriting / trimming `CLAUDE.md`'s 34k of legitimate developer documentation. The content moves to `docs/internals/architecture.md`; only the AGENTS.md / symlink shape changes.
- Migrating Textual, Appium, Whisper, ElevenLabs, or Google Drive integrations. Those are product choices, not convention gaps.
- Touching production deployment. The project deploys via local Docker; no `DEPLOYMENT_CONTEXT` exists and none is needed yet.
- Reflowing all documented commands beyond the mechanical `poetry run` → `uv run` swap.

## Gap analysis (snapshot, 2026-05-21)

| Convention | Current state | Gap |
|---|---|---|
| `default-stack.md` toolchain | Poetry | Needs uv (PR 2) |
| `python.md` layout | Flat `whatsapp_chat_autoexport/` at repo root | Needs `src/` layout (PR 3) |
| `python.md` typecheck | No mypy configured | Needs `mypy --strict` + per-module overrides (PR 4) |
| `git.md` AGENTS.md | Exists but doesn't match template, 30 lines but missing canonical commands / where-things-live / project glossary | Rewrite (PR 1) |
| `git.md` CLAUDE.md | 34k regular file with developer docs | Must be a symlink to AGENTS.md; existing content moves to `docs/internals/architecture.md` (PR 1) |
| `git.md` `.ai/` | Absent | Add scaffold (PR 1) |
| `git.md` `.gitignore` | Missing `.cursor/`, `.codex/`, `.opencode/`, `.aider*`, `CLAUDE.local.md`, `*.local.md`, `GEMINI.md` | Extend (PR 1) |
| `ci.md` pre-commit | No lefthook / pre-commit | Add lefthook with format→lint→typecheck→secret-scan cascade (PR 4) |
| `ci.md` `verify.sh` | Absent | Add (PR 4) |
| `ci.md` GH Actions | Single `test.yml`, no lint / typecheck / secret-scan | Expand to `ci.yml` with parallel jobs (PR 5) |
| `deps.md` Dependabot | Absent | Add `.github/dependabot.yml` (PR 5) |
| `release.md` release-please | Absent | Add workflow + config + manifest (PR 5) |
| `git.md` LICENSE | MIT, AJ Anderson | ✅ present |
| `readme.md` README | Present | ✅ in scope only if PR audit surfaces issues |

## Architecture: five-PR train

Each PR has one branch, one issue, lands sequentially, merges on green CI. The agent runs autonomously per AJ's directive: file the issue, cut the branch under `.worktrees/`, do the work, run `verify.sh` locally before push, open the PR with `gh pr create`, watch CI, merge on green.

Between any two PRs the repo is in a working state.

```
PR 1: Repo hygiene & AI files
  └── AGENTS.md rewrite, CLAUDE.md→symlink, .ai/ scaffold, .gitignore extensions
  └── Risk: near-zero (docs + symlink only)

PR 2: uv migration
  └── pyproject.toml PEP 621, uv.lock, Dockerfile, CI, docs, AGENTS.md commands
  └── Risk: medium (lockfile re-resolve, build-system swap)

PR 3: src/ layout
  └── git mv to src/whatsapp_chat_autoexport, pyproject build config, coverage path
  └── Risk: medium (build config must point at new path)

PR 4: lefthook + mypy + verify.sh
  └── lefthook.yml, [tool.mypy] strict + per-module overrides, verify.sh
  └── Risk: low-medium (mypy may surface real bugs — fix inline)

PR 5: CI + release-please + dependabot
  └── ci.yml multi-job, release-please.yml + config + manifest, dependabot.yml, labels
  └── Risk: medium (release-please needs repo permissions check)
```

## Per-PR detail

### PR 1 — Repo hygiene & AI files

**Branch:** `chore/NN-repo-hygiene-ai-files` (NN from issue created up-front).

**Files touched:**
- `AGENTS.md` — full rewrite to convention template.
- `CLAUDE.md` — content moves to `docs/internals/architecture.md`; replaced with symlink to `AGENTS.md` (`ln -s AGENTS.md CLAUDE.md`; symlink itself is committed).
- `docs/internals/architecture.md` — new home for the existing developer documentation.
- `.ai/commands/.gitkeep`, `.ai/skills/.gitkeep`, `.ai/plans/.gitkeep` — empty scaffold.
- `.gitignore` — add `.cursor/`, `.codex/`, `.opencode/`, `.aider*`, `CLAUDE.local.md`, `*.local.md`, `GEMINI.md`. Confirm `.claude/`, `.worktrees/`, `assets/verification/` remain.

**AGENTS.md content sections (≤50 lines):**
- One-paragraph "what this is" describing the WhatsApp export automation.
- Stack constraints — empty at PR 1 time (uv lands in PR 2; `src/` lands in PR 3). Each later PR adds or removes entries as appropriate.
- Canonical commands — `dev: n/a`, `build: docker build .`, `test: poetry run pytest` (changes to `uv run pytest` in PR 2), `lint: poetry run ruff check .`, `format: poetry run ruff format .`, `typecheck: n/a` (changes to `uv run mypy src/` in PR 4).
- Where things live — pointer at `whatsapp_chat_autoexport/` (becomes `src/whatsapp_chat_autoexport/` after PR 3), `tests/`, `docs/`, `docs/internals/architecture.md` (new), `sample_data/`, `.ai/`.
- Project glossary — short list: ChatExporter, WhatsAppDriver, AppiumManager, preflight, pipeline phases.
- In-flight — empty at PR 1; mentions the convention alignment effort itself while it's running.
- Project note link — `obsidian://open?vault=Journal&file=Atlas%2FWhatsapp%20Chat%20AutoExport`.

**Verification:**
- `readlink CLAUDE.md` returns `AGENTS.md`.
- `cat CLAUDE.md` returns the AGENTS.md content (proves the symlink resolves).
- `wc -l AGENTS.md` ≤ 50.
- `git diff --stat` shows expected files only.
- `uv run pytest` (still poetry at this stage — so `poetry run pytest`) green: no code touched.

**Risk:** Near-zero. Symlinks behave identically on macOS and Linux (only platforms in use).

### PR 2 — uv migration

**Branch:** `chore/NN-uv-migration`.

**Files touched:**
- `pyproject.toml` — full rewrite of `[tool.poetry]`-based config to PEP 621 `[project]` + `[dependency-groups]`. Keep all existing `[project.scripts]` entries. Replace `[build-system]` with `hatchling`. Preserve `[tool.pytest.ini_options]`, `[tool.coverage.*]`, `[tool.ruff.*]` unchanged.
- `uv.lock` — generated via `uv lock`.
- `poetry.lock` — deleted.
- `Dockerfile` — swap `pip install poetry && poetry install --no-root` for `pip install uv && uv sync --frozen --no-dev`. Entry point stays `whatsapp --headless`.
- `.github/workflows/test.yml` — swap `pip install poetry` + `poetry install --with dev` for `astral-sh/setup-uv@v3` + `uv sync --all-extras --dev`. Test step becomes `uv run pytest …`.
- `Makefile` — already uses `uv run mkdocs`; no change needed but audit.
- `docs/internals/architecture.md` (the renamed CLAUDE.md) — sed pass replacing `poetry run` → `uv run`, `poetry install` → `uv sync`, `poetry add` → `uv add`. Tighten the install/setup section to match uv's flow.
- `README.md`, `QUICKSTART.md`, `README.Docker.md` — same sed pass.
- `AGENTS.md` — canonical commands block updated to `uv run`.

**Dependency-group choice:** Use `[dependency-groups]` (PEP 735) for dev deps. `uv sync --all-extras --dev` activates them in CI. This is the convention's preferred shape per `default-stack.md`.

**Verification:**
- `uv sync --all-extras --dev` succeeds locally.
- `uv run pytest -m "not requires_api and not requires_device and not requires_drive"` matches pre-migration test count.
- `uv run whatsapp --help` prints CLI help.
- CI is green.
- `docker build -t whatsapp-export .` succeeds. (Run smoke test is manual since `requires_device`.)

**Risk:** Medium. PEP 621 metadata must include all Poetry quirks (URL fields, classifiers if any). The textual/appium/elevenlabs/openai/google stack resolves cleanly on PEP 621 today.

### PR 3 — `src/` layout

**Branch:** `chore/NN-src-layout`.

**Files touched:**
- `git mv whatsapp_chat_autoexport src/whatsapp_chat_autoexport` — preserves history.
- `pyproject.toml` — add `[tool.hatch.build.targets.wheel] packages = ["src/whatsapp_chat_autoexport"]`. Update `[tool.coverage.run] source = ["src/whatsapp_chat_autoexport"]`. `[tool.ruff.lint.isort] known-first-party` unchanged (package name is identical).
- `mkdocs.yml` — check for path references; mkdocstrings may need `paths: [src]`.
- `Makefile` / `docs/internals/architecture.md` — update file-tree diagrams.
- Cleanup that must happen at this PR: the stray log/XML files currently nested inside the package directory (`export_log.txt`, `export_error_*.xml`, `google_drive_error_*.xml`) move out — to `.logs/` if they're useful or deleted if they're debugging detritus. They must NOT move into `src/`.

**Imports:** No code-level import changes. Every `from whatsapp_chat_autoexport.foo import …` continues to resolve.

**Verification:**
- `uv run pytest` matches pre-move test count.
- `uv run whatsapp --help` works.
- `docker build` succeeds.
- `git log --follow src/whatsapp_chat_autoexport/cli_entry.py` shows history pre-move.
- No file at `whatsapp_chat_autoexport/` at repo root after the move.

**Risk:** Medium. Mostly the build config; the move itself is mechanical. Watch for `sys.path` games in tests.

### PR 4 — Lefthook + mypy + verify.sh

**Branch:** `chore/NN-lefthook-mypy-verify`.

**Files touched:**
- `pyproject.toml` — add `mypy` and `gitleaks` (binary; or vendor via pre-commit) to `[dependency-groups]` dev. Add `[tool.mypy]` with `strict = true`, plus `[[tool.mypy.overrides]]` blocks for known-noisy modules: `whatsapp_chat_autoexport.whatsapp_export`, `whatsapp_chat_autoexport.legacy.*`, `whatsapp_chat_autoexport.tui.*`. Override modules get `ignore_errors = true` initially.
- `lefthook.yml` — four-stage cascade (run order matches `ci.md`):
  1. `ruff format` (auto-fix on commit, doesn't block)
  2. `ruff check` (blocks)
  3. `mypy src/` (blocks)
  4. `gitleaks protect --staged` (blocks)
- `verify.sh` (new, `chmod +x`) — runs the same four-stage cascade plus `uv run pytest -m "not requires_api and not requires_device and not requires_drive"`. Writes artifacts (logs of each stage) to `$ARTIFACTS_DIR` per `ci.md`. Exit 0 on full pass.
- `AGENTS.md` — `typecheck: uv run mypy src/` populated.

**On per-module overrides.** Strict typing on legacy modules is deferred deliberately — new code is held to `--strict`, existing code is allowlisted by module so the hook can land without forcing a multi-day type rewrite. Each override entry is a TODO ticket waiting to be opened; intent is to remove them over time.

**On `gitleaks` install.** Use the prebuilt binary in CI (fast) and on developer machines via `brew install gitleaks`. If gitleaks isn't available, lefthook gracefully reports "skipped" rather than failing — preferable to a hook that requires a manual install before the project works.

**Verification:**
- `lefthook install` then `git commit` triggers the cascade.
- `./verify.sh` exits 0 on a clean working tree.
- `uv run mypy src/` exits 0 (with overrides absorbing legacy noise).
- `gitleaks detect` exits 0 against the repo history.

**Risk:** Low-medium. mypy may surface genuine bugs in non-override modules — those get fixed inline rather than added to the overrides list.

### PR 5 — CI + release-please + dependabot

**Branch:** `chore/NN-ci-release-dependabot`.

**Files touched:**
- `.github/workflows/test.yml` → renamed to `.github/workflows/ci.yml`. Expanded to four parallel jobs:
  - `lint` — `uv run ruff check . && uv run ruff format --check .`
  - `typecheck` — `uv run mypy src/`
  - `test` — existing pytest run, unchanged
  - `secret-scan` — `gitleaks detect --no-banner`
  All four jobs share an `actions/checkout@v4` + `astral-sh/setup-uv@v3` + `uv sync` prelude.
- `.github/workflows/release-please.yml` (new) — `googleapis/release-please-action@v4`, triggered on push to `main`, permissions `contents: write` + `pull-requests: write`.
- `release-please-config.json` (new) — release type `python`, `package-name: whatsapp-chat-autoexport`, `bump-minor-pre-major: true`.
- `.release-please-manifest.json` (new) — `{".": "0.2.0"}` (current version).
- `.github/dependabot.yml` (new) — `pip` ecosystem on `/`, weekly, one PR per dep, labels `type:chore`.
- GitHub labels — `gh label create type:feat type:fix type:chore type:docs` if missing.
- `README.md` — confirm CI badge URL still resolves (workflow filename changed from `test.yml` to `ci.yml`).

**Pre-PR check:** `gh api repos/:owner/:repo -q .permissions` to confirm `contents: write` is on. If not, fail loudly in the PR body asking AJ to flip it — do not silently merge a no-op release-please.

**Verification:**
- All four CI jobs green on the PR itself.
- After merge to `main`, release-please opens a release PR within ~5 minutes.
- Dependabot opens its first scan within 24h (out of band, not blocking PR merge).

**Risk:** Medium. release-please permissions and the `python` release type config are the failure modes. Both are covered by the pre-PR permission check and a dry-run of the release-please action locally if needed.

## Workflow and execution

**Per-PR loop:**
1. `gh issue create --title "<title>" --label type:chore --milestone <active>` — capture branch number.
2. `git worktree add .worktrees/<branch-leaf> -b chore/NN-<slug>` from latest `main`.
3. Make the changes.
4. Run `./verify.sh` locally (or in PR 1–3 the per-PR verification listed above).
5. `gh pr create` with body `Closes #NN`.
6. Wait for CI green.
7. `gh pr merge --auto --squash` (auto-merge already enabled per AGENTS.md).
8. After merge: `git worktree remove .worktrees/<branch-leaf>`, delete the local branch, pull `main`.
9. Move to next PR.

**Rollback strategy.** Each PR is squash-merged. If a PR breaks `main` for downstream work, `gh pr create` a revert PR or `git revert <sha>` from a fresh branch. No PR depends on a non-`main` state from another PR.

**Halt conditions.** Stop autonomous execution and surface to AJ if any of:
- `mypy --strict` (PR 4) reveals a bug that would change runtime behavior — needs a judgment call.
- Lockfile resolution (PR 2) downgrades a critical dep (textual, appium-python-client, openai SDK).
- release-please (PR 5) requires repo permission changes that the agent can't make.
- Any test fails post-`src/` move (PR 3) and the cause isn't a path/import oversight.
- Any pre-commit hook flags secrets in repo history (PR 4) — needs a key-rotation conversation, not a quiet fix.

## Error handling

- **Failing CI on a PR:** never disable a check to merge. Investigate, fix forward.
- **Pre-commit hook fails locally:** fix the underlying issue. Never `--no-verify`. The conventions explicitly forbid bypass without chat confirmation.
- **Convention drift mid-train:** if `~/.conventions/CONVENTIONS.md` changes during execution, finish the current PR, then re-evaluate. Don't try to track a moving target inside one PR.

## Testing strategy

- Each PR runs the full pytest suite (filtered to skip `requires_api`, `requires_device`, `requires_drive`).
- PR 3 (`src/` move) is the only one likely to surface new test failures. Mitigation: do a full local `uv run pytest -v` before push.
- No new tests are added by this work. Convention alignment changes are validated by the conventions themselves (`./verify.sh`, lefthook, CI green).
- Manual smoke test of the full export flow happens once, after PR 3 lands, against a real Android device. If it works, PR 4 and 5 land without further device-level checks.

## Out-of-scope (deferred follow-ups)

- Splitting `CLAUDE.md`'s 34k content into multiple focused docs under `docs/`.
- Tightening mypy overrides — opening per-module issues to type-clean `whatsapp_export.py`, `tui/*`, `legacy/*` over time.
- Bitwarden secret flow (`secrets.md`) — current setup uses `.env` + env vars; works for now.
- MkDocs site polish.
- `DEPLOYMENT_CONTEXT` files — not yet warranted.

## See also

- `~/.conventions/CONVENTIONS.md` — root.
- `~/.conventions/conventions/default-stack.md` — uv defaults.
- `~/.conventions/conventions/python.md` — src layout, mypy strict.
- `~/.conventions/conventions/git.md` — AGENTS.md template, symlink rule, `.ai/`, `.gitignore` defaults.
- `~/.conventions/conventions/ci.md` — pre-commit cascade, verify.sh, Python runner detection.
- `~/.conventions/conventions/release.md` — release-please, tags.
- `~/.conventions/conventions/deps.md` — Dependabot weekly, release-please.
