# CLI Cleanup & Subcommand Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flag-triggered modes with subcommands (`whatsapp run`, `whatsapp pipeline`, default TUI), add a TOML config file for user defaults, and remove redundant/legacy/phantom flags.

**Architecture:** Split `cli_entry.py` into a thin top-level dispatcher plus per-subcommand modules under `whatsapp_chat_autoexport/cli/subcommands/`. A new `cli/config.py` provides a TOML loader with a documented precedence chain (parser default < user config < project config < env < CLI flag). The existing `headless.py` orchestrators are left intact and called from the subcommand modules — phantom `getattr` calls become explicit attribute reads. TUI defaults read the same config via the new loader. One-release deprecation window keeps `--headless` and `--pipeline-only` flags working with a stderr warning.

**Tech Stack:** Python 3.13+, `argparse` with subparsers, `tomllib` (stdlib, read-only), Textual (unchanged), `pytest` (out of scope).

**Spec:** `docs/superpowers/specs/2026-04-29-cli-cleanup-design.md`

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `whatsapp_chat_autoexport/cli/__init__.py` | Marker for the cli package (already exists; will be expanded). |
| `whatsapp_chat_autoexport/cli/config.py` | Config dataclass + TOML loader + `apply_to_args()` precedence merger. |
| `whatsapp_chat_autoexport/cli/subcommands/__init__.py` | Re-exports subcommand registrars. |
| `whatsapp_chat_autoexport/cli/subcommands/tui.py` | `whatsapp` (no subcommand) → `run_tui()`. |
| `whatsapp_chat_autoexport/cli/subcommands/run.py` | `whatsapp run` → calls `headless.run_headless()`. |
| `whatsapp_chat_autoexport/cli/subcommands/pipeline.py` | `whatsapp pipeline SRC OUT` → calls `headless.run_pipeline_only()`. |
| `whatsapp_chat_autoexport/cli/subcommands/config_init.py` | `whatsapp config init [--force]` scaffolds `~/.config/whatsapp-autoexport/config.toml`. |
| `whatsapp_chat_autoexport/cli/templates/config.toml.template` | Default config file body with inline comments. |

### Modified files

| Path | Change |
|---|---|
| `whatsapp_chat_autoexport/cli_entry.py` | Replaced with subparsers + deprecation shim for `--headless` / `--pipeline-only`. |
| `whatsapp_chat_autoexport/headless.py` | Phantom `getattr` calls replaced with explicit attribute reads from a typed namespace; constants inlined for the six removed-flag defaults. |
| `whatsapp_chat_autoexport/tui/textual_app.py` | Add a `c` keybinding that opens the user config in `$EDITOR`. The constructor signature is **unchanged** — config defaults are merged into args before `WhatsAppExporterApp` is constructed. |
| `pyproject.toml` | 5 deprecated entry points removed; `whatsapp` entry point unchanged. |

### Deleted files

| Path | Reason |
|---|---|
| `whatsapp_chat_autoexport/deprecated_entry.py` | Tied to the 5 removed entry points. |

---

## Tasks

### Task 1: Create CliConfig dataclass + TOML loader

**Files:**
- Create: `whatsapp_chat_autoexport/cli/config.py`

- [ ] **Step 1: Verify the cli package directory exists**

Run: `ls whatsapp_chat_autoexport/cli/`
Expected: `__init__.py`, `commands/` directory listed (existing MCP sync CLI structure).

- [ ] **Step 2: Create `cli/config.py` with the loader**

Write to `whatsapp_chat_autoexport/cli/config.py`:

