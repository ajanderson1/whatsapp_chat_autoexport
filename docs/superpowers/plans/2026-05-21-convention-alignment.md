# Convention Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `whatsapp_chat_autoexport` into full alignment with `~/.conventions/CONVENTIONS.md` via five sequenced PRs, each merged on green CI before the next begins.

**Architecture:** Five-PR train executed autonomously. PR 1 lands repo hygiene & AI files; PR 2 migrates Poetry → uv; PR 3 moves to `src/` layout; PR 4 adds lefthook + mypy + verify.sh; PR 5 adds multi-job CI + release-please + dependabot. Each PR is independently green and revertible. Between PRs the repo is always in a working state.

**Tech Stack:** Python 3.13, uv, ruff, mypy (strict + per-module overrides), pytest, lefthook, gitleaks, GitHub Actions, release-please, Dependabot.

**Spec:** `docs/superpowers/specs/2026-05-21-convention-alignment-design.md`

---

## Conventions for the executor

- **Worktrees:** every PR uses its own worktree under `.worktrees/<branch-leaf>/`. Create via `git worktree add .worktrees/<branch-leaf> -b <branch-name>` from latest `main`.
- **Branch naming:** `chore/NN-<slug>` where NN is the GitHub issue number created in step 1 of each task group.
- **Issue creation:** `gh issue create --title "<title>" --label type:chore --body "<body>"`. Capture the returned issue number.
- **PR body:** must include `Closes #NN`.
- **Auto-merge:** project already has auto-merge enabled. After CI is green, run `gh pr merge --auto --squash`.
- **Local-first CI:** run the test command on the worktree branch before `git push`. No red CI gets pushed.
- **No `--no-verify`:** never skip hooks. If a hook fails, fix the underlying issue.
- **Conventional commits:** every commit is `<type>(<scope>): <subject>`. Most commits here are `chore` or `docs`.
- **Cleanup after merge:** `git worktree remove .worktrees/<branch-leaf>` and `git branch -d chore/NN-<slug>` once the PR squash-merges.
- **Halt conditions** (from spec § Workflow and execution): mypy reveals runtime-changing bugs; uv lockfile downgrades a critical dep; release-please needs repo permission changes; tests fail post-`src/` move with non-path-related cause; gitleaks flags secrets in history.

---

## PR 1 — Repo hygiene & AI files

### Task 1.1: File issue and create worktree

**Files:** none touched yet.

- [ ] **Step 1: File the GitHub issue**

Run:

```bash
gh issue create \
  --title "Convention alignment PR 1: repo hygiene & AI files" \
  --label type:chore \
  --body "Bring AGENTS.md, CLAUDE.md, .ai/, .gitignore in line with ~/.conventions/CONVENTIONS.md. See docs/superpowers/specs/2026-05-21-convention-alignment-design.md § PR 1."
```

Expected: outputs the issue URL. Note the issue number (referred to as `NN1` below).

- [ ] **Step 2: Create the worktree**

Run from repo root:

```bash
git fetch origin main
git worktree add .worktrees/repo-hygiene-ai-files -b chore/NN1-repo-hygiene-ai-files origin/main
cd .worktrees/repo-hygiene-ai-files
```

Expected: new worktree under `.worktrees/repo-hygiene-ai-files/` checked out at `chore/NN1-repo-hygiene-ai-files`.

All subsequent steps in this PR run inside this worktree.

### Task 1.2: Move CLAUDE.md content to docs/internals/architecture.md

**Files:**
- Create: `docs/internals/architecture.md`
- Will-overwrite-in-Task-1.4: `CLAUDE.md` (currently regular file)

- [ ] **Step 1: Create the docs/internals directory and move content**

Run:

```bash
mkdir -p docs/internals
git mv CLAUDE.md docs/internals/architecture.md
```

Expected: `docs/internals/architecture.md` now contains the full previous CLAUDE.md content; `CLAUDE.md` no longer exists at repo root.

- [ ] **Step 2: Add an H1 + brief intro to the moved file**

Open `docs/internals/architecture.md`. Replace the existing first H1 line (`# CLAUDE.md`) with:

```markdown
# whatsapp_chat_autoexport — Developer Architecture Reference

> Source of truth for the project's internal architecture, commands, workflows, and testing strategy. Used by Claude Code and other coding agents via `AGENTS.md` → `## Where things live`.
```

- [ ] **Step 3: Verify no broken self-references**

Run:

```bash
grep -nE "CLAUDE\.md" docs/internals/architecture.md README.md QUICKSTART.md README.Docker.md 2>/dev/null
```

Expected: any `CLAUDE.md` references in `README.md` / `QUICKSTART.md` / `README.Docker.md` need updating to point at `docs/internals/architecture.md`. Update them inline. Self-references inside `architecture.md` itself (e.g. the historical phrase "Contents of CLAUDE.md") can stay — they're historical context.

- [ ] **Step 4: Commit**

```bash
git add docs/internals/architecture.md README.md QUICKSTART.md README.Docker.md
git commit -m "docs: move CLAUDE.md content to docs/internals/architecture.md"
```

### Task 1.3: Rewrite AGENTS.md to the convention template

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Replace AGENTS.md with the convention template**

Overwrite `AGENTS.md` with this exact content:

```markdown
# AGENTS.md
> Project-specific context. Global conventions: ~/.conventions/CONVENTIONS.md.

## What this is

WhatsApp chat export automation for Android. Uses Appium + UiAutomator2 to drive the WhatsApp UI, trigger per-chat exports to Google Drive, then download, extract, transcribe (Whisper / ElevenLabs), and build a final organised output. Single-user tool; runs locally or in Docker.

## Stack constraints (overrides global defaults)
<!-- Empty here at PR 1 time. Entries are added by later PRs in the convention-alignment train. -->

## Canonical commands
- dev: n/a
- build: `docker build -t whatsapp-export .`
- test: `poetry run pytest`
- lint: `poetry run ruff check .`
- format: `poetry run ruff format .`
- typecheck: n/a

## Where things live
- `whatsapp_chat_autoexport/` — main package (moves to `src/whatsapp_chat_autoexport/` in a later PR).
- `tests/unit/`, `tests/integration/` — pytest suite.
- `docs/internals/architecture.md` — developer architecture reference (commands, workflows, testing strategy).
- `docs/superpowers/specs/` — design specs.
- `docs/superpowers/plans/` — implementation plans.
- `sample_data/` — real WhatsApp export used by tests.
- `.ai/` — portable prompt templates, skills, plans (harness-agnostic).

