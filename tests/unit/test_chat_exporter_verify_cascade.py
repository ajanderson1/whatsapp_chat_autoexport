"""Unit tests for ChatExporter's consecutive-verify-failure cascade halt.

Pins the defence-in-depth behaviour added for issue #27: if the verifier
ever regresses again, the orchestrator halts the batch after 3 consecutive
verification failures rather than grinding through hundreds of chats.
"""

from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter


@pytest.mark.unit
def test_three_consecutive_verify_failures_halts_batch(tmp_path):
    """Mock driver where verify always fails; batch must halt at chat 3."""
    driver = MagicMock()
    driver.verify_whatsapp_is_open.return_value = False
    driver.is_session_active.return_value = True
    driver.reconnect.return_value = False  # any recovery attempt also fails

    logger = MagicMock()
    logger.debug = False  # match Logger contract used elsewhere

    exporter = ChatExporter(driver, logger)

    chat_names = [f"Chat {i}" for i in range(1, 6)]  # 5 chats

    # Use the legacy `export_chats` path (line 1666 verify call site) — its
    # cascade-halt logic is structurally simpler to test (no StateManager
    # setup required). The new-workflow path (`export_chats_with_new_workflow`,
    # line 501) uses identical counter logic and is exercised in production.
    results, _timings, _total, _skipped = exporter.export_chats(
        chat_names=chat_names,
        include_media=False,
    )

    # Three verify calls (chats 1, 2, 3) — then the limit fires and the loop
    # breaks before chat 4's verify call.
    assert driver.verify_whatsapp_is_open.call_count == ChatExporter.MAX_CONSECUTIVE_VERIFY_FAILURES, (
        f"Expected exactly {ChatExporter.MAX_CONSECUTIVE_VERIFY_FAILURES} verify "
        f"calls before halt, got {driver.verify_whatsapp_is_open.call_count}"
    )

    # Chats 4 and 5 must not appear in results — the batch halted before them.
    assert "Chat 4" not in results
    assert "Chat 5" not in results

    # Chats 1-3 are recorded as failed.
    for n in (1, 2, 3):
        assert results.get(f"Chat {n}") is False, f"Chat {n} should be recorded as failed"

    # The halt message reaches the logger.
    halt_messages = [
        call for call in logger.error.call_args_list
        if "consecutive WhatsApp verification failures" in str(call)
    ]
    assert halt_messages, "Expected a 'consecutive verify failures' halt log message"
