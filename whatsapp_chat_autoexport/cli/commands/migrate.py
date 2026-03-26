"""
Migrate command for WhatsApp Chat Auto-Export.

Reads all existing transcript.txt files in a vault WhatsApp directory
and converts each from old format to new format (transcript.md +
index.md). Keeps original transcript.txt as backup (rename to
transcript.txt.bak) unless --no-backup is specified.

    CLI: poetry run whatsapp-migrate --input <vault-whatsapp-dir>
    JSON summary to stdout, progress to stderr.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...output.index_builder import IndexBuilder
from ...output.spec_formatter import SpecFormatter
from ...processing.transcript_parser import Message
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
# Per-chat migration
# ---------------------------------------------------------------------------

def _find_legacy_transcripts(input_dir: Path) -> List[Path]:
    """
    Find all legacy transcript.txt files under the input directory.

    Looks for both flat layout (``input_dir/*.txt``) and nested layout
    (``input_dir/<chat>/transcript.txt`` or ``input_dir/<chat>/*.txt``).
    Returns only ``.txt`` files (not already-migrated ``.md`` files).
    """
    transcripts: List[Path] = []

    for child in sorted(input_dir.iterdir()):
        if not child.is_dir():
            # Flat layout: .txt files directly in root
            if child.suffix == ".txt" and child.name != "transcript.txt.bak":
                transcripts.append(child)
            continue

        # Nested layout: look inside sub-directories
        for name in ("transcript.txt",):
            candidate = child / name
            if candidate.is_file():
                transcripts.append(candidate)
                break
        else:
            # Fall back to any .txt file in the sub-directory
            for txt_file in sorted(child.glob("*.txt")):
                if txt_file.is_file() and not txt_file.name.endswith(".bak"):
                    transcripts.append(txt_file)
                    break

    return transcripts


def _migrate_chat(
    transcript_path: Path,
    input_dir: Path,
    spec_formatter: SpecFormatter,
    index_builder: IndexBuilder,
    no_backup: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Migrate a single legacy transcript to v2 format.

    Returns a per-chat result dict.
    """
    # Determine chat directory and name
    if transcript_path.parent == input_dir:
        # Flat layout: file is directly in input_dir
        chat_name = transcript_path.stem
        chat_dir = input_dir / chat_name
    else:
        # Nested layout: file is inside a chat sub-directory
        chat_name = transcript_path.parent.name
        chat_dir = transcript_path.parent

    result: Dict[str, Any] = {
        "name": chat_name,
        "folder": chat_name,
        "source_file": str(transcript_path),
        "old_message_count": 0,
        "new_message_count": 0,
        "counts_match": False,
        "status": "ok",
    }

    # Parse legacy transcript via TranscriptSource
    ts = TranscriptSource(input_dir)
    messages = ts.get_messages(chat_name)
    result["old_message_count"] = len(messages)

    if not messages:
        result["status"] = "empty"
        return result

    if dry_run:
        result["new_message_count"] = len(messages)
        result["counts_match"] = True
        result["status"] = "dry_run"
        return result

    # Ensure chat directory exists (for flat layout migration)
    chat_dir.mkdir(parents=True, exist_ok=True)

    # Write transcript.md via SpecFormatter
    transcript_content = spec_formatter.format_transcript(
        messages=messages,
        chat_jid=chat_name,
        contact_name=chat_name,
    )
    transcript_md = chat_dir / "transcript.md"
    _atomic_write(transcript_md, transcript_content)

    # Write index.md via IndexBuilder
    index_path = chat_dir / "index.md"
    source_entry = {
        "type": "migration",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "messages": len(messages),
    }
    index_content = index_builder.build_index(
        messages=messages,
        chat_jid=chat_name,
        contact_name=chat_name,
        sources=[source_entry],
    )
    _atomic_write(index_path, index_content)

    # Validate: re-read the new transcript and compare message counts
    ts_new = TranscriptSource(input_dir)
    # Clear cache to force re-read
    ts_new._cache.clear()
    new_messages = ts_new.get_messages(chat_name)
    result["new_message_count"] = len(new_messages)
    result["counts_match"] = len(new_messages) == len(messages)

    if not result["counts_match"]:
        result["status"] = "count_mismatch"
        _progress(
            f"  WARNING: message count mismatch for {chat_name}: "
            f"old={len(messages)}, new={len(new_messages)}"
        )

    # Backup original transcript.txt
    if not no_backup and transcript_path.exists():
        backup_path = transcript_path.with_suffix(".txt.bak")
        shutil.copy2(str(transcript_path), str(backup_path))

    return result


# ---------------------------------------------------------------------------
# Main migration orchestration
# ---------------------------------------------------------------------------

def run_migrate(
    input_dir: Path,
    user_display_name: str = "AJ Anderson",
    dry_run: bool = False,
    no_backup: bool = False,
) -> Dict[str, Any]:
    """
    Run the legacy transcript migration pipeline.

    This is the programmatic entry point -- the CLI argument parser calls
    this function with resolved arguments.

    Args:
        input_dir: Vault WhatsApp directory containing legacy transcripts.
        user_display_name: Display name for "from me" messages.
        dry_run: If True, report what would change without writing.
        no_backup: If True, do not create .bak backup of originals.

    Returns:
        JSON-serialisable summary dict.
    """
    summary: Dict[str, Any] = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "input_dir": str(input_dir),
        "chats_migrated": 0,
        "chats_empty": 0,
        "chats_count_mismatch": 0,
        "chats_errored": 0,
        "total_messages": 0,
        "chat_results": [],
        "error": None,
    }

    # ---- 1. Validate input directory ----
    if not input_dir.is_dir():
        summary["error"] = f"Input directory not found: {input_dir}"
        _json_summary(summary)
        return summary

    # ---- 2. Find legacy transcripts ----
    _progress(f"Scanning for legacy transcripts in {input_dir}...")
    transcripts = _find_legacy_transcripts(input_dir)

    if not transcripts:
        summary["error"] = "No legacy transcript.txt files found"
        _json_summary(summary)
        return summary

    _progress(f"Found {len(transcripts)} legacy transcript(s)")

    # ---- 3. Create formatters ----
    spec_formatter = SpecFormatter(user_display_name=user_display_name)
    index_builder = IndexBuilder(user_display_name=user_display_name)

    # ---- 4. Per-chat migration loop ----
    for transcript_path in transcripts:
        chat_name = (
            transcript_path.stem
            if transcript_path.parent == input_dir
            else transcript_path.parent.name
        )
        _progress(f"Migrating: {chat_name}")

        try:
            chat_result = _migrate_chat(
                transcript_path=transcript_path,
                input_dir=input_dir,
                spec_formatter=spec_formatter,
                index_builder=index_builder,
                no_backup=no_backup,
                dry_run=dry_run,
            )
            summary["chat_results"].append(chat_result)

            if chat_result["status"] in ("ok", "dry_run"):
                summary["chats_migrated"] += 1
                summary["total_messages"] += chat_result["old_message_count"]
            elif chat_result["status"] == "empty":
                summary["chats_empty"] += 1
            elif chat_result["status"] == "count_mismatch":
                summary["chats_migrated"] += 1
                summary["chats_count_mismatch"] += 1
                summary["total_messages"] += chat_result["old_message_count"]

        except Exception as exc:
            _progress(f"  ERROR migrating {chat_name}: {exc}")
            summary["chats_errored"] += 1
            summary["chat_results"].append({
                "name": chat_name,
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
    """Create the argument parser for the migrate command."""
    parser = argparse.ArgumentParser(
        prog="whatsapp-migrate",
        description="Migrate legacy WhatsApp transcript.txt files to v2 format (transcript.md + index.md)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input ~/Journal/People/Correspondence/Whatsapp
  %(prog)s --input ~/exports --dry-run
  %(prog)s --input ~/exports --no-backup
        """,
    )

    parser.add_argument(
        "--input",
        type=str,
        required=True,
        metavar="DIR",
        help="Vault WhatsApp directory containing legacy transcripts",
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
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create .bak backup of original transcript.txt files",
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for the migrate command."""
    parser = create_parser()
    args = parser.parse_args(argv)

    input_dir = Path(args.input).expanduser().resolve()

    summary = run_migrate(
        input_dir=input_dir,
        user_display_name=args.user_display_name,
        dry_run=args.dry_run,
        no_backup=args.no_backup,
    )

    return 0 if summary.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