## Project glossary
- **ChatExporter** — orchestrates the per-chat WhatsApp → Drive export flow.
- **WhatsAppDriver** — Appium-based UI driver with verification + lock detection.
- **AppiumManager** — manages Appium server lifecycle on port 4723.
- **Preflight** — API credential capacity checks run before every session.
- **Pipeline** — download → extract → transcribe → build-output stages run after export.

## In-flight
- Convention alignment effort — see `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` and `docs/superpowers/plans/2026-05-21-convention-alignment.md`. Some commands above change as the train lands (poetry → uv; layout flat → `src/`; typecheck `n/a` → `mypy src/`).

## Autonomous allowlist
<!-- Empty. -->

## Project note
[Atlas/Whatsapp Chat AutoExport](obsidian://open?vault=Journal&file=Atlas%2FWhatsapp%20Chat%20AutoExport)
```

- [ ] **Step 2: Verify line count**

Run:

```bash
wc -l AGENTS.md
```

Expected: line count ≤ 50 (target from `git.md` § AGENTS.md shape and rules). If over, trim glossary or where-things-live entries.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): rewrite AGENTS.md to convention template"
```

### Task 1.4: Replace CLAUDE.md with a symlink to AGENTS.md

**Files:**
- Create: `CLAUDE.md` (symlink → `AGENTS.md`)

- [ ] **Step 1: Create the symlink and stage it**

Run from repo root:

```bash
ln -s AGENTS.md CLAUDE.md
git add CLAUDE.md
```

- [ ] **Step 2: Verify the symlink resolves and the file is recorded as a symlink**

Run:

```bash
test -L CLAUDE.md && echo "OK: symlink"
readlink CLAUDE.md
git ls-files --stage CLAUDE.md
```

Expected:
- `OK: symlink`
- `AGENTS.md`
- A line like `120000 <hash> 0	CLAUDE.md` (mode `120000` = symlink).

- [ ] **Step 3: Verify symlink content matches AGENTS.md**

Run:

```bash
diff -q CLAUDE.md AGENTS.md
```

Expected: no output (files compare identical — symlink resolves).

- [ ] **Step 4: Commit**

```bash
git commit -m "docs(agents): symlink CLAUDE.md → AGENTS.md (per git.md)"
```

### Task 1.5: Add the `.ai/` scaffold

**Files:**
- Create: `.ai/commands/.gitkeep`
- Create: `.ai/skills/.gitkeep`
- Create: `.ai/plans/.gitkeep`
- Create: `.ai/README.md`

- [ ] **Step 1: Create the directory scaffold**

Run:

```bash
mkdir -p .ai/commands .ai/skills .ai/plans
touch .ai/commands/.gitkeep .ai/skills/.gitkeep .ai/plans/.gitkeep
```

- [ ] **Step 2: Add a brief README pointing at the convention**

Write `.ai/README.md` with this exact content:

```markdown
# .ai/

Portable, harness-agnostic prompt templates, skills, and plans. Each harness (Claude Code, Codex, OpenCode, Pi) references this directory from its own config. Content is plain markdown; never harness-specific syntax.

See `~/.conventions/conventions/git.md` § AI assistant files — committed vs gitignored.

- `commands/` — prompt templates.
- `skills/` — progressive-disclosure docs.
- `plans/` — design / implementation plans (project-level plans currently live in `docs/superpowers/plans/`; this directory exists for the future).
```

- [ ] **Step 3: Commit**

```bash
git add .ai/
git commit -m "chore: add .ai/ scaffold for portable prompts/skills/plans"
```

### Task 1.6: Extend `.gitignore` with convention defaults

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read current `.gitignore`**

Run:

```bash
cat .gitignore
```

Confirm which of the convention defaults are missing. The full required set (from `git.md` § .gitignore defaults) is:

```
# Local env
.env
.env.local
.env.*.local

# Worktrees
.worktrees/

# Verification artifacts (per ci.md)
assets/verification/

# AI assistant caches and local overrides
.claude/
.cursor/
.codex/
.opencode/
.aider*
CLAUDE.local.md
*.local.md
GEMINI.md

# OS / editor
.DS_Store
.vscode/
.idea/
*.swp
```

- [ ] **Step 2: Edit `.gitignore` so all of the above lines are present**

Add any missing lines under the appropriate comment header. Preserve existing project-specific lines (`EXECUTIVE_SUMMARY.md`, `*.xml`, `.serena`, `upload_error_*.xml`, `whatsapp_chat_autoexport.code-workspace`, `run_full_export.py`, `test_tui_flow.py`, `site/`, `PRPs/`, `.logs/`, `.mcp.json`). Don't reorder or delete those.

After the edit, the new lines that must appear (and not be duplicates of existing entries) are:

```gitignore
.env.local
.env.*.local
.cursor/
.codex/
.opencode/
.aider*
CLAUDE.local.md
*.local.md
GEMINI.md
.vscode/
.idea/
*.swp
```

(`.env`, `.claude/`, `.worktrees/`, `assets/verification/`, `.DS_Store` are already present — leave them alone.)

- [ ] **Step 3: Confirm no currently-tracked file becomes ignored**

Run:

```bash
git status --ignored | grep -E "^\s+(\.cursor|\.codex|\.opencode|\.aider|CLAUDE\.local|GEMINI)" || echo "no surprises"
```

Expected: `no surprises` (none of the newly-ignored patterns match anything currently tracked).

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: extend .gitignore with convention defaults"
```

### Task 1.7: Push, open PR, merge on green

- [ ] **Step 1: Run pytest locally on the worktree branch**

Run:

```bash
poetry install --with dev
poetry run pytest -m "not requires_api and not requires_device and not requires_drive"
```

Expected: green. (No code touched — should match `main` test count.)

- [ ] **Step 2: Push the branch**

```bash
git push -u origin chore/NN1-repo-hygiene-ai-files
```

- [ ] **Step 3: Open the PR**

Run (substitute `NN1`):

```bash
gh pr create --title "chore: repo hygiene & AI files (convention alignment PR 1/5)" --body "$(cat <<'EOF'
## Summary
- Rewrite AGENTS.md to the convention template (≤50 lines, canonical commands, where-things-live, glossary).
- Move existing CLAUDE.md content to `docs/internals/architecture.md`; replace `CLAUDE.md` with a symlink to `AGENTS.md` (per `git.md`).
- Add `.ai/` scaffold (`commands/`, `skills/`, `plans/`) with a brief README.
- Extend `.gitignore` with convention defaults (`.cursor/`, `.codex/`, `.opencode/`, `.aider*`, `CLAUDE.local.md`, `*.local.md`, `GEMINI.md`, `.vscode/`, `.idea/`, `*.swp`).

Closes #NN1.

Spec: `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` § PR 1.

## Test plan
- [x] `readlink CLAUDE.md` returns `AGENTS.md`.
- [x] `wc -l AGENTS.md` ≤ 50.
- [x] `diff -q CLAUDE.md AGENTS.md` is empty.
- [x] `poetry run pytest -m "not requires_api and not requires_device and not requires_drive"` matches pre-PR test count.
EOF
)"
```

- [ ] **Step 4: Wait for CI green and auto-merge**

Run:

```bash
gh pr merge --auto --squash
gh pr checks --watch
```

Expected: all checks green; PR squash-merged into `main`.

- [ ] **Step 5: Cleanup**

After merge, from the repo root (not the worktree):

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport
git checkout main
git pull
git worktree remove .worktrees/repo-hygiene-ai-files
git branch -d chore/NN1-repo-hygiene-ai-files
```

