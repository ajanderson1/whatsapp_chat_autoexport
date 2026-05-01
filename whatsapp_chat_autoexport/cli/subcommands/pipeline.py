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
        help="Output format: v2 (default) or legacy.",
    )
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--force-transcribe", action="store_true")
    p.add_argument(
        "--transcription-provider",
        choices=["whisper", "elevenlabs"], default=None,
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