```python
"""TOML config loader for the whatsapp CLI.

Resolution order (low → high precedence):
  1. Parser defaults (handled by argparse)
  2. User config:    $XDG_CONFIG_HOME/whatsapp-autoexport/config.toml
                     or ~/.config/whatsapp-autoexport/config.toml
  3. Project config: ./.whatsapp-autoexport.toml
  4. Environment variables (handled elsewhere — not in scope here)
  5. Explicit CLI flags (handled by argparse)

This module loads (2) and (3) and exposes a `CliConfig` dataclass that
subcommand modules use to fill in defaults *before* parsing CLI flags.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_FILENAME = "config.toml"
CONFIG_DIRNAME = "whatsapp-autoexport"
PROJECT_CONFIG_FILENAME = ".whatsapp-autoexport.toml"


def _user_config_path() -> Path:
    """Return the user-level config path following XDG conventions."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / CONFIG_DIRNAME / CONFIG_FILENAME


def _project_config_path(start: Optional[Path] = None) -> Path:
    """Return the project-level config path (cwd-relative)."""
    return (start or Path.cwd()) / PROJECT_CONFIG_FILENAME


@dataclass
class CliConfig:
    """User-level CLI defaults loaded from TOML.

    Every field maps 1:1 to a CLI flag. ``None`` means "no override —
    use the parser default."
    """

    # [defaults] section
    transcription_provider: Optional[str] = None
    output_media: Optional[bool] = None       # maps to --no-output-media (inverted)
    delete_from_drive: Optional[bool] = None
    wireless_adb: Optional[bool] = None
    auto_select: Optional[bool] = None

    # [paths] section
    output: Optional[str] = None

    # Tracks which fields were sourced from a config file (for --help annotation)
    sourced_from_config: Dict[str, Path] = field(default_factory=dict)

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "CliConfig":
        """Load config, merging user → project → explicit (highest wins)."""
        cfg = cls()
        for path in cls._candidate_paths(explicit_path):
            if path.is_file():
                cfg._merge(path)
        return cfg

    @staticmethod
    def _candidate_paths(explicit: Optional[Path]) -> list[Path]:
        if explicit is not None:
            return [explicit]
        return [_user_config_path(), _project_config_path()]

    def _merge(self, path: Path) -> None:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        defaults = data.get("defaults", {})
        paths = data.get("paths", {})

        for key in (
            "transcription_provider", "output_media",
            "delete_from_drive", "wireless_adb", "auto_select",
        ):
            if key in defaults:
                setattr(self, key, defaults[key])
                self.sourced_from_config[key] = path

        if "output" in paths:
            self.output = paths["output"]
            self.sourced_from_config["output"] = path

    def to_argparse_defaults(self) -> Dict[str, Any]:
        """Map config fields to argparse dest names, skipping None."""
        out: Dict[str, Any] = {}
        if self.transcription_provider is not None:
            out["transcription_provider"] = self.transcription_provider
        if self.output_media is not None:
            # CLI flag is --no-output-media (store_true). Config inverts.
            out["no_output_media"] = not self.output_media
        if self.delete_from_drive is not None:
            out["delete_from_drive"] = self.delete_from_drive
        if self.wireless_adb is not None:
            # Config flag is bool; CLI accepts optional IP:PORT.
            out["wireless_adb"] = True if self.wireless_adb else None
        if self.auto_select is not None:
            out["auto_select"] = self.auto_select
        if self.output is not None:
            out["output"] = self.output
        return out
```

- [ ] **Step 3: Confirm imports resolve**

Run: `poetry run python -c "from whatsapp_chat_autoexport.cli.config import CliConfig; print(CliConfig.load())"`
Expected: prints `CliConfig(transcription_provider=None, ..., sourced_from_config={})` (no errors).

- [ ] **Step 4: Commit**

```bash
git add whatsapp_chat_autoexport/cli/config.py
git commit -m "feat(cli): add CliConfig TOML loader with XDG + project-local resolution"
```

---

### Task 2: Add config template + config_init subcommand

**Files:**
- Create: `whatsapp_chat_autoexport/cli/templates/config.toml.template`
- Create: `whatsapp_chat_autoexport/cli/subcommands/__init__.py`
- Create: `whatsapp_chat_autoexport/cli/subcommands/config_init.py`

- [ ] **Step 1: Write the config template**

Write to `whatsapp_chat_autoexport/cli/templates/config.toml.template`:

```toml
# whatsapp-autoexport — user defaults
#
# Located at: ~/.config/whatsapp-autoexport/config.toml
# Project override: ./.whatsapp-autoexport.toml (loaded after user config)
# Per-run override: --config PATH
#
# Any flag passed on the command line wins over values in this file.

[defaults]
# Transcription provider: "whisper" or "elevenlabs"
transcription_provider = "whisper"

# Include media files in the final output directory
# (false = transcriptions are still produced; media is used during the run
#  but not copied to output). Equivalent to --no-output-media when false.
output_media = true

# Delete files from Google Drive after they have been processed locally
delete_from_drive = false

# Use wireless ADB by default (the CLI will still prompt for IP:PORT if needed)
wireless_adb = false

# Automatically select all chats when running headlessly
# (only meaningful for `whatsapp run`; ignored by the TUI)
auto_select = false

[paths]
# Default output directory for processed exports
# output = "/Users/you/whatsapp_exports"
```

- [ ] **Step 2: Create the subcommands package marker**

Write to `whatsapp_chat_autoexport/cli/subcommands/__init__.py`:

```python
"""Subcommand modules for the unified `whatsapp` CLI."""
```

- [ ] **Step 3: Implement `whatsapp config init`**

Write to `whatsapp_chat_autoexport/cli/subcommands/config_init.py`:

