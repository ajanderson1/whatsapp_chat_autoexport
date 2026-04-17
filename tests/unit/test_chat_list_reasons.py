"""Tests for reason propagation on ChatListWidget.update_chat_status."""

from whatsapp_chat_autoexport.tui.textual_widgets.chat_list import (
    ChatListWidget,
    ChatDisplayStatus,
)


def test_update_chat_status_stores_reason():
    widget = ChatListWidget(chats=["ChatA", "ChatB"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="Verify failed")
    reasons = widget.get_status_reasons()
    assert reasons.get("ChatA") == "Verify failed"


def test_update_chat_status_without_reason_clears_previous_reason():
    widget = ChatListWidget(chats=["ChatA"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="first")
    widget.update_chat_status("ChatA", ChatDisplayStatus.COMPLETED)
    assert widget.get_status_reasons().get("ChatA") is None


def test_get_status_reasons_returns_copy():
    widget = ChatListWidget(chats=["ChatA"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.FAILED, reason="x")
    copy = widget.get_status_reasons()
    copy["ChatA"] = "mutated"
    assert widget.get_status_reasons().get("ChatA") == "x"


def test_update_chat_status_no_reason_arg_is_backwards_compatible():
    """Existing call sites that don't pass `reason` must continue to work."""
    widget = ChatListWidget(chats=["ChatA"])
    widget.update_chat_status("ChatA", ChatDisplayStatus.COMPLETED)
    assert widget.chat_statuses.get("ChatA") == ChatDisplayStatus.COMPLETED
