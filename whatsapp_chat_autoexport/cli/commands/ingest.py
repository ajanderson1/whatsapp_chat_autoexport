"""
Ingest command for WhatsApp Chat Auto-Export.

Takes an Appium export directory and an output directory, parses each
chat via AppiumSource, merges with any existing vault transcripts
(TranscriptSource), deduplicates, and writes v2 format output
(transcript.md + index.md) via SpecFormatter + IndexBuilder.

    CLI: poetry run whatsapp-ingest <export-dir> --output <vault-dir>
    JSON summary to stdout, progress to stderr.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...output.index_builder import IndexBuilder
from ...output.spec_formatter import SpecFormatter
from ...processing.dedup import deduplicate
from ...processing.transcript_parser import Message
from ...sources.appium_source import AppiumSource
from ...sources.transcript_source import TranscriptSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress(msg: str) -> None:
    """Print a progress line to stderr."""
    print(msg, file=sys.stderr, flush=True)


def _json_summary(data: Dict[str, Any]) -> None:
    """Print a JSON summary to stdout."""
    print(json.dumps(data, indent=2, default=str))


def _atomic_write(target: Path, content: str) -> None:
    """Write *content* to *target* atomically via a temp file."""
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(target))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


# ---------------------------------------------------------------------------
# Per-chat ingest
# ---------------------------------------------------------------------------

def _ingest_chat(
    chat_name: str,
    appium_messages: List[Message],
    output_dir: Path,
    spec_formatter: SpecFormatter,
    index_builder: IndexBuilder,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Ingest a single chat from Appium export, merging with existing vault data.

    Returns a per-chat result dict.
    """
    chat_dir = output_dir / chat_name
    result: Dict[str, Any] = {
        "name": chat_name,
        "folder": chat_name,
        "appium_messages": len(appium_messages),
        "existing_messages": 0,
        "merged_messages": 0,
        "new_messages": 0,
        "status": "ok",
    }

    # Load existing transcript if present
    existing_messages: List[Message] = []
    transcript_md = chat_dir / "transcript.md"
    transcript_txt = chat_dir / "transcript.txt"

    if transcript_md.exists() or transcript_txt.exists():
        ts = TranscriptSource(output_dir)
        existing_messages = ts.get_messages(chat_name)
        result["existing_messages"] = len(existing_messages)

    # Merge + deduplicate
    all_messages = existing_messages + appium_messages
    merged = deduplicate(all_messages)
    result["merged_messages"] = len(merged)
    result["new_messages"] = len(merged) - result["existing_messages"]

    if result["new_messages"] <= 0 and existing_messages:
        result["status"] = "already_current"
        result["new_messages"] = 0
        return result

    if dry_run:
        result["status"] = "dry_run"
        return result

    # Ensure chat directory exists
    chat_dir.mkdir(parents=True, exist_ok=True)

    # Write transcript.md via SpecFormatter (atomic write)
    transcript_content = spec_formatter.format_transcript(
        messages=merged,
        chat_jid=chat_name,
        contact_name=chat_name,
    )
    _atomic_write(transcript_md, transcript_content)

    # Write/update index.md via IndexBuilder
    index_path = chat_dir / "index.md"
    source_entry = {
        "type": "appium_export",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "messages": len(appium_messages),
    }

    if index_path.exists():
        existing_index = index_path.read_text(encoding="utf-8")
        index_content = index_builder.update_index(
            existing_content=existing_index,
            new_messages=appium_messages,
            source_entry=source_entry,
        )
    else:
        index_content = index_builder.build_index(
            messages=merged,
            chat_jid=chat_name,
            contact_name=chat_name,
            sources=[source_entry],
        )
    _atomic_write(index_path, index_content)

    return result


# ---------------------------------------------------------------------------
# Main ingest orchestration
# ---------------------------------------------------------------------------