```python
"""`whatsapp config init` — scaffold a user config file."""
from __future__ import annotations

import argparse
import sys
from importlib.resources import files
from pathlib import Path

from ..config import _user_config_path


def add_subparser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "config",
        help="Manage user config (run `whatsapp config init` to scaffold).",
    )
    sub = p.add_subparsers(dest="config_action", required=True)
    init = sub.add_parser("init", help="Create a default config file.")
    init.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing config file.",
    )
    init.set_defaults(_handler=run)
    return p


def run(args: argparse.Namespace) -> int:
    target = _user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not getattr(args, "force", False):
        print(
            f"Config already exists at {target}. "
            f"Pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    template = files("whatsapp_chat_autoexport.cli.templates").joinpath(
        "config.toml.template"
    ).read_text()
    target.write_text(template)
    print(f"Wrote {target}")
    return 0
```

- [ ] **Step 4: Confirm template is included as package data**

Run: `grep -A20 'tool.poetry' pyproject.toml | grep -E "include|packages"`
Expected: project uses default poetry packaging — `.toml.template` files inside the package are picked up automatically. (If the grep returns nothing, no action needed; defaults work.)

- [ ] **Step 5: Smoke-test the template loads**

Run: `poetry run python -c "from importlib.resources import files; print(files('whatsapp_chat_autoexport.cli.templates').joinpath('config.toml.template').read_text()[:80])"`
Expected: prints the first 80 chars of the template (`# whatsapp-autoexport — user defaults...`).

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/cli/templates/ whatsapp_chat_autoexport/cli/subcommands/__init__.py whatsapp_chat_autoexport/cli/subcommands/config_init.py
git commit -m "feat(cli): add config template and \`whatsapp config init\` subcommand"
```

---

### Task 3: Extract subcommand modules (TUI, run, pipeline)

**Files:**
- Create: `whatsapp_chat_autoexport/cli/subcommands/tui.py`
- Create: `whatsapp_chat_autoexport/cli/subcommands/run.py`
- Create: `whatsapp_chat_autoexport/cli/subcommands/pipeline.py`

- [ ] **Step 1: Create `subcommands/tui.py`**

This wraps the existing `run_tui()` logic from `cli_entry.py:226-244` and accepts the loaded `CliConfig`:

```python
"""`whatsapp` (no subcommand) — launch the Textual TUI."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..config import CliConfig


def add_subparser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # The TUI is the *default* (no subcommand). We still register a hidden
    # parser so `whatsapp tui` works and surfaces the same flags.
    p = subparsers.add_parser(
        "tui",
        help=argparse.SUPPRESS,  # default mode, no need to advertise
    )
    p.add_argument("--output", type=str, default=None, metavar="DIR")
    p.add_argument("--limit", type=int, default=None, metavar="N")
    p.add_argument("--no-output-media", action="store_true")
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument(
        "--transcription-provider",
        choices=["whisper", "elevenlabs"], default="whisper",
    )
    p.add_argument("--delete-from-drive", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--skip-preflight", action="store_true")
    p.set_defaults(_handler=run)
    return p


def run(args: argparse.Namespace) -> int:
    from ...tui.textual_app import WhatsAppExporterApp

    output_dir = Path(args.output).expanduser() if args.output else None

    app = WhatsAppExporterApp(
        output_dir=output_dir,
        include_media=not args.no_output_media,
        transcribe_audio=not args.no_transcribe,
        delete_from_drive=args.delete_from_drive,
        transcription_provider=args.transcription_provider,
        limit=args.limit,
        debug=args.debug,
        skip_preflight=args.skip_preflight,
    )
    app.run()
    return 0
```

- [ ] **Step 2: Create `subcommands/run.py`**

```python
"""`whatsapp run` — full export + pipeline (formerly --headless)."""
from __future__ import annotations

import argparse


def add_subparser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "run",
        help="Run full export + pipeline (was --headless).",
    )
    p.add_argument(
        "--output", type=str, required=False, metavar="DIR",
        help="Output directory for processed exports (required unless set in config).",
    )
    p.add_argument("--limit", type=int, default=None, metavar="N")
    p.add_argument(
        "--without-media", action="store_true",
        help=("Export chats without media files. WARNING: disables audio/video "
              "transcription because no media is downloaded."),
    )
    p.add_argument(
        "--wireless-adb", nargs="?", const=True, default=None, metavar="IP:PORT",
        help="Use wireless ADB (optionally provide IP:PORT).",
    )
    p.add_argument("--resume", type=str, default=None, metavar="PATH")
    p.add_argument("--auto-select", action="store_true")
    p.add_argument("--no-output-media", action="store_true")
    p.add_argument("--delete-from-drive", action="store_true")
    p.add_argument(
        "--keep-drive-duplicates", action="store_true", default=False,
    )
    p.add_argument(
        "--format", choices=["v2", "legacy"], default="v2", metavar="FORMAT",
        help="Output format: v2 (default) or legacy.",
    )
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--force-transcribe", action="store_true")
    p.add_argument(
        "--transcription-provider",
        choices=["whisper", "elevenlabs"], default="whisper",
    )
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.set_defaults(_handler=run)
    return p


def run(args: argparse.Namespace) -> int:
    import sys

    if not args.output:
        print("error: `whatsapp run` requires --output DIR (or `output` in config).",
              file=sys.stderr)
        return 2

    if args.without_media:
        print(
            "WARNING: --without-media disables audio/video transcription "
            "(no media will be downloaded to transcribe).",
            file=sys.stderr,
        )

    # Map new --format to legacy headless.py expectation:
    #   - args.format       → format_version (the "real" format choice)
    #   - args.output_format → always "legacy" (old --format=spec is removed)
    args.format_version = args.format
    args.format = "legacy"

    from ...headless import run_headless
    return run_headless(args)
```

- [ ] **Step 3: Create `subcommands/pipeline.py`**

```python
"""`whatsapp pipeline SRC OUT` — pipeline-only on existing files."""
from __future__ import annotations

import argparse


def add_subparser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "pipeline",
        help="Run pipeline only on existing files (was --pipeline-only).",
    )
    p.add_argument("source", help="Source directory containing WhatsApp exports.")
    p.add_argument("pipeline_output", help="Output directory for processed files.")
    p.add_argument("--limit", type=int, default=None, metavar="N")
    p.add_argument("--no-output-media", action="store_true")
    p.add_argument("--delete-from-drive", action="store_true")
    p.add_argument("--keep-drive-duplicates", action="store_true", default=False)
    p.add_argument(
        "--format", choices=["v2", "legacy"], default="v2", metavar="FORMAT",
    )
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--force-transcribe", action="store_true")
    p.add_argument(
        "--transcription-provider",
        choices=["whisper", "elevenlabs"], default="whisper",
    )
    p.add_argument("--skip-drive-download", action="store_true")
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.set_defaults(_handler=run)
    return p


def run(args: argparse.Namespace) -> int:
    args.format_version = args.format
    args.format = "legacy"

    from ...headless import run_pipeline_only
    return run_pipeline_only(args)
```

- [ ] **Step 4: Smoke-test imports**

Run: `poetry run python -c "from whatsapp_chat_autoexport.cli.subcommands import tui, run, pipeline, config_init; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/cli/subcommands/tui.py whatsapp_chat_autoexport/cli/subcommands/run.py whatsapp_chat_autoexport/cli/subcommands/pipeline.py
git commit -m "feat(cli): add tui/run/pipeline subcommand modules"
```

---

### Task 4: Replace `cli_entry.py` with subparser dispatcher + deprecation shim

**Files:**
- Modify: `whatsapp_chat_autoexport/cli_entry.py` (full rewrite)

- [ ] **Step 1: Rewrite `cli_entry.py`**

Overwrite the file with the new dispatcher. The shim at the top intercepts `--headless` and `--pipeline-only` from `argv` *before* argparse sees them, rewrites them to subcommand form, and prints a deprecation notice.

```python
"""Unified CLI entry point for WhatsApp Chat Auto-Export.