PR 1 done.

---

## PR 2 — uv migration

### Task 2.1: File issue and create worktree

- [ ] **Step 1: File the GitHub issue**

```bash
gh issue create \
  --title "Convention alignment PR 2: Poetry → uv migration" \
  --label type:chore \
  --body "Migrate pyproject.toml to PEP 621, replace poetry.lock with uv.lock, update Dockerfile + CI + docs. See docs/superpowers/specs/2026-05-21-convention-alignment-design.md § PR 2."
```

Note the issue number as `NN2`.

- [ ] **Step 2: Create the worktree**

```bash
git fetch origin main
git worktree add .worktrees/uv-migration -b chore/NN2-uv-migration origin/main
cd .worktrees/uv-migration
```

All subsequent steps run inside this worktree.

### Task 2.2: Convert `pyproject.toml` to PEP 621

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Verify uv is installed**

Run:

```bash
uv --version
```

Expected: prints a version. If missing, install via `brew install uv`.

- [ ] **Step 2: Replace the `[tool.poetry]` block with PEP 621**

Overwrite `pyproject.toml` with this exact content (preserves pytest / coverage / ruff config; replaces poetry sections with `[project]` + `[dependency-groups]` + hatchling build system):

```toml
[project]
name = "whatsapp-chat-autoexport"
version = "0.2.0"
description = "WhatsApp chat export automation for Android (Appium-driven, Google Drive, optional transcription)."
readme = "README.md"
requires-python = ">=3.13,<4.0"
authors = [
    { name = "AJ Anderson", email = "ajanderson1@gmail.com" },
]
license = { text = "MIT" }
dependencies = [
    "appium-python-client>=5.2.4,<6.0.0",
    "ipykernel>=7.1.0,<8.0.0",
    "colorama>=0.4.6,<1.0.0",
    "google-api-python-client>=2.100.0,<3.0.0",
    "google-auth-httplib2>=0.2.0,<1.0.0",
    "google-auth-oauthlib>=1.1.0,<2.0.0",
    "tqdm>=4.66.0,<5.0.0",
    "openai>=1.0.0,<2.0.0",
    "elevenlabs>=1.0.0,<2.0.0",
    "pydantic-settings>=2.12.0,<3.0.0",
    "python-dotenv>=1.1.0,<2.0.0",
    "httpx>=0.28.1,<1.0.0",
    "pyyaml>=6.0.3,<7.0.0",
    "rich>=14.3.1,<15.0.0",
    "typer>=0.21.1,<1.0.0",
    "textual>=0.94.0",
]

[project.scripts]
whatsapp = "whatsapp_chat_autoexport.cli_entry:main"
whatsapp-export = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_export_main"
whatsapp-process = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_process_main"
whatsapp-drive = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_drive_main"
whatsapp-pipeline = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_pipeline_main"
whatsapp-logs = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_logs_main"
whatsapp-sync = "whatsapp_chat_autoexport.cli.commands.sync:main"
whatsapp-ingest = "whatsapp_chat_autoexport.cli.commands.ingest:main"
whatsapp-migrate = "whatsapp_chat_autoexport.cli.commands.migrate:main"
whatsapp-rebuild = "whatsapp_chat_autoexport.cli.commands.rebuild:main"

[dependency-groups]
dev = [
    "pytest>=7.4.0,<8.0.0",
    "pytest-cov>=4.1.0,<5.0.0",
    "pytest-mock>=3.11.1,<4.0.0",
    "pytest-timeout>=2.1.0,<3.0.0",
    "pytest-asyncio>=0.23,<1.0.0",
    "ruff>=0.11,<1.0.0",
]

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["whatsapp_chat_autoexport"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--strict-markers",
    "--tb=short",
    "--cov=whatsapp_chat_autoexport",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-fail-under=0",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "requires_api: marks tests that require API keys",
    "requires_device: marks tests that require an Android device",
    "requires_drive: marks tests that require live Google Drive credentials and the fixture folder env var",
    "unit: marks tests as unit tests",
    "manual: marks tests that must be run by a human with real credentials (skipped in CI)",
]
timeout = 300
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["whatsapp_chat_autoexport"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/site-packages/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]

[tool.ruff]
target-version = "py313"
line-length = 120

[tool.ruff.lint]
select = [
    "E",
    "W",
    "F",
    "I",
    "B",
    "UP",
]
ignore = [
    "E501",
    "B008",
]

[tool.ruff.lint.isort]
known-first-party = ["whatsapp_chat_autoexport"]
```

(Note: `[tool.hatch.build.targets.wheel]` still points at `whatsapp_chat_autoexport` — the `src/` move happens in PR 3, where this is updated.)

- [ ] **Step 3: Delete `poetry.lock`**

```bash
rm poetry.lock
```

- [ ] **Step 4: Generate `uv.lock`**

```bash
uv lock
```

Expected: produces `uv.lock` and reports the resolved package count. Watch for downgrades of `textual`, `appium-python-client`, `openai`, `elevenlabs` — if any drop a major version, **halt** and surface to the user.

- [ ] **Step 5: Verify the package installs and entry points work**

