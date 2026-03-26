"""
Sync command for WhatsApp Chat Auto-Export.

Incremental sync from the MCP bridge — the primary way to keep
transcripts current. Orchestrates:

    Load state -> Preflight (query MCP chats, compare watermarks)
    -> Retry voice queue -> Per-chat sync loop -> Save state
    -> JSON summary to stdout
"""

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...mcp.bridge_reader import BridgeReader, BridgeReaderError, DatabaseNotFoundError
from ...mcp.state import MCPState
from ...output.index_builder import IndexBuilder
from ...output.spec_formatter import SpecFormatter
from ...processing.dedup import find_new_messages
from ...processing.transcript_parser import Message
from ...sources.mcp_source import MCPSource
from ...sources.base import ChatInfo
from ...sources.transcript_source import TranscriptSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jid_to_folder_name(
    jid: str,
    chat_name: Optional[str] = None,
    state: Optional[MCPState] = None,
) -> str:
    """
    Resolve a JID to a filesystem-safe folder name.

    Resolution order:
    1. State contact cache
    2. Chat name from MCPSource
    3. JID with ``@`` and ``.`` stripped (fallback)
    """
    if state:
        cached = state.get_contact_name(jid)
        if cached:
            return _sanitise_folder_name(cached)

    if chat_name:
        return _sanitise_folder_name(chat_name)

    # Fallback: strip the domain part of the JID
    return _sanitise_folder_name(jid.split("@")[0])


def _sanitise_folder_name(name: str) -> str:
    """Make a string safe for use as a directory name."""
    # Remove characters that are problematic on common filesystems
    sanitised = re.sub(r'[<>:"/\\|?*]', '', name)
    # Collapse multiple spaces / trim
    sanitised = re.sub(r'\s+', ' ', sanitised).strip()
    return sanitised or "unknown"


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
# Voice transcription helper
# ---------------------------------------------------------------------------

def _try_transcribe_voice(
    msg: Message,
    mcp_source: MCPSource,
    state: MCPState,
) -> Optional[str]:
    """
    Attempt to transcribe a voice message via ElevenLabs.

    Returns the transcription text on success, or None on failure
    (in which case the message is added to the voice retry queue).
    """
    if not msg.message_id:
        return None

    try:
        media_path = mcp_source.get_media(msg.message_id)
        if not media_path:
            state.add_voice_retry(msg.message_id, "", msg.timestamp)
            return None

        # Late import to avoid hard dependency when transcription is not used
        from ...transcription.elevenlabs_transcriber import ElevenLabsTranscriber

        transcriber = ElevenLabsTranscriber()
        if not transcriber.is_available():
            state.add_voice_retry(msg.message_id, "", msg.timestamp)
            return None

        result = transcriber.transcribe(media_path, skip_existing=True)
        if result.success and result.text:
            return result.text

        state.add_voice_retry(msg.message_id, "", msg.timestamp)
        return None

    except Exception as exc:
        _progress(f"  Voice transcription failed for {msg.message_id}: {exc}")
        state.add_voice_retry(msg.message_id, "", msg.timestamp)
        return None


def _retry_voice_queue(
    state: MCPState,
    mcp_source: MCPSource,
) -> Dict[str, int]:
    """
    Retry queued voice messages that previously failed transcription.

    Returns stats dict with ``retried`` and ``succeeded`` counts.
    """
    retries = state.pop_voice_retries(max_attempts=3)
    if not retries:
        return {"retried": 0, "succeeded": 0}

    _progress(f"Retrying {len(retries)} queued voice transcription(s)...")

    succeeded = 0
    for item in retries:
        try:
            media_path = mcp_source.get_media(item.message_id)
            if not media_path:
                # Re-queue
                state.add_voice_retry(
                    item.message_id,
                    item.chat_jid,
                    datetime.fromisoformat(item.timestamp),
                )
                continue

            from ...transcription.elevenlabs_transcriber import ElevenLabsTranscriber

            transcriber = ElevenLabsTranscriber()
            if not transcriber.is_available():
                state.add_voice_retry(
                    item.message_id,
                    item.chat_jid,
                    datetime.fromisoformat(item.timestamp),
                )
                continue

            result = transcriber.transcribe(media_path, skip_existing=True)
            if result.success and result.text:
                succeeded += 1
            else:
                state.add_voice_retry(
                    item.message_id,
                    item.chat_jid,
                    datetime.fromisoformat(item.timestamp),
                )
        except Exception as exc:
            _progress(f"  Voice retry failed for {item.message_id}: {exc}")
            state.add_voice_retry(
                item.message_id,
                item.chat_jid,
                datetime.fromisoformat(item.timestamp),
            )

    return {"retried": len(retries), "succeeded": succeeded}


# ---------------------------------------------------------------------------
# Per-chat sync
# ---------------------------------------------------------------------------