Subcommands:
  whatsapp                    Launch the interactive TUI (default)
  whatsapp run --output DIR   Headless export + pipeline
  whatsapp pipeline SRC OUT   Pipeline-only on existing files
  whatsapp config init        Scaffold ~/.config/whatsapp-autoexport/config.toml

Legacy --headless / --pipeline-only flags still dispatch correctly with a
one-line deprecation notice (removed in the next release).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .cli.config import CliConfig
from .cli.subcommands import config_init, pipeline, run, tui


# ---------------------------------------------------------------------------
# Deprecation shim: rewrite legacy flag forms to subcommand forms before parse
# ---------------------------------------------------------------------------

def _rewrite_legacy_flags(argv: List[str]) -> List[str]:
    """Map legacy `--headless` / `--pipeline-only` invocations to subcommands.

    Emits a stderr deprecation notice when a rewrite happens.
    """
    if not argv:
        return argv

    # Already a subcommand? leave alone
    known = {"run", "pipeline", "tui", "config", "-h", "--help", "--version"}
    if argv[0] in known:
        return argv

    if "--headless" in argv:
        new = [a for a in argv if a != "--headless"]
        new.insert(0, "run")
        print(
            "warning: --headless is deprecated; use `whatsapp run` instead.",
            file=sys.stderr,
        )
        return new

    if "--pipeline-only" in argv:
        new = [a for a in argv if a != "--pipeline-only"]
        new.insert(0, "pipeline")
        print(
            "warning: --pipeline-only is deprecated; use `whatsapp pipeline` instead.",
            file=sys.stderr,
        )
        return new

    return argv


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whatsapp",
        description="WhatsApp Chat Auto-Export — TUI, headless, or pipeline-only.",
    )
    parser.add_argument(
        "--config", type=str, default=None, metavar="PATH",
        help="Path to a TOML config file (overrides default lookup).",
    )

    subparsers = parser.add_subparsers(dest="subcommand")
    tui.add_subparser(subparsers)
    run.add_subparser(subparsers)
    pipeline.add_subparser(subparsers)
    config_init.add_subparser(subparsers)

    return parser


