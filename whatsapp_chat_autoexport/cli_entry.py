"""
Unified CLI entry point for WhatsApp Chat Auto-Export.

Dispatches to one of three modes:
- TUI (default): Interactive Textual application
- Headless (--headless): Non-interactive export + pipeline
- Pipeline-only (--pipeline-only): Non-interactive pipeline processing only

All R7 flags are parsed here and forwarded to the selected mode.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def create_parser() -> argparse.ArgumentParser:
    """Create the unified argument parser with all R7 flags."""
    parser = argparse.ArgumentParser(
        prog="whatsapp",
        description="WhatsApp Chat Auto-Export — TUI, headless, or pipeline-only mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)         Launch interactive TUI
  --headless        Run full export + pipeline without TUI (requires --output)
  --pipeline-only   Run pipeline only on existing files (requires source and output args)

Examples:
  %(prog)s                                  # Launch TUI
  %(prog)s --headless --output ~/exports    # Headless export + pipeline
  %(prog)s --pipeline-only /downloads /out  # Pipeline-only on local files
  %(prog)s --limit 5 --debug                # TUI with limit and debug
        """,
    )

    # Mode flags
    mode_group = parser.add_argument_group("Mode Selection")
    mode_group.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no TUI). Requires --output.",
    )
    mode_group.add_argument(
        "--pipeline-only",
        action="store_true",
        help="Run pipeline only (no device export). Requires source and output positional args.",
    )

    # Pipeline-only positional args (optional — only required for --pipeline-only)
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Source directory (for --pipeline-only mode)",
    )
    parser.add_argument(
        "pipeline_output",
        nargs="?",
        default=None,
        help="Output directory (for --pipeline-only mode)",
    )

    # Export options
    export_group = parser.add_argument_group("Export Options")
    export_group.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of chats to export",
    )
    export_group.add_argument(
        "--without-media",
        action="store_true",
        help="Export chats without media files",
    )
    export_group.add_argument(
        "--wireless-adb",
        nargs="?",
        const=True,
        default=None,
        metavar="IP:PORT",
        help="Use wireless ADB (optionally provide IP:PORT)",
    )
    export_group.add_argument(
        "--resume",
        type=str,
        default=None,
        metavar="PATH",
        help="Resume export, skipping chats already in PATH",
    )
    export_group.add_argument(
        "--auto-select",
        action="store_true",
        help="Automatically select all chats for export",
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="DIR",
        help="Output directory for processed exports",
    )
    output_group.add_argument(
        "--no-output-media",
        action="store_true",
        help="Exclude media from final output (transcriptions still created)",
    )
    output_group.add_argument(
        "--delete-from-drive",
        action="store_true",
        help="Delete files from Google Drive after processing",
    )
    output_group.add_argument(
        "--keep-drive-duplicates",
        action="store_true",
        default=False,
        help="Skip deleting Drive root duplicates after each per-chat download "
             "(default: duplicates are removed).",
    )

    # Transcription options
    transcribe_group = parser.add_argument_group("Transcription Options")
    transcribe_group.add_argument(
        "--no-transcribe",
        action="store_true",
        help="Skip audio/video transcription",
    )
    transcribe_group.add_argument(
        "--force-transcribe",
        action="store_true",
        help="Re-transcribe even if transcriptions already exist",
    )
    transcribe_group.add_argument(
        "--transcription-provider",
        type=str,
        choices=["whisper", "elevenlabs"],
        default="whisper",
        metavar="PROVIDER",
        help="Transcription provider (default: whisper)",
    )

    # Pipeline options
    pipeline_group = parser.add_argument_group("Pipeline Options")
    pipeline_group.add_argument(
        "--skip-drive-download",
        action="store_true",
        help="Skip Google Drive download, process local files only",
    )

    # General options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )

    return parser


def detect_mode(args: argparse.Namespace) -> str:
    """
    Determine which mode to run based on parsed args.

    Returns one of: 'tui', 'headless', 'pipeline-only'
    """
    if args.headless and args.pipeline_only:
        return "error:conflict"
    if args.headless:
        return "headless"
    if args.pipeline_only:
        return "pipeline-only"
    return "tui"


def validate_args(args: argparse.Namespace, mode: str) -> Optional[str]:
    """
    Validate argument combinations for the selected mode.

    Returns an error message string if validation fails, None if valid.
    """
    if mode == "error:conflict":
        return "Cannot use --headless and --pipeline-only together."

    if mode == "headless" and not args.output:
        return "--headless mode requires --output DIR."

    if mode == "pipeline-only":
        if not args.source:
            return "--pipeline-only mode requires source and output positional arguments."
        if not args.pipeline_output:
            return "--pipeline-only mode requires both source and output positional arguments."

    return None


def run_tui(args: argparse.Namespace) -> int:
    """Launch the Textual TUI application."""
    # Guard TUI imports — only import Textual when actually running the TUI
    from .tui.textual_app import WhatsAppExporterApp

    output_dir = Path(args.output).expanduser() if args.output else None

    app = WhatsAppExporterApp(
        output_dir=output_dir,
        include_media=not args.no_output_media,
        transcribe_audio=not args.no_transcribe,
        delete_from_drive=args.delete_from_drive,
        transcription_provider=args.transcription_provider,
        limit=args.limit,
        debug=args.debug,
    )
    app.run()
    return 0


def run_headless(args: argparse.Namespace) -> int:
    """Run in headless mode (full export + pipeline, no TUI)."""
    from .headless import run_headless as _run_headless

    return _run_headless(args)


def run_pipeline_only(args: argparse.Namespace) -> int:
    """Run pipeline-only mode on existing local files."""
    from .headless import run_pipeline_only as _run_pipeline_only

    return _run_pipeline_only(args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry point for the unified CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    mode = detect_mode(args)
    error = validate_args(args, mode)

    if error:
        parser.error(error)
        # parser.error calls sys.exit(2), but return for clarity
        return 2  # pragma: no cover

    if mode == "tui":
        return run_tui(args)
    elif mode == "headless":
        return run_headless(args)
    elif mode == "pipeline-only":
        return run_pipeline_only(args)

    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
