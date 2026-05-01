"""`whatsapp` (no subcommand) — launch the Textual TUI."""
from __future__ import annotations

import argparse
from pathlib import Path


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
        choices=["whisper", "elevenlabs"], default=None,
    )
    p.add_argument("--delete-from-drive", action="store_true")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--skip-preflight", action="store_true")
    p.set_defaults(_handler=run)
    return p


def run(args: argparse.Namespace) -> int:
    """Launch the Textual TUI.

    ``args`` has already been merged with ``CliConfig`` defaults by
    ``cli_entry.main()`` before this handler is called, so flags absent
    from the command line have already been filled in from
    ``~/.config/whatsapp-autoexport/config.toml`` (and the project-local
    override, if present). Read directly from ``args``.
    """
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