def _apply_config_defaults(
    args: argparse.Namespace, cfg: CliConfig,
) -> argparse.Namespace:
    """Merge config-file defaults into args where the user didn't pass a flag.

    We can't tell from a parsed Namespace alone whether a value came from the
    parser default or the user. So we trust the parser's own defaults: if the
    current value matches the parser default, fall back to config.
    """
    overrides = cfg.to_argparse_defaults()
    for key, value in overrides.items():
        # Skip if the user provided an explicit value (i.e. the namespace
        # already holds a non-default value). For booleans we treat False as
        # "not set" since all our boolean flags are store_true (default False).
        current = getattr(args, key, None)
        if current is None or current is False:
            setattr(args, key, value)
    return args


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    rewritten = _rewrite_legacy_flags(raw)

    parser = create_parser()

    # Default subcommand is "tui" if nothing was given
    if not rewritten:
        rewritten = ["tui"]

    args = parser.parse_args(rewritten)

    # Load config (explicit --config wins, else XDG → project)
    explicit = Path(args.config).expanduser() if args.config else None
    cfg = CliConfig.load(explicit_path=explicit)
    args = _apply_config_defaults(args, cfg)

    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 0

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test top-level help**

Run: `poetry run whatsapp --help`
Expected: lists subcommands `run`, `pipeline`, `config` (and the hidden `tui`); shows `--config PATH` global flag; no errors.

- [ ] **Step 3: Smoke-test legacy flag rewrite**

Run: `poetry run whatsapp --headless --output /tmp/x --auto-select --limit 0 2>&1 | head -3`
Expected: first line on stderr is `warning: --headless is deprecated; use \`whatsapp run\` instead.` Then the run subcommand executes (will fail at preflight or device steps — that's fine; we're only checking the rewrite).

- [ ] **Step 4: Smoke-test new subcommand form**

Run: `poetry run whatsapp run --help`
Expected: shows the `run` subparser's flags (`--output`, `--limit`, `--without-media`, etc.) and nothing else.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/cli_entry.py
git commit -m "feat(cli): replace flag-based modes with subparser dispatch + deprecation shim"
```

---

### Task 5: Drop phantom `getattr` defaults in `headless.py`

**Files:**
- Modify: `whatsapp_chat_autoexport/headless.py` (specific lines below)

The six phantom flags (`skip_appium`, `google_drive_folder`, `poll_interval`, `poll_timeout`, `transcription_language`, `skip_opus_conversion`) are not in any subparser. We replace each `getattr(args, "...", default)` with the inlined default.

Existing `getattr(args, "...", ...)` calls for *real* flags (`debug`, `output`, `auto_select`, `wireless_adb`, etc.) stay — they protect against the deprecation shim path and keep the TUI/pipeline-only callsites working.

- [ ] **Step 1: Edit `run_headless()` — remove `skip_appium`**

Replace lines 154-163 (the entire `# Step 1: Appium` block) in `whatsapp_chat_autoexport/headless.py`:

Old:
```python
        # Step 1: Appium ---------------------------------------------------
        skip_appium = getattr(args, "skip_appium", False)
        if not skip_appium:
            logger.step(1, "Starting Appium server...")
            appium_manager = AppiumManager(logger)
            if not appium_manager.start_appium():
                logger.error("Failed to start Appium. Is it installed?")
                return 2
        else:
            logger.info("Skipping Appium startup (--skip-appium)")
```

New:
```python
        # Step 1: Appium ---------------------------------------------------
        logger.step(1, "Starting Appium server...")
        appium_manager = AppiumManager(logger)
        if not appium_manager.start_appium():
            logger.error("Failed to start Appium. Is it installed?")
            return 2
```

- [ ] **Step 2: Edit `run_headless()` — fix the `pipeline_config = PipelineConfig(...)` block**