```bash
uv sync --all-extras
uv run whatsapp --help
```

Expected: `whatsapp --help` prints the CLI help text.

- [ ] **Step 6: Run the test suite**

```bash
uv sync --all-extras --dev
uv run pytest -m "not requires_api and not requires_device and not requires_drive"
```

Expected: green, matching the `main` test count.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock
git rm poetry.lock
git commit -m "chore(build): migrate pyproject.toml from Poetry to uv (PEP 621)"
```

### Task 2.3: Update Dockerfile

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Read current Dockerfile**

```bash
cat Dockerfile
```

Identify the Poetry install/run steps.

- [ ] **Step 2: Replace Poetry steps with uv**

In `Dockerfile`, find any line installing Poetry (e.g. `pip install poetry`) and any `poetry install …` / `poetry run …` invocation. Replace with:

- `pip install --no-cache-dir uv` (in place of `pip install poetry`)
- `uv sync --frozen --no-dev` (in place of `poetry install --no-dev` / `--without dev` / `--only main` / `poetry install`)
- The entry point line stays as-is if it already uses `whatsapp`; otherwise change `ENTRYPOINT ["poetry", "run", "whatsapp", "--headless"]` → `ENTRYPOINT ["whatsapp", "--headless"]` (the installed script is on PATH after `uv sync`).

Copy semantics matter: `pyproject.toml` and `uv.lock` must be copied into the image **before** `uv sync` runs, and the package source copied after, to keep layer cache effective.

A canonical structure to land on (adapt to the existing file's stage / base image / system-package layers, do not blindly overwrite):

```dockerfile
# Build / install layer
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

# Package source
COPY whatsapp_chat_autoexport ./whatsapp_chat_autoexport
RUN uv sync --frozen --no-dev  # re-runs to pick up the package itself

ENTRYPOINT ["whatsapp", "--headless"]
```

- [ ] **Step 3: Build the image and smoke-test**

```bash
docker build -t whatsapp-export:uv-migration .
docker run --rm --entrypoint whatsapp whatsapp-export:uv-migration --help
```

Expected: build succeeds; `whatsapp --help` prints inside the container.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "chore(docker): switch Dockerfile from Poetry to uv"
```

### Task 2.4: Update CI workflow

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Replace Poetry install with `astral-sh/setup-uv`**

Edit `.github/workflows/test.yml`. Replace the existing `Install Poetry` + `Install dependencies` steps with:

```yaml
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --all-extras --dev
```

Change the test step from `poetry run pytest …` to `uv run pytest …`:

```yaml
      - name: Run tests
        run: uv run pytest --cov=whatsapp_chat_autoexport --cov-report=xml -m "not requires_api and not requires_device and not requires_drive"
```

The `actions/setup-python@v5` step stays — uv uses the system Python by default but a pinned setup is fine.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "chore(ci): swap Poetry for uv in test workflow"
```

### Task 2.5: Update docs and AGENTS.md commands

**Files:**
- Modify: `docs/internals/architecture.md`, `README.md`, `QUICKSTART.md`, `README.Docker.md`, `AGENTS.md`

- [ ] **Step 1: Sed-replace `poetry run` → `uv run` across the docs**

Run (use `gsed` if `sed -i` complains on macOS; otherwise install GNU sed via `brew install gnu-sed`):

```bash
for f in docs/internals/architecture.md README.md QUICKSTART.md README.Docker.md; do
  test -f "$f" || continue
  sed -i.bak \
    -e 's|poetry run |uv run |g' \
    -e 's|poetry install --with dev|uv sync --all-extras --dev|g' \
    -e 's|poetry install|uv sync|g' \
    -e 's|poetry add |uv add |g' \
    "$f"
  rm "$f.bak"
done
```

- [ ] **Step 2: Manual scan for any remaining `poetry`/`Poetry` references**

```bash
grep -n -E "poetry|Poetry" docs/internals/architecture.md README.md QUICKSTART.md README.Docker.md || echo "clean"
```

Expected: any remaining hits are either historical / narrative ("This project migrated from Poetry to uv on 2026-05-21" is fine) or section headings to manually fix. Update inline.

- [ ] **Step 3: Update AGENTS.md canonical commands**

Edit the `## Canonical commands` block in `AGENTS.md`:

```markdown
## Canonical commands
- dev: n/a
- build: `docker build -t whatsapp-export .`
- test: `uv run pytest`
- lint: `uv run ruff check .`
- format: `uv run ruff format .`
- typecheck: n/a
```

Then add to the `## Stack constraints` block (currently empty):

```markdown
## Stack constraints (overrides global defaults)
<!-- Empty — project follows global defaults. -->
```

(uv is now the global default, so no constraint entry is needed.)

- [ ] **Step 4: Commit**

```bash
git add docs/internals/architecture.md README.md QUICKSTART.md README.Docker.md AGENTS.md
git commit -m "docs: replace poetry commands with uv equivalents"
```

### Task 2.6: Push, open PR, merge on green

- [ ] **Step 1: Final local check**

```bash
uv sync --all-extras --dev
uv run pytest -m "not requires_api and not requires_device and not requires_drive"
docker build -t whatsapp-export:uv-final .
```

All three must succeed.

- [ ] **Step 2: Push the branch**

```bash
git push -u origin chore/NN2-uv-migration
```

- [ ] **Step 3: Open the PR**

```bash
gh pr create --title "chore: migrate Poetry → uv (convention alignment PR 2/5)" --body "$(cat <<'EOF'
## Summary
- `pyproject.toml` rewritten to PEP 621 (`[project]` + `[dependency-groups]`), hatchling build backend.
- `poetry.lock` deleted, `uv.lock` added.
- Dockerfile switched from `pip install poetry` + `poetry install` to `pip install uv` + `uv sync --frozen --no-dev`.
- CI workflow switched from Poetry to `astral-sh/setup-uv@v3` + `uv sync` + `uv run pytest`.
- Docs & AGENTS.md commands swept from `poetry run` to `uv run`.

Closes #NN2.

Spec: `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` § PR 2.

## Test plan
- [x] `uv sync --all-extras --dev` succeeds locally.
- [x] `uv run pytest -m "not requires_api and not requires_device and not requires_drive"` matches pre-PR count.
- [x] `uv run whatsapp --help` prints CLI help.
- [x] `docker build -t whatsapp-export .` succeeds.
- [x] CI green.
EOF
)"
```

