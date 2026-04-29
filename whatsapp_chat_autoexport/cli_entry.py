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