Replace lines 203-222 in `whatsapp_chat_autoexport/headless.py`:

Old:
```python
        pipeline_config = PipelineConfig(
            google_drive_folder=getattr(args, "google_drive_folder", None),
            delete_from_drive=getattr(args, "delete_from_drive", False),
            cleanup_drive_duplicates=not getattr(args, "keep_drive_duplicates", False),
            skip_download=False,
            poll_interval=getattr(args, "poll_interval", 8),
            poll_timeout=getattr(args, "poll_timeout", 300),
            transcribe_audio_video=not no_transcribe,
            transcription_language=getattr(args, "transcription_language", None),
            transcription_provider=getattr(args, "transcription_provider", "whisper"),
            skip_existing_transcriptions=not getattr(args, "force_transcribe", False),
            convert_opus_to_m4a=not getattr(args, "skip_opus_conversion", False),
            output_dir=output_dir,
            include_media=not getattr(args, "no_output_media", False),
            include_transcriptions=True,
            output_format=getattr(args, "format", "legacy"),
            cleanup_temp=True,
            dry_run=False,
            format_version=getattr(args, "format_version", "v2"),
        )
```

New:
```python
        pipeline_config = PipelineConfig(
            google_drive_folder=None,  # not exposed; subfolder support is unused
            delete_from_drive=getattr(args, "delete_from_drive", False),
            cleanup_drive_duplicates=not getattr(args, "keep_drive_duplicates", False),
            skip_download=False,
            # poll_interval/timeout: pipeline uses adaptive backoff; defaults are fine
            transcribe_audio_video=not no_transcribe,
            transcription_language=None,  # auto-detect; flag never existed publicly
            transcription_provider=getattr(args, "transcription_provider", "whisper"),
            skip_existing_transcriptions=not getattr(args, "force_transcribe", False),
            convert_opus_to_m4a=True,  # always convert; required for transcription
            output_dir=output_dir,
            include_media=not getattr(args, "no_output_media", False),
            include_transcriptions=True,
            output_format=getattr(args, "format", "legacy"),
            cleanup_temp=True,
            dry_run=False,
            format_version=getattr(args, "format_version", "v2"),
        )
```

- [ ] **Step 3: Edit `run_headless()` — remove the `google_drive_folder` line below the config block**

Replace lines 230-232 in `whatsapp_chat_autoexport/headless.py`:

Old:
```python
        # Step 7: Export + pipeline ----------------------------------------
        logger.step(7, "Exporting chats...")
        include_media = not getattr(args, "without_media", False)
        google_drive_folder = getattr(args, "google_drive_folder", None)
```

New:
```python
        # Step 7: Export + pipeline ----------------------------------------
        logger.step(7, "Exporting chats...")
        include_media = not getattr(args, "without_media", False)
        google_drive_folder = None  # not exposed; subfolder support is unused
```

- [ ] **Step 4: Run a syntax check**

Run: `poetry run python -c "import whatsapp_chat_autoexport.headless"`
Expected: no output (clean import).

- [ ] **Step 5: Smoke-test the run subcommand still constructs config**

Run: `poetry run whatsapp run --output /tmp/x --auto-select --limit 0 --skip-preflight 2>&1 | grep -E "Pipeline configured|error|Error" | head -3`
Expected: either "Pipeline configured — output: /tmp/x ..." or a downstream error about no device. Either is acceptable — we're confirming the config block doesn't `TypeError` from a missing argument.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/headless.py
git commit -m "refactor(headless): inline phantom getattr defaults (skip_appium, google_drive_folder, etc.)"
```

---

### Task 6: Remove deprecated entry points + `deprecated_entry.py`

**Files:**
- Modify: `pyproject.toml`
- Delete: `whatsapp_chat_autoexport/deprecated_entry.py`

- [ ] **Step 1: Remove the five deprecated script lines from `pyproject.toml`**

Open `pyproject.toml` and remove these five lines from the `[tool.poetry.scripts]` block:

```
whatsapp-export = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_export_main"
whatsapp-process = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_process_main"
whatsapp-drive = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_drive_main"
whatsapp-pipeline = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_pipeline_main"
whatsapp-logs = "whatsapp_chat_autoexport.deprecated_entry:whatsapp_logs_main"
```

Also remove the `# Deprecated commands ...` comment line directly above them.

- [ ] **Step 2: Delete `deprecated_entry.py`**

```bash
rm whatsapp_chat_autoexport/deprecated_entry.py
```

- [ ] **Step 3: Re-install entry points**

Run: `poetry install --quiet`
Expected: clean install, no errors.

- [ ] **Step 4: Verify removed entry points are gone**

