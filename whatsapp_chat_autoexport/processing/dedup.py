"""
Deduplication engine for WhatsApp Chat Auto-Export.

Provides two modes of deduplication:
- Full dedup: merge messages from any combination of sources
- Incremental dedup: find genuinely new messages given an existing tail

Dedup key logic:
- Every message always gets a compound key: hash(timestamp_to_minute + sender + content[:80])
- MCP messages additionally get an ID key: id:{message_id}
- A message is a duplicate if ANY of its keys match an already-seen key

Conflict resolution:
- Same key from two sources -> prefer source="mcp" (better timestamps + IDs)
- Same timestamp + sender but different content -> keep both (not duplicates)
"""

import hashlib
from typing import List, Set

from .transcript_parser import Message


# Source priority: higher number = preferred when deduplicating
_SOURCE_PRIORITY = {
    "mcp": 10,
    "appium": 5,
    "transcript": 3,
    "unknown": 0,
}


def _source_priority(source: str) -> int:
    """Return numeric priority for a source (higher = preferred)."""
    return _SOURCE_PRIORITY.get(source, 0)


def _compound_key(msg: Message) -> str:
    """
    Generate a compound dedup key from timestamp (truncated to minute),
    sender, and first 80 chars of content.
    """
    ts_minute = msg.timestamp.strftime("%Y-%m-%d %H:%M")
    raw = f"{ts_minute}|{msg.sender}|{msg.content[:80]}"
    return f"ck:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _all_keys(msg: Message) -> List[str]:
    """
    Return all dedup keys for a message.

    Every message gets a compound key. MCP messages additionally get an
    ID-based key. This ensures cross-source matching works even when one
    source has message_id and the other doesn't.
    """
    keys = [_compound_key(msg)]
    if msg.message_id:
        keys.append(f"id:{msg.message_id}")
    return keys


def _dedup_key(msg: Message) -> str:
    """
    Return the primary dedup key for a message.

    Uses message_id when available (MCP source), otherwise the compound key.
    Used for display/debugging — the actual dedup logic uses _all_keys().
    """
    if msg.message_id:
        return f"id:{msg.message_id}"
    return _compound_key(msg)


def deduplicate(messages: List[Message]) -> List[Message]:
    """
    Full dedup: takes messages from any combination of sources, returns a
    deduplicated, chronologically sorted list.

    When two messages share any dedup key, the one from the higher-priority
    source is kept (MCP > Appium > transcript > unknown).

    Args:
        messages: Messages from any combination of sources.

    Returns:
        Deduplicated list sorted by timestamp (then by line_number for
        stable ordering of same-timestamp messages).
    """
    if not messages:
        return []

    # Map any dedup key -> the best message for that key's group
    # Also track which group each message belongs to (by a canonical group ID)
    key_to_group: dict[str, int] = {}
    group_best: dict[int, Message] = {}
    next_group = 0

    for msg in messages:
        keys = _all_keys(msg)

        # Find if any key already belongs to a group
        existing_groups = set()
        for k in keys:
            if k in key_to_group:
                existing_groups.add(key_to_group[k])

        if not existing_groups:
            # New message — create a new group
            group_id = next_group
            next_group += 1
            for k in keys:
                key_to_group[k] = group_id
            group_best[group_id] = msg
        else:
            # Merge into the lowest-numbered existing group
            group_id = min(existing_groups)
            # Point all keys to this group
            for k in keys:
                key_to_group[k] = group_id
            # Also re-point any other groups that were found
            for old_group in existing_groups:
                if old_group != group_id:
                    # Merge: move the best from old group if better
                    if old_group in group_best:
                        old_best = group_best.pop(old_group)
                        if _source_priority(old_best.source) > _source_priority(
                            group_best.get(group_id, msg).source
                        ):
                            group_best[group_id] = old_best
                    # Re-point all keys from old group
                    for kk, gg in list(key_to_group.items()):
                        if gg == old_group:
                            key_to_group[kk] = group_id

            # Compare this message against the current best for the group
            current_best = group_best.get(group_id)
            if current_best is None or _source_priority(msg.source) > _source_priority(
                current_best.source
            ):
                group_best[group_id] = msg

    result = list(group_best.values())
    result.sort(key=lambda m: (m.timestamp, m.line_number))
    return result


def find_new_messages(
    new_messages: List[Message],
    existing_tail: List[Message],
) -> List[Message]:
    """
    Incremental dedup: given new messages and the tail of an existing
    transcript, returns only genuinely new messages.

    This is optimised for the sync use-case where we fetch messages with
    an overlap window and need to filter out those already in the transcript.

    Args:
        new_messages: Freshly fetched messages (e.g. from MCP with overlap).
        existing_tail: The last N messages from the existing transcript.

    Returns:
        Messages from new_messages that are not already in existing_tail,
        sorted chronologically.
    """
    if not new_messages:
        return []

    if not existing_tail:
        # Nothing to compare against — everything is new
        result = list(new_messages)
        result.sort(key=lambda m: (m.timestamp, m.line_number))
        return result

    # Build set of all dedup keys from the existing tail
    existing_keys: Set[str] = set()
    for msg in existing_tail:
        existing_keys.update(_all_keys(msg))

    # A new message is novel only if NONE of its keys match existing
    novel = []
    for msg in new_messages:
        msg_keys = _all_keys(msg)
        if not any(k in existing_keys for k in msg_keys):
            novel.append(msg)

    novel.sort(key=lambda m: (m.timestamp, m.line_number))
    return novel
