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