Run: `poetry run whatsapp-export 2>&1 | head -3 || echo "not found (expected)"`
Expected: `command not found` or `not found (expected)` — the script binary no longer exists.

- [ ] **Step 5: Verify the main entry point still works**

Run: `poetry run whatsapp --help | head -3`
Expected: parser usage line.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml whatsapp_chat_autoexport/deprecated_entry.py
git commit -m "chore: remove deprecated entry points (whatsapp-export, -pipeline, -process, -drive, -logs)"
```

---

### Task 7: Wire TUI to read CliConfig

**Files:**
- Modify: `whatsapp_chat_autoexport/cli/subcommands/tui.py`

The TUI subcommand currently constructs `WhatsAppExporterApp` from CLI flags only. We modify the `run()` handler to consult `CliConfig` for any value the user didn't pass. The `WhatsAppExporterApp` class itself is **not** modified — it already accepts these as constructor args.

- [ ] **Step 1: Update `subcommands/tui.py` to read config**

Replace the `run()` function in `whatsapp_chat_autoexport/cli/subcommands/tui.py`:

Old:
```python
def run(args: argparse.Namespace) -> int:
    from ...tui.textual_app import WhatsAppExporterApp

    output_dir = Path(args.output).expanduser() if args.output else None

    app = WhatsAppExporterApp(
        output_dir=output_dir,
        include_media=not args.no_output_media,
        transcribe_audio=not args.no_transcribe,
        delete_from_drive=args.delete_from_drive,
        transcription_provider=args.transcription_provider,
        limit=args.limit,
        debug=args.debug,
        skip_preflight=args.skip_preflight,
    )
    app.run()
    return 0
```

New:
```python
def run(args: argparse.Namespace) -> int:
    from ...tui.textual_app import WhatsAppExporterApp

    # Args have already been merged with CliConfig in cli_entry.main();
    # we just read them directly here.
    output_dir = Path(args.output).expanduser() if args.output else None

    app = WhatsAppExporterApp(
        output_dir=output_dir,
        include_media=not args.no_output_media,
        transcribe_audio=not args.no_transcribe,
        delete_from_drive=args.delete_from_drive,
        transcription_provider=args.transcription_provider,
        limit=args.limit,
        debug=args.debug,
        skip_preflight=args.skip_preflight,
    )
    app.run()
    return 0
```

(The function body is unchanged — the docstring change makes the contract explicit. Config merging happens in `cli_entry.main()` before `run()` is called.)

- [ ] **Step 2: Manual sanity check — config provides TUI defaults**

Create a temp config file:

```bash
mkdir -p /tmp/whatsapp-config-test
cat > /tmp/whatsapp-config-test/config.toml <<'EOF'
[defaults]
transcription_provider = "elevenlabs"
output_media = false
delete_from_drive = true
[paths]
output = "/tmp/whatsapp-config-test/exports"
EOF
```

Then run:
```bash
poetry run whatsapp --config /tmp/whatsapp-config-test/config.toml tui --help
```

Expected: the help still lists the flags. Now construct the namespace with `python -c`:
```bash
poetry run python -c "
from whatsapp_chat_autoexport.cli_entry import create_parser, _apply_config_defaults
from whatsapp_chat_autoexport.cli.config import CliConfig
from pathlib import Path

parser = create_parser()
args = parser.parse_args(['tui'])
cfg = CliConfig.load(Path('/tmp/whatsapp-config-test/config.toml'))
args = _apply_config_defaults(args, cfg)
print('provider:', args.transcription_provider)
print('no_output_media:', args.no_output_media)
print('delete_from_drive:', args.delete_from_drive)
print('output:', args.output)
"
```
Expected:
```
provider: elevenlabs
no_output_media: True
delete_from_drive: True
output: /tmp/whatsapp-config-test/exports
```

- [ ] **Step 3: Cleanup**

```bash
rm -rf /tmp/whatsapp-config-test
```

- [ ] **Step 4: Commit (only if there were source changes)**

If only the docstring/comment in `tui.py` changed, commit it; otherwise this task may be a no-op commit.

```bash
git add whatsapp_chat_autoexport/cli/subcommands/tui.py
git diff --cached --stat
# If diff is empty, skip the commit; otherwise:
git commit -m "docs(tui-subcommand): clarify config-merging contract"
```

---

### Task 8: Add `c` keybinding to open config in $EDITOR

**Files:**
- Modify: `whatsapp_chat_autoexport/tui/textual_app.py`

- [ ] **Step 1: Add the binding to `WhatsAppExporterApp.BINDINGS`**

In `whatsapp_chat_autoexport/tui/textual_app.py`, locate the `BINDINGS` list (lines 64-76). Add this entry after the `slash` binding:

```python
        Binding("c", "edit_config", "Edit config", show=False),