- [ ] **Step 4: Wait for CI and auto-merge**

```bash
gh pr merge --auto --squash
gh pr checks --watch
```

- [ ] **Step 5: Cleanup**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport
git checkout main && git pull
git worktree remove .worktrees/uv-migration
git branch -d chore/NN2-uv-migration
```

PR 2 done.

---

## PR 3 — `src/` layout

### Task 3.1: File issue and create worktree

- [ ] **Step 1: File the GitHub issue**

```bash
gh issue create \
  --title "Convention alignment PR 3: src/ layout" \
  --label type:chore \
  --body "Move whatsapp_chat_autoexport/ → src/whatsapp_chat_autoexport/, update build config + coverage path, clean stray log/XML files. See docs/superpowers/specs/2026-05-21-convention-alignment-design.md § PR 3."
```

Note the issue number as `NN3`.

- [ ] **Step 2: Create the worktree**

```bash
git fetch origin main
git worktree add .worktrees/src-layout -b chore/NN3-src-layout origin/main
cd .worktrees/src-layout
```

### Task 3.2: Clean stray log/XML files from inside the package

**Files:**
- Delete: `whatsapp_chat_autoexport/export_log.txt`, `whatsapp_chat_autoexport/export_error_*.xml`, `whatsapp_chat_autoexport/google_drive_error_*.xml`
- Also delete from repo root if tracked: `google_drive_error_Tim Cocking.xml`, `EXECUTIVE_SUMMARY.md` (already gitignored but check if any are tracked).

- [ ] **Step 1: List the stray files**

```bash
ls whatsapp_chat_autoexport/*.txt whatsapp_chat_autoexport/*.xml 2>/dev/null
git ls-files whatsapp_chat_autoexport/ | grep -E "\.(txt|xml)$"
```

- [ ] **Step 2: Remove tracked stray files**

```bash
git rm whatsapp_chat_autoexport/export_log.txt 2>/dev/null
git rm "whatsapp_chat_autoexport/export_error_+46 76 553 11 97.xml" 2>/dev/null
git rm "whatsapp_chat_autoexport/google_drive_error_+971 56 241 0291.xml" 2>/dev/null
git rm "google_drive_error_Tim Cocking.xml" 2>/dev/null
```

Use the exact filenames git reports — quote any with spaces or special characters.

- [ ] **Step 3: Verify no remaining stray files inside the package**

```bash
git ls-files whatsapp_chat_autoexport/ | grep -vE "\.py$|\.tcss$" || echo "package contains only .py / .tcss"
```

Expected: only Python and Textual style files remain. If any non-code files remain (e.g. a real fixture), leave them.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove stray log/XML files from inside the package"
```

### Task 3.3: Move package into `src/`

**Files:**
- Move: `whatsapp_chat_autoexport/` → `src/whatsapp_chat_autoexport/`

- [ ] **Step 1: Create `src/` and move the package**

```bash
mkdir -p src
git mv whatsapp_chat_autoexport src/whatsapp_chat_autoexport
```

- [ ] **Step 2: Verify history is preserved**

```bash
git log --follow -1 -- src/whatsapp_chat_autoexport/cli_entry.py
```

Expected: shows commits from the pre-move history.

- [ ] **Step 3: Commit the move on its own**

```bash
git commit -m "chore: move package to src/ layout"
```

(Separate commit from the build-config update so the move shows cleanly in `git log`.)

### Task 3.4: Update `pyproject.toml` build + coverage paths

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update the hatchling packages path**

Edit the `[tool.hatch.build.targets.wheel]` block:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/whatsapp_chat_autoexport"]
```

- [ ] **Step 2: Update coverage source**

Edit `[tool.coverage.run]`:

```toml
[tool.coverage.run]
source = ["src/whatsapp_chat_autoexport"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/site-packages/*",
]
```

- [ ] **Step 3: Sync and run the test suite**

```bash
uv sync --all-extras --dev
uv run pytest -m "not requires_api and not requires_device and not requires_drive"
```

Expected: same green count as `main` (modulo the stray-file-removal commit). If any test fails on an import-path or fixture-path issue, fix inline (likely `tests/conftest.py` or any test that uses a literal `whatsapp_chat_autoexport/` path).

- [ ] **Step 4: Verify the CLI still works**

```bash
uv run whatsapp --help
```

Expected: CLI help text prints.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/ 2>/dev/null
git commit -m "chore(build): point hatchling + coverage at src/ layout"
```

### Task 3.5: Update path references in mkdocs and architecture doc

**Files:**
- Modify: `mkdocs.yml` (if it references the package path)
- Modify: `docs/internals/architecture.md` (file-tree diagram)
- Modify: `Dockerfile` (the `COPY whatsapp_chat_autoexport …` line)

- [ ] **Step 1: Audit mkdocs.yml**

```bash
grep -nE "whatsapp_chat_autoexport|paths" mkdocs.yml
```

If `mkdocs.yml` references the package path (e.g. mkdocstrings `paths:`), update to `paths: [src]` or `src/whatsapp_chat_autoexport`. If no such reference, skip.

- [ ] **Step 2: Update Dockerfile COPY paths**

Edit `Dockerfile`. Change:

```dockerfile
COPY whatsapp_chat_autoexport ./whatsapp_chat_autoexport
```

to:

```dockerfile
COPY src ./src
```

Rebuild to confirm:

```bash
docker build -t whatsapp-export:src-layout .
docker run --rm --entrypoint whatsapp whatsapp-export:src-layout --help
```

- [ ] **Step 3: Update the file-tree diagram in `docs/internals/architecture.md`**

Search for the `whatsapp_chat_autoexport/` block under `## File Organization`. Update the heading line and any internal paths to reflect `src/whatsapp_chat_autoexport/`.

- [ ] **Step 4: Update AGENTS.md "where things live" entry**

In `AGENTS.md`, change:

```markdown
- `whatsapp_chat_autoexport/` — main package (moves to `src/whatsapp_chat_autoexport/` in a later PR).
```

to:

```markdown
- `src/whatsapp_chat_autoexport/` — main package.
```

- [ ] **Step 5: Commit**

```bash
git add mkdocs.yml Dockerfile docs/internals/architecture.md AGENTS.md
git commit -m "docs: update path references for src/ layout"
```

### Task 3.6: Push, open PR, merge on green

- [ ] **Step 1: Final local check**

```bash
uv sync --all-extras --dev
uv run pytest -m "not requires_api and not requires_device and not requires_drive"
uv run whatsapp --help
docker build -t whatsapp-export:src-final .
```

All four must succeed.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin chore/NN3-src-layout
gh pr create --title "chore: move package to src/ layout (convention alignment PR 3/5)" --body "$(cat <<'EOF'
## Summary
- `git mv whatsapp_chat_autoexport src/whatsapp_chat_autoexport` (history preserved).
- `pyproject.toml`: hatchling `packages` and `[tool.coverage.run] source` repointed to `src/whatsapp_chat_autoexport`.
- Dockerfile, mkdocs config, AGENTS.md, architecture doc updated for new path.
- Stray log/XML files cleaned out of the package directory in a prior commit.

Closes #NN3.

Spec: `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` § PR 3.

## Test plan
- [x] `uv run pytest -m "not requires_api and not requires_device and not requires_drive"` matches pre-PR count.
- [x] `uv run whatsapp --help` works.
- [x] `docker build` succeeds and runs `whatsapp --help` inside the container.
- [x] `git log --follow src/whatsapp_chat_autoexport/cli_entry.py` shows pre-move history.
EOF
)"
```

- [ ] **Step 3: Wait for CI and auto-merge**

```bash
gh pr merge --auto --squash
gh pr checks --watch
```

- [ ] **Step 4: Cleanup**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport
git checkout main && git pull
git worktree remove .worktrees/src-layout
git branch -d chore/NN3-src-layout
```

PR 3 done.

---

## PR 4 — Lefthook + mypy + verify.sh

### Task 4.1: File issue and create worktree

- [ ] **Step 1: File the issue**

```bash
gh issue create \
  --title "Convention alignment PR 4: lefthook + mypy + verify.sh" \
  --label type:chore \
  --body "Add lefthook pre-commit cascade (format → lint → typecheck → secret-scan), mypy --strict with per-module overrides, and verify.sh entrypoint. See docs/superpowers/specs/2026-05-21-convention-alignment-design.md § PR 4."
```

Note the issue number as `NN4`.

- [ ] **Step 2: Create the worktree**

```bash
git fetch origin main
git worktree add .worktrees/lefthook-mypy-verify -b chore/NN4-lefthook-mypy-verify origin/main
cd .worktrees/lefthook-mypy-verify
```

### Task 4.2: Add mypy with strict + per-module overrides

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add mypy to dev deps**

In `pyproject.toml`, append to the `dev` dependency group:

```toml
[dependency-groups]
dev = [
    # ... existing entries unchanged ...
    "mypy>=1.11,<2.0",
]
```

- [ ] **Step 2: Add `[tool.mypy]` config with strict mode**

Append to `pyproject.toml`:

```toml
[tool.mypy]
strict = true
python_version = "3.13"
packages = ["whatsapp_chat_autoexport"]
mypy_path = "src"
exclude = [
    "tests/",
    "build/",
    "dist/",
]

# Per-module overrides for legacy / noisy modules.
# Goal: each entry is a TODO — remove the override and type-clean the module over time.
[[tool.mypy.overrides]]
module = "whatsapp_chat_autoexport.whatsapp_export"
ignore_errors = true

[[tool.mypy.overrides]]
module = "whatsapp_chat_autoexport.whatsapp_process"
ignore_errors = true

[[tool.mypy.overrides]]
module = "whatsapp_chat_autoexport.legacy.*"
ignore_errors = true

[[tool.mypy.overrides]]
module = "whatsapp_chat_autoexport.tui.*"
ignore_errors = true

# Third-party modules without stubs — silence missing-imports for these only.
[[tool.mypy.overrides]]
module = [
    "appium.*",
    "selenium.*",
    "elevenlabs.*",
    "google.*",
    "googleapiclient.*",
    "google_auth_oauthlib.*",
    "google_auth_httplib2.*",
    "colorama",
    "textual.*",
    "rich.*",
    "tqdm",
    "typer",
    "pydantic_settings",
]
ignore_missing_imports = true
```

- [ ] **Step 3: Run mypy and react**

```bash
uv sync --all-extras --dev
uv run mypy src/whatsapp_chat_autoexport
```

Three outcomes:
- **Exit 0:** great. Move on.
- **Errors only in modules already in the override list:** the override block isn't applying — check module-name spelling and that `mypy_path = "src"` is set.
- **Errors in non-override modules (e.g. `pipeline.py`, `headless.py`, `cli_entry.py`):** review case by case. If it's a real bug (wrong return type that masks a runtime issue), **halt** and surface. If it's type noise (missing annotations on internal helpers), add a focused override for that module with a comment `# TODO: type-clean and remove override`, OR fix inline if the fix is small.

The goal of this step is `uv run mypy src/whatsapp_chat_autoexport` exit 0 so the lefthook can be enabled. Tightening is a follow-up effort.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(typecheck): add mypy --strict with per-module overrides for legacy modules"
```

### Task 4.3: Add `lefthook.yml`

**Files:**
- Create: `lefthook.yml`

- [ ] **Step 1: Verify lefthook is installed locally**

```bash
lefthook --version
```

Expected: prints a version. If missing, install via `brew install lefthook`.

- [ ] **Step 2: Write `lefthook.yml`**

Create `lefthook.yml` at repo root:

```yaml
# Pre-commit cascade — order matches ~/.conventions/conventions/ci.md
# 1. Formatter (auto-fix, doesn't block)
# 2. Linter (blocks)
# 3. Type check (blocks)
# 4. Secret scan (blocks)

pre-commit:
  parallel: false  # cascade order matters; run sequentially
  commands:
    1-format:
      glob: "*.{py}"
      run: uv run ruff format {staged_files}
      stage_fixed: true

    2-lint:
      glob: "*.{py}"
      run: uv run ruff check --fix {staged_files}
      stage_fixed: true

    3-typecheck:
      glob: "*.{py}"
      # mypy needs the full module graph, not staged files — operate on the package.
      run: uv run mypy src/whatsapp_chat_autoexport

    4-secret-scan:
      run: gitleaks protect --staged --no-banner --redact
      # If gitleaks isn't installed, lefthook skips gracefully with a warning.
      skip:
        - run: which gitleaks > /dev/null
          name: gitleaks-missing
          message: "gitleaks not installed — skipping secret scan. Install via 'brew install gitleaks'."
```

- [ ] **Step 3: Install hooks into `.git/hooks/`**

```bash
lefthook install
```

Expected: prints "Hooks installed".

- [ ] **Step 4: Smoke-test the hook**

Make a trivial whitespace-only change to a file in `src/`, stage it, and try to commit:

```bash
echo "" >> src/whatsapp_chat_autoexport/__init__.py
git add src/whatsapp_chat_autoexport/__init__.py
git commit -m "test: lefthook smoke" --dry-run
```

Expected: the cascade runs, ruff format auto-fixes the trailing whitespace, ruff check passes, mypy passes, gitleaks runs (or skips with a message). Then `git restore --staged src/whatsapp_chat_autoexport/__init__.py && git checkout src/whatsapp_chat_autoexport/__init__.py` to undo the smoke change.

- [ ] **Step 5: Commit `lefthook.yml`**

```bash
git add lefthook.yml
git commit -m "chore(hooks): add lefthook pre-commit cascade"
```

### Task 4.4: Add `verify.sh`

**Files:**
- Create: `verify.sh` (executable)

- [ ] **Step 1: Write `verify.sh`**

Create `verify.sh` at repo root with this content:

```bash
#!/usr/bin/env bash
# Local verification entry point. Mirrors the pre-commit cascade plus pytest.
# Per ~/.conventions/conventions/ci.md § verify.sh contract:
#   - exit 0 = pass
#   - artifacts written to $ARTIFACTS_DIR (set by the harness; defaults below)

set -euo pipefail

: "${ARTIFACTS_DIR:=assets/verification/local}"
mkdir -p "$ARTIFACTS_DIR"

echo "→ ruff format --check"
uv run ruff format --check . | tee "$ARTIFACTS_DIR/01-format.log"

echo "→ ruff check"
uv run ruff check . | tee "$ARTIFACTS_DIR/02-lint.log"

echo "→ mypy src/whatsapp_chat_autoexport"
uv run mypy src/whatsapp_chat_autoexport | tee "$ARTIFACTS_DIR/03-typecheck.log"

if command -v gitleaks > /dev/null; then
    echo "→ gitleaks detect"
    gitleaks detect --no-banner --redact | tee "$ARTIFACTS_DIR/04-secret-scan.log"
else
    echo "→ gitleaks not installed — skipping (install via 'brew install gitleaks')"
fi

echo "→ pytest (no API / device / drive tests)"
uv run pytest -m "not requires_api and not requires_device and not requires_drive" \
    | tee "$ARTIFACTS_DIR/05-pytest.log"

echo
echo "✓ verify.sh passed. Artifacts in $ARTIFACTS_DIR/"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x verify.sh
```

- [ ] **Step 3: Run it**

```bash
./verify.sh
```

Expected: exits 0, all five stages green (or four if gitleaks is missing locally — that's fine for the smoke test, CI will still run it).

- [ ] **Step 4: Update AGENTS.md typecheck command**

In `AGENTS.md`, change the `## Canonical commands` block's `typecheck` line:

```markdown
- typecheck: `uv run mypy src/whatsapp_chat_autoexport`
```

And add a `verify` line:

```markdown
- verify: `./verify.sh`
```

- [ ] **Step 5: Commit**

```bash
git add verify.sh AGENTS.md
git commit -m "chore: add verify.sh and document in AGENTS.md"
```

### Task 4.5: Push, open PR, merge on green

- [ ] **Step 1: Run verify.sh one more time on a clean tree**

```bash
./verify.sh
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin chore/NN4-lefthook-mypy-verify
gh pr create --title "chore: lefthook + mypy + verify.sh (convention alignment PR 4/5)" --body "$(cat <<'EOF'
## Summary
- Added `mypy --strict` with `[[tool.mypy.overrides]]` for legacy modules (`whatsapp_export`, `whatsapp_process`, `legacy.*`, `tui.*`) and third-party stub-less libs.
- Added `lefthook.yml` with the four-stage pre-commit cascade per `~/.conventions/conventions/ci.md`: ruff format → ruff check → mypy → gitleaks.
- Added `verify.sh` (executable) running the same cascade plus pytest; writes artifacts to `$ARTIFACTS_DIR`.
- AGENTS.md canonical commands now lists `typecheck` and `verify`.

Closes #NN4.

Spec: `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` § PR 4.

## Test plan
- [x] `uv run mypy src/whatsapp_chat_autoexport` exits 0.
- [x] `lefthook install` then trial commit runs the full cascade.
- [x] `./verify.sh` exits 0 with artifacts in `assets/verification/local/`.
- [x] Pytest count matches `main`.
EOF
)"
```

- [ ] **Step 3: Wait for CI and auto-merge**

```bash
gh pr merge --auto --squash
gh pr checks --watch
```

- [ ] **Step 4: Cleanup**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport
git checkout main && git pull
git worktree remove .worktrees/lefthook-mypy-verify
git branch -d chore/NN4-lefthook-mypy-verify
```

PR 4 done.

---

## PR 5 — CI + release-please + dependabot

### Task 5.1: File issue, create worktree, verify repo permissions

- [ ] **Step 1: File the issue**

```bash
gh issue create \
  --title "Convention alignment PR 5: CI + release-please + dependabot" \
  --label type:chore \
  --body "Split test.yml into multi-job ci.yml (lint/typecheck/test/secret-scan), add release-please workflow + config + manifest, add dependabot.yml, ensure default labels exist. See docs/superpowers/specs/2026-05-21-convention-alignment-design.md § PR 5."
```

Note the issue number as `NN5`.

- [ ] **Step 2: Create the worktree**

```bash
git fetch origin main
git worktree add .worktrees/ci-release-dependabot -b chore/NN5-ci-release-dependabot origin/main
cd .worktrees/ci-release-dependabot
```

- [ ] **Step 3: Verify repo has `contents: write` permission for Actions**

```bash
gh api repos/:owner/:repo --jq '.permissions, .default_branch'
gh api repos/:owner/:repo/actions/permissions --jq '.'
```

Expected: `contents: write` is on, default workflow permissions allow writing. If `default_workflow_permissions` is `read`, the release-please workflow will fail silently. **Halt** and ask AJ to flip the setting via repo Settings → Actions → General → Workflow permissions → "Read and write permissions".

### Task 5.2: Expand CI workflow

**Files:**
- Move/Modify: `.github/workflows/test.yml` → `.github/workflows/ci.yml`

- [ ] **Step 1: Rename the file**

```bash
git mv .github/workflows/test.yml .github/workflows/ci.yml
```

- [ ] **Step 2: Rewrite `ci.yml` with four parallel jobs**

Overwrite `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --all-extras --dev
      - name: ruff format --check
        run: uv run ruff format --check .
      - name: ruff check
        run: uv run ruff check .

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --all-extras --dev
      - name: mypy
        run: uv run mypy src/whatsapp_chat_autoexport

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --all-extras --dev
      - name: Run tests
        run: uv run pytest --cov=whatsapp_chat_autoexport --cov-report=xml -m "not requires_api and not requires_device and not requires_drive"
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          fail_ci_if_error: false

  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: Update README CI badge URL**

```bash
grep -n "test.yml\|workflows/test" README.md
```

Replace any badge URL referring to `test.yml` with `ci.yml`. Example:

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "chore(ci): split test.yml into multi-job ci.yml (lint/typecheck/test/secret-scan)"
```

### Task 5.3: Add release-please

**Files:**
- Create: `.github/workflows/release-please.yml`
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/release-please.yml`:

```yaml
name: release-please

on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    steps:
      - uses: googleapis/release-please-action@v4
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
```

- [ ] **Step 2: Write release-please config**

Create `release-please-config.json`:

```json
{
  "release-type": "python",
  "packages": {
    ".": {
      "package-name": "whatsapp-chat-autoexport",
      "bump-minor-pre-major": true,
      "bump-patch-for-minor-pre-major": false,
      "include-component-in-tag": false
    }
  }
}
```

- [ ] **Step 3: Write the manifest**

Create `.release-please-manifest.json`:

```json
{
  ".": "0.2.0"
}
```

The version `0.2.0` matches the current `[project].version` in `pyproject.toml`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release-please.yml release-please-config.json .release-please-manifest.json
git commit -m "chore: add release-please for Conventional-Commits-driven versioning"
```

### Task 5.4: Add Dependabot config

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Write dependabot config**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "type:chore"
    commit-message:
      prefix: "chore"
      include: "scope"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    labels:
      - "type:chore"
    commit-message:
      prefix: "chore"
      include: "scope"
```

- [ ] **Step 2: Commit**

```bash
git add .github/dependabot.yml
git commit -m "chore: add Dependabot for pip + github-actions, weekly"
```

### Task 5.5: Ensure default GitHub labels exist

- [ ] **Step 1: List existing labels**

```bash
gh label list
```

- [ ] **Step 2: Create any missing convention labels**

For each label in the table below that's not present, create it:

| Label | Colour | Description |
|---|---|---|
| `type:feat` | `84b6eb` | Feature work |
| `type:fix` | `e11d21` | Bug fixes |
| `type:chore` | `cccccc` | Tooling / refactor / maintenance |
| `type:docs` | `c7def8` | Docs-only changes |

Example creation command:

```bash
gh label create "type:feat"  --color "84b6eb" --description "Feature work"               || true
gh label create "type:fix"   --color "e11d21" --description "Bug fixes"                  || true
gh label create "type:chore" --color "cccccc" --description "Tooling / refactor / maintenance" || true
gh label create "type:docs"  --color "c7def8" --description "Docs-only changes"          || true
```

(`|| true` tolerates the case where a label already exists.)

This step is not committed — it's a GitHub API side effect.

### Task 5.6: Push, open PR, merge on green

- [ ] **Step 1: Final local check**

```bash
./verify.sh
```

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin chore/NN5-ci-release-dependabot
gh pr create --title "chore: CI + release-please + dependabot (convention alignment PR 5/5)" --body "$(cat <<'EOF'
## Summary
- `.github/workflows/test.yml` renamed to `ci.yml` and split into four parallel jobs: lint (ruff format + check), typecheck (mypy), test (pytest + codecov), secret-scan (gitleaks-action).
- `release-please` wired up via `googleapis/release-please-action@v4` (`release-type: python`, manifest pinned at 0.2.0). Opens a release PR on every push to `main`.
- Dependabot configured for `pip` and `github-actions`, weekly, labelled `type:chore`.
- Default GitHub labels (`type:feat`, `type:fix`, `type:chore`, `type:docs`) created/verified.

Closes #NN5. Last of the convention-alignment train.

Spec: `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` § PR 5.

## Test plan
- [x] All four CI jobs green on this PR.
- [x] Repo permissions verified: `contents: write` and `pull-requests: write` for Actions.
- [x] After merge, expect release-please to open a release PR within ~5 minutes (will be verified post-merge).
- [x] `./verify.sh` passes locally.
EOF
)"
```

- [ ] **Step 3: Wait for CI and auto-merge**

```bash
gh pr merge --auto --squash
gh pr checks --watch
```

- [ ] **Step 4: Cleanup**

```bash
cd /Users/ajanderson/GitHub/projects/whatsapp_chat_autoexport
git checkout main && git pull
git worktree remove .worktrees/ci-release-dependabot
git branch -d chore/NN5-ci-release-dependabot
```

- [ ] **Step 5: Verify release-please opened a release PR**

Wait ~5 minutes, then:

```bash
gh pr list --label "autorelease: pending"
```

Expected: one open PR titled something like `chore(main): release 0.3.0` (or similar bump). No action needed — leaving it open is correct; AJ merges it when ready to cut a tag.

PR 5 done. Train complete.

---

## Post-train verification

- [ ] `AGENTS.md` ≤ 50 lines and matches the template from `git.md`.
- [ ] `readlink CLAUDE.md` returns `AGENTS.md`.
- [ ] `pyproject.toml` is PEP 621 (`[project]` block, no `[tool.poetry]`).
- [ ] `src/whatsapp_chat_autoexport/` exists; no `whatsapp_chat_autoexport/` at repo root.
- [ ] `lefthook.yml`, `verify.sh`, `release-please-config.json`, `.release-please-manifest.json`, `.github/dependabot.yml` all present.
- [ ] `.github/workflows/ci.yml` runs four jobs; `release-please.yml` exists.
- [ ] `./verify.sh` exits 0.
- [ ] `uv run pytest -m "not requires_api and not requires_device and not requires_drive"` green.
- [ ] `docker build && docker run --entrypoint whatsapp <image> --help` works.

Update the project note at `/Users/ajanderson/Journal/Atlas/Whatsapp Chat AutoExport.md` with a one-line summary of what landed.
