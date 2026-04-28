"""
Rebuild command for WhatsApp Chat Auto-Export.

Fetches full history for a single chat from MCPSource (no watermark
filter), writes fresh transcript.md + index.md replacing any existing
files, and resets the watermark in state.

    CLI: poetry run whatsapp-rebuild <chat-name-or-jid> --output <vault-dir>
    JSON summary to stdout, progress to stderr.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...mcp.bridge_reader import BridgeReader
from ...mcp.state import MCPState
from ...output.index_builder import IndexBuilder
from ...output.spec_formatter import SpecFormatter
from ...processing.transcript_parser import Message
from ...sources.base import ChatInfo
from ...sources.mcp_source import MCPSource


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


def _sanitise_folder_name(name: str) -> str:
    """Make a string safe for use as a directory name."""
    sanitised = re.sub(r'[<>:"/\\|?*]', '', name)
    sanitised = re.sub(r'\s+', ' ', sanitised).strip()
    return sanitised or "unknown"


def _resolve_chat(
    chat_identifier: str,
    mcp_source: MCPSource,
) -> Optional[ChatInfo]:
    """
    Resolve a chat name or JID to a ChatInfo object.

    Tries exact JID match first, then case-insensitive name substring.
    """
    chats = mcp_source.get_chats()

    # Exact JID match
    for chat in chats:
        if chat.jid == chat_identifier:
            return chat

    # Name substring match (case-insensitive)
    lower_id = chat_identifier.lower()
    matches = [c for c in chats if lower_id in (c.name or "").lower()]

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        _progress(
            f"Ambiguous chat identifier '{chat_identifier}' matches "
            f"{len(matches)} chats: {[c.name for c in matches]}"
        )
        return None

    return None


# ---------------------------------------------------------------------------
# Main rebuild orchestration
# ---------------------------------------------------------------------------

def run_rebuild(
    chat_identifier: str,
    output_dir: Path,
    db_path: Optional[Path] = None,
    state_file: Optional[Path] = None,
    user_display_name: str = "AJ Anderson",
) -> Dict[str, Any]:
    """
    Rebuild a single chat from MCP bridge (full history, no watermark).

    This is the programmatic entry point -- the CLI argument parser calls
    this function with resolved arguments.

    Args:
        chat_identifier: Chat name or JID to rebuild.
        output_dir: Vault output directory for transcripts.
        db_path: MCP bridge SQLite path (auto-detect if None).
        state_file: State file path (default: <output>/.sync-state.json).
        user_display_name: Display name for "from me" messages.

    Returns:
        JSON-serialisable summary dict.
    """
    summary: Dict[str, Any] = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "chat_identifier": chat_identifier,
        "output_dir": str(output_dir),
        "chat_name": None,
        "chat_jid": None,
        "message_count": 0,
        "status": "ok",
        "error": None,
    }

    # ---- 1. Load state ----
    effective_state_file = state_file or (output_dir / ".sync-state.json")
    _progress(f"Loading state from {effective_state_file}")
    state = MCPState.load(effective_state_file)

    # ---- 2. Create MCP source ----
    try:
        source_kwargs: Dict[str, Any] = {"user_display_name": user_display_name}
        if db_path:
            source_kwargs["db_path"] = db_path
        mcp_source = MCPSource(**source_kwargs)
    except Exception as exc:
        summary["error"] = f"Failed to create MCP source: {exc}"
        _json_summary(summary)
        return summary

    # ---- 3. Resolve chat ----
    _progress(f"Resolving chat: {chat_identifier}")
    chat = _resolve_chat(chat_identifier, mcp_source)

    if chat is None:
        summary["error"] = f"Chat not found: {chat_identifier}"
        _json_summary(summary)
        return summary

    summary["chat_name"] = chat.name
    summary["chat_jid"] = chat.jid
    _progress(f"Resolved to: {chat.name} ({chat.jid})")

    # ---- 4. Fetch full message history (no watermark filter) ----
    _progress(f"Fetching full history for {chat.name}...")
    try:
        messages = mcp_source.get_messages(chat.jid)
    except Exception as exc:
        summary["error"] = f"Failed to fetch messages: {exc}"
        _json_summary(summary)
        return summary

    if not messages:
        summary["error"] = f"No messages found for {chat.name}"
        _json_summary(summary)
        return summary

    messages.sort(key=lambda m: (m.timestamp, m.line_number))
    summary["message_count"] = len(messages)
    _progress(f"Fetched {len(messages)} messages")

    # ---- 5. Create formatters ----
    spec_formatter = SpecFormatter(user_display_name=user_display_name)
    index_builder = IndexBuilder(user_display_name=user_display_name)

    # ---- 6. Write transcript.md + index.md ----
    folder_name = _sanitise_folder_name(chat.name or chat.jid.split("@")[0])
    chat_dir = output_dir / folder_name
    chat_dir.mkdir(parents=True, exist_ok=True)

    # Write transcript.md
    transcript_path = chat_dir / "transcript.md"
    transcript_content = spec_formatter.format_transcript(
        messages=messages,
        chat_jid=chat.jid,
        contact_name=chat.name or folder_name,
    )
    _atomic_write(transcript_path, transcript_content)
    _progress(f"Wrote {transcript_path}")

    # Write index.md (fresh, replacing any existing)
    index_path = chat_dir / "index.md"
    source_entry = {
        "type": "mcp_rebuild",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "messages": len(messages),
    }
    index_content = index_builder.build_index(
        messages=messages,
        chat_jid=chat.jid,
        contact_name=chat.name or folder_name,
        sources=[source_entry],
    )
    _atomic_write(index_path, index_content)
    _progress(f"Wrote {index_path}")

    # ---- 7. Reset watermark in state ----
    if messages:
        latest_ts = max(m.timestamp for m in messages)
        state.set_watermark(chat.jid, latest_ts)
        _progress(f"Watermark reset to {latest_ts.isoformat()}")

    # Update contact cache
    if chat.name and chat.name != chat.jid:
        state.set_contact_name(chat.jid, chat.name)

    # ---- 8. Save state ----
    try:
        state.save(effective_state_file)
        _progress(f"State saved to {effective_state_file}")
    except Exception as exc:
        _progress(f"WARNING: Failed to save state: {exc}")
        summary["error"] = f"State save failed: {exc}"

    summary["success"] = summary["error"] is None
    _json_summary(summary)
    return summary


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the rebuild command."""
    parser = argparse.ArgumentParser(
        prog="whatsapp-rebuild",
        description="Rebuild a single chat from the WhatsApp MCP bridge (full history)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Alice Smith" --output ~/Journal/People/Correspondence/Whatsapp
  %(prog)s alice@s.whatsapp.net --output ~/exports
  %(prog)s "Alice" --output ~/exports --db-path /path/to/messages.db
        """,
    )

    parser.add_argument(
        "chat",
        type=str,
        metavar="CHAT",
        help="Chat name or JID to rebuild",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        metavar="DIR",
        help="Vault output directory for transcripts",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        metavar="PATH",
        help="MCP bridge SQLite database path (default: auto-detect)",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        metavar="PATH",
        help="State file path (default: <output>/.sync-state.json)",
    )
    parser.add_argument(
        "--user-display-name",
        type=str,
        default="AJ Anderson",
        metavar="NAME",
        help='Display name for "from me" messages (default: "AJ Anderson")',
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for the rebuild command."""
    parser = create_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output).expanduser().resolve()
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else None
    state_file = Path(args.state_file).expanduser().resolve() if args.state_file else None

    summary = run_rebuild(
        chat_identifier=args.chat,
        output_dir=output_dir,
        db_path=db_path,
        state_file=state_file,
        user_display_name=args.user_display_name,
    )

    return 0 if summary.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