```

- [ ] **Step 2: Add the `action_edit_config` method**

Add this method to the `WhatsAppExporterApp` class (any sensible spot, e.g. near other action methods):

```python
    def action_edit_config(self) -> None:
        """Open the user config file in $EDITOR.

        If the config does not yet exist, scaffolds it first using the
        same template as `whatsapp config init`.
        """
        import os
        import subprocess
        from importlib.resources import files

        from ..cli.config import _user_config_path

        config_path = _user_config_path()
        if not config_path.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            template = files("whatsapp_chat_autoexport.cli.templates").joinpath(
                "config.toml.template"
            ).read_text()
            config_path.write_text(template)

        editor = os.environ.get("EDITOR", "vi")
        with self.suspend():
            subprocess.run([editor, str(config_path)])
```

- [ ] **Step 3: Smoke-test (manual)**

Run: `poetry run whatsapp` then press `c`. Expected: `$EDITOR` opens on `~/.config/whatsapp-autoexport/config.toml` (creating it if missing). Quit the editor; the TUI resumes.

If `$EDITOR` is unset, `vi` is used. If you don't have a device available to fully launch the TUI, this step can be skipped — the next end-to-end task confirms imports/bindings still parse.

- [ ] **Step 4: Commit**

```bash
git add whatsapp_chat_autoexport/tui/textual_app.py
git commit -m "feat(tui): add 'c' keybinding to edit user config in \$EDITOR"
```

---

### Task 9: End-to-end validation

**Files:** none (validation only)

- [ ] **Step 1: `whatsapp --help` lists subcommands**

Run: `poetry run whatsapp --help`
Expected output contains the lines:
```
{run,pipeline,config}
```
(plus the hidden `tui`).

- [ ] **Step 2: `whatsapp run --help` is focused**

Run: `poetry run whatsapp run --help`
Expected: shows only the `run` flags. Confirm `--without-media` help text mentions transcription disablement.

- [ ] **Step 3: Legacy `--headless` warning appears**

Run: `poetry run whatsapp --headless --output /tmp/x --auto-select 2>&1 | head -1`
Expected: `warning: --headless is deprecated; use \`whatsapp run\` instead.`

- [ ] **Step 4: `whatsapp config init` writes the config file**

```bash
TEST_HOME=$(mktemp -d)
HOME="$TEST_HOME" poetry run whatsapp config init
ls "$TEST_HOME/.config/whatsapp-autoexport/config.toml"
HOME="$TEST_HOME" poetry run whatsapp config init 2>&1 | grep -i "already exists"
HOME="$TEST_HOME" poetry run whatsapp config init --force
rm -rf "$TEST_HOME"
```
Expected: file is created the first time, the second invocation reports `already exists`, `--force` overwrites successfully.

- [ ] **Step 5: Phantom flags are gone from headless**

Run: `grep -E "skip_appium|google_drive_folder|poll_interval|poll_timeout|transcription_language|skip_opus_conversion" whatsapp_chat_autoexport/headless.py`
Expected: no matches.

- [ ] **Step 6: Five deprecated entry points are gone**

Run: `grep -E "whatsapp-export|whatsapp-pipeline|whatsapp-process|whatsapp-drive|whatsapp-logs" pyproject.toml`
Expected: no matches.

- [ ] **Step 7: deprecated_entry.py is deleted**

Run: `test -f whatsapp_chat_autoexport/deprecated_entry.py && echo "still here" || echo "gone (expected)"`
Expected: `gone (expected)`.

- [ ] **Step 8: Update CLAUDE.md migration notes (light touch)**

Modify `CLAUDE.md` to:
1. Replace example invocations using `--headless` / `--pipeline-only` with `whatsapp run` / `whatsapp pipeline`.
2. Update the "Deprecated Commands" table — replace the five `whatsapp-*` rows with a single line: "Legacy commands `whatsapp-export`/`-pipeline`/`-process`/`-drive`/`-logs` and the `--headless`/`--pipeline-only` flag aliases were removed in this release; see `whatsapp <subcommand> --help`."
3. Add a one-paragraph note pointing to `~/.config/whatsapp-autoexport/config.toml` and `whatsapp config init`.

- [ ] **Step 9: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: update CLI reference for subcommand restructure + config file"
```

---

## Out of Scope (per spec)

- MCP sync CLI (`whatsapp-sync`, `-ingest`, `-migrate`, `-rebuild`) — left as-is.
- Test refactor — handled under the parallel testing-revision effort.
- Output format end-of-life decision (`v2` vs `legacy`) — separate concern.
