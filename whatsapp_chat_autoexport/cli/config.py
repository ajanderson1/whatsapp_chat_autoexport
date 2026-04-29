"""TOML config loader for the whatsapp CLI.

Resolution order (low → high precedence):
  1. Parser defaults (handled by argparse)
  2. User config:    $XDG_CONFIG_HOME/whatsapp-autoexport/config.toml
                     or ~/.config/whatsapp-autoexport/config.toml
  3. Project config: ./.whatsapp-autoexport.toml
  4. Environment variables (handled elsewhere — not in scope here)
  5. Explicit CLI flags (handled by argparse)

This module loads (2) and (3) and exposes a `CliConfig` dataclass that
``cli_entry.main()`` merges into the parsed argparse Namespace, filling
in defaults for flags the user did not pass on the command line.
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
    sourced_from_config: Dict[str, Path] = field(
        default_factory=dict, repr=False, compare=False,
    )

    @classmethod
    def load(cls, explicit_path: Optional[Path] = None) -> "CliConfig":
        """Load config.

        Without ``explicit_path``: merges user config and project config,
        with project values winning over user values.
        With ``explicit_path``: loads only that file (user and project
        configs are bypassed).
        """
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
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(
                f"Config file {path} contains invalid TOML: {exc}"
            ) from exc
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
        if self.wireless_adb:
            # Config flag is bool; CLI accepts optional IP:PORT.
            # Only emit when truthy — False means "use the parser default".
            out["wireless_adb"] = True
        if self.auto_select is not None:
            out["auto_select"] = self.auto_select
        if self.output is not None:
            out["output"] = self.output
        return out
