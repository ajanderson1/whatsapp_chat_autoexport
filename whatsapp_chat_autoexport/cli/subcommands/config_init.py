"""`whatsapp config init` — scaffold a user config file."""
from __future__ import annotations

import argparse
import sys
from importlib.resources import files

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

    if target.exists() and not getattr(args, "force", False):
        print(
            f"Config already exists at {target}. "
            f"Pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)

    template = files("whatsapp_chat_autoexport.cli.templates").joinpath(
        "config.toml.template"
    ).read_text()
    target.write_text(template)
    print(f"Wrote {target}")
    return 0