def run_ingest(
    export_dir: Path,
    output_dir: Path,
    user_display_name: str = "AJ Anderson",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run the Appium export ingest pipeline.

    This is the programmatic entry point -- the CLI argument parser calls
    this function with resolved arguments.

    Args:
        export_dir: Appium export directory containing chat sub-dirs.
        output_dir: Vault output directory for transcripts.
        user_display_name: Display name for "from me" messages.
        dry_run: If True, report what would change without writing.

    Returns:
        JSON-serialisable summary dict.
    """
    summary: Dict[str, Any] = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "export_dir": str(export_dir),
        "output_dir": str(output_dir),
        "chats_processed": 0,
        "chats_gap_filled": 0,
        "chats_already_current": 0,
        "chats_errored": 0,
        "total_new_messages": 0,
        "chat_results": [],
        "error": None,
    }

    # ---- 1. Validate export directory ----
    if not export_dir.is_dir():
        summary["error"] = f"Export directory not found: {export_dir}"
        _json_summary(summary)
        return summary

    # ---- 2. Create Appium source ----
    appium_source = AppiumSource(export_dir, user_display_name=user_display_name)

    # ---- 3. Discover chats ----
    _progress(f"Scanning Appium export at {export_dir}...")
    chats = appium_source.get_chats()

    if not chats:
        summary["error"] = "No chats found in Appium export directory"
        _json_summary(summary)
        return summary

    _progress(f"Found {len(chats)} chat(s) in Appium export")

    # ---- 4. Create formatters ----
    spec_formatter = SpecFormatter(user_display_name=user_display_name)
    index_builder = IndexBuilder(user_display_name=user_display_name)

    # ---- 5. Per-chat ingest loop ----
    for chat in chats:
        _progress(f"Ingesting: {chat.name}")
        try:
            appium_messages = appium_source.get_messages(chat.jid)
            if not appium_messages:
                _progress(f"  Skipping {chat.name}: no messages")
                continue

            chat_result = _ingest_chat(
                chat_name=chat.name,
                appium_messages=appium_messages,
                output_dir=output_dir,
                spec_formatter=spec_formatter,
                index_builder=index_builder,
                dry_run=dry_run,
            )
            summary["chat_results"].append(chat_result)

            if chat_result["status"] == "ok":
                summary["chats_processed"] += 1
                summary["total_new_messages"] += chat_result["new_messages"]
                if chat_result["new_messages"] > 0 and chat_result["existing_messages"] > 0:
                    summary["chats_gap_filled"] += 1
            elif chat_result["status"] == "already_current":
                summary["chats_already_current"] += 1
            elif chat_result["status"] == "dry_run":
                summary["chats_processed"] += 1
                summary["total_new_messages"] += chat_result["new_messages"]

        except Exception as exc:
            _progress(f"  ERROR ingesting {chat.name}: {exc}")
            summary["chats_errored"] += 1
            summary["chat_results"].append({
                "name": chat.name,
                "status": "error",
                "error": str(exc),
            })

    summary["success"] = summary["chats_errored"] == 0 and summary["error"] is None
    _json_summary(summary)
    return summary


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the ingest command."""
    parser = argparse.ArgumentParser(
        prog="whatsapp-ingest",
        description="Ingest Appium WhatsApp exports into vault transcripts (v2 format)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/appium-export --output ~/Journal/People/Correspondence/Whatsapp
  %(prog)s /path/to/export --output ~/exports --dry-run
  %(prog)s /path/to/export --output ~/exports --user-display-name "Jane Doe"
        """,
    )

    parser.add_argument(
        "export_dir",
        type=str,
        metavar="EXPORT_DIR",
        help="Appium export directory containing chat sub-directories",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        metavar="DIR",
        help="Vault output directory for transcripts",
    )
    parser.add_argument(
        "--user-display-name",
        type=str,
        default="AJ Anderson",
        metavar="NAME",
        help='Display name for "from me" messages (default: "AJ Anderson")',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for the ingest command."""
    parser = create_parser()
    args = parser.parse_args(argv)

    export_dir = Path(args.export_dir).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_ingest(
        export_dir=export_dir,
        output_dir=output_dir,
        user_display_name=args.user_display_name,
        dry_run=args.dry_run,
    )

    return 0 if summary.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