def _sync_chat(
    chat: ChatInfo,
    mcp_source: MCPSource,
    state: MCPState,
    output_dir: Path,
    spec_formatter: SpecFormatter,
    index_builder: IndexBuilder,
    overlap_minutes: int,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Sync a single chat from the MCP bridge.

    Returns a per-chat result dict.
    """
    jid = chat.jid
    folder_name = _jid_to_folder_name(jid, chat.name, state)
    chat_dir = output_dir / folder_name

    result: Dict[str, Any] = {
        "jid": jid,
        "name": chat.name,
        "folder": folder_name,
        "new_messages": 0,
        "total_messages": 0,
        "status": "ok",
        "is_new_chat": False,
    }

    # Determine watermark and overlap window
    watermark = state.get_watermark(jid)
    fetch_after: Optional[datetime] = None
    if watermark:
        fetch_after = watermark - timedelta(minutes=overlap_minutes)

    # Fetch messages from MCP source
    new_msgs = mcp_source.get_messages(jid, after=fetch_after)
    if not new_msgs:
        result["status"] = "no_new_messages"
        return result

    # Read existing transcript for dedup
    existing_messages: List[Message] = []
    transcript_path = chat_dir / "transcript.md"
    if transcript_path.exists():
        ts = TranscriptSource(output_dir)
        existing_messages = ts.get_messages(folder_name)
    else:
        result["is_new_chat"] = True

    # Dedup: compare fetched messages against existing transcript tail
    # Use last 200 messages as a generous tail for dedup matching
    tail_size = max(200, len(new_msgs))
    existing_tail = existing_messages[-tail_size:] if existing_messages else []
    genuinely_new = find_new_messages(new_msgs, existing_tail)

    if not genuinely_new and not result["is_new_chat"]:
        result["status"] = "no_new_messages"
        return result

    result["new_messages"] = len(genuinely_new)

    # Attempt voice transcription for audio messages
    for msg in genuinely_new:
        if msg.is_media and msg.media_type == "audio" and msg.message_id:
            transcription = _try_transcribe_voice(msg, mcp_source, state)
            if transcription:
                # Inject transcription as content addendum so SpecFormatter
                # picks it up via its _extract_transcription logic
                msg.content = msg.content + f" [Transcription]: {transcription}"

    # Merge existing + new for full transcript
    all_messages = existing_messages + genuinely_new
    all_messages.sort(key=lambda m: (m.timestamp, m.line_number))
    result["total_messages"] = len(all_messages)

    if dry_run:
        result["status"] = "dry_run"
        return result

    # Ensure chat directory exists
    chat_dir.mkdir(parents=True, exist_ok=True)

    # Write transcript.md via SpecFormatter (atomic write)
    transcript_content = spec_formatter.format_transcript(
        messages=all_messages,
        chat_jid=jid,
        contact_name=chat.name or folder_name,
    )
    _atomic_write(transcript_path, transcript_content)

    # Write/update index.md via IndexBuilder
    index_path = chat_dir / "index.md"
    source_entry = {
        "type": "mcp_bridge",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "messages": len(genuinely_new),
    }

    if index_path.exists():
        existing_index = index_path.read_text(encoding="utf-8")
        index_content = index_builder.update_index(
            existing_content=existing_index,
            new_messages=genuinely_new,
            source_entry=source_entry,
        )
    else:
        index_content = index_builder.build_index(
            messages=all_messages,
            chat_jid=jid,
            contact_name=chat.name or folder_name,
            sources=[source_entry],
        )
    _atomic_write(index_path, index_content)

    # Update watermark — use the latest message timestamp
    if genuinely_new:
        latest_ts = max(m.timestamp for m in genuinely_new)
        state.set_watermark(jid, latest_ts)

    # Update contact cache
    if chat.name and chat.name != jid:
        state.set_contact_name(jid, chat.name)

    return result


# ---------------------------------------------------------------------------
# Main sync orchestration
# ---------------------------------------------------------------------------

def run_sync(
    output_dir: Path,
    db_path: Optional[Path] = None,
    state_file: Optional[Path] = None,
    dry_run: bool = False,
    chat_filter: Optional[str] = None,
    overlap_minutes: int = 10,
    user_display_name: str = "AJ Anderson",
) -> Dict[str, Any]:
    """
    Run the incremental sync from MCP bridge.

    This is the programmatic entry point — the CLI argument parser calls
    this function with resolved arguments.

    Args:
        output_dir: Vault output directory.
        db_path: MCP bridge SQLite path (auto-detect if None).
        state_file: State file path (default: <output>/.sync-state.json).
        dry_run: If True, report what would change without writing.
        chat_filter: If set, only sync chats whose name contains this string.
        overlap_minutes: Overlap window in minutes for watermark queries.
        user_display_name: Display name for "from me" messages.

    Returns:
        JSON-serialisable summary dict.
    """
    summary: Dict[str, Any] = {
        "success": False,
        "timestamp": datetime.now().isoformat(),
        "dry_run": dry_run,
        "chats_synced": 0,
        "chats_skipped": 0,
        "chats_errored": 0,
        "total_new_messages": 0,
        "chat_results": [],
        "voice_retry": {"retried": 0, "succeeded": 0},
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

    # ---- 3. Preflight: query chats ----
    _progress("Querying MCP bridge for chats...")
    try:
        all_chats = mcp_source.get_chats()
    except Exception as exc:
        summary["error"] = f"Failed to query MCP chats: {exc}"
        _json_summary(summary)
        return summary

    if not all_chats:
        summary["error"] = "No chats found in MCP bridge"
        _json_summary(summary)
        return summary

    _progress(f"Found {len(all_chats)} chat(s) in MCP bridge")

    # ---- 4. Compare watermarks → build changed-chats list ----
    changed_chats: List[ChatInfo] = []
    skipped_chats: List[str] = []

    for chat in all_chats:
        # Apply chat filter if specified
        if chat_filter:
            if chat_filter.lower() not in (chat.name or "").lower():
                continue

        watermark = state.get_watermark(chat.jid)
        if watermark and chat.last_message_time:
            if chat.last_message_time <= watermark:
                skipped_chats.append(chat.jid)
                continue

        changed_chats.append(chat)

    summary["chats_skipped"] = len(skipped_chats)
    _progress(
        f"Changed: {len(changed_chats)} | "
        f"Unchanged: {len(skipped_chats)}"
    )

    # ---- 5. Retry voice queue ----
    if not dry_run:
        voice_stats = _retry_voice_queue(state, mcp_source)
        summary["voice_retry"] = voice_stats

    # ---- 6. Create formatters ----
    spec_formatter = SpecFormatter(user_display_name=user_display_name)
    index_builder = IndexBuilder(user_display_name=user_display_name)

    # ---- 7. Per-chat sync loop ----
    for chat in changed_chats:
        _progress(f"Syncing: {chat.name or chat.jid}")
        try:
            chat_result = _sync_chat(
                chat=chat,
                mcp_source=mcp_source,
                state=state,
                output_dir=output_dir,
                spec_formatter=spec_formatter,
                index_builder=index_builder,
                overlap_minutes=overlap_minutes,
                dry_run=dry_run,
            )
            summary["chat_results"].append(chat_result)

            if chat_result["status"] in ("ok", "dry_run"):
                summary["chats_synced"] += 1
                summary["total_new_messages"] += chat_result["new_messages"]
            elif chat_result["status"] == "no_new_messages":
                summary["chats_skipped"] += 1

        except Exception as exc:
            _progress(f"  ERROR syncing {chat.name or chat.jid}: {exc}")
            traceback.print_exc(file=sys.stderr)
            summary["chats_errored"] += 1
            summary["chat_results"].append({
                "jid": chat.jid,
                "name": chat.name,
                "status": "error",
                "error": str(exc),
            })

    # ---- 8. Save state ----
    if not dry_run:
        try:
            state.save(effective_state_file)
            _progress(f"State saved to {effective_state_file}")
        except Exception as exc:
            _progress(f"WARNING: Failed to save state: {exc}")
            summary["error"] = f"State save failed: {exc}"

    summary["success"] = summary["chats_errored"] == 0 and summary["error"] is None
    _json_summary(summary)
    return summary


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the sync command."""
    parser = argparse.ArgumentParser(
        prog="whatsapp-sync",
        description="Incremental sync from WhatsApp MCP bridge to vault transcripts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --output ~/Journal/People/Correspondence/Whatsapp
  %(prog)s --output ~/exports --dry-run
  %(prog)s --output ~/exports --chat "Alice"
  %(prog)s --output ~/exports --db-path /path/to/messages.db
        """,
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
        "--dry-run",
        action="store_true",
        help="Report what would change without writing files",
    )
    parser.add_argument(
        "--chat",
        type=str,
        default=None,
        metavar="NAME",
        help="Sync only chats whose name contains NAME",
    )
    parser.add_argument(
        "--overlap-minutes",
        type=int,
        default=10,
        metavar="N",
        help="Overlap window in minutes for watermark queries (default: 10)",
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
    """CLI entry point for the sync command."""
    parser = create_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output).expanduser().resolve()
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else None
    state_file = Path(args.state_file).expanduser().resolve() if args.state_file else None

    summary = run_sync(
        output_dir=output_dir,
        db_path=db_path,
        state_file=state_file,
        dry_run=args.dry_run,
        chat_filter=args.chat,
        overlap_minutes=args.overlap_minutes,
        user_display_name=args.user_display_name,
    )

    return 0 if summary.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
