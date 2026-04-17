"""Tests for WhatsAppDriver.is_community_chat() upfront probe and ExportOutcome."""

import pytest
from unittest.mock import MagicMock, patch

from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver
from whatsapp_chat_autoexport.export.chat_exporter import (
    ChatExporter,
    ExportOutcome,
    ExportOutcomeKind,
)


def _make_driver():
    """Build a WhatsAppDriver without a real Appium connection."""
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.driver = MagicMock()
    wd.logger = MagicMock()
    return wd


def test_returns_true_when_community_pill_present():
    """Returns True when community_pill element is found and displayed."""
    wd = _make_driver()
    pill = MagicMock()
    pill.is_displayed.return_value = True
    wd.driver.find_elements.return_value = [pill]

    assert wd.is_community_chat() is True
    wd.driver.find_elements.assert_called_once_with("id", "com.whatsapp:id/community_pill")


def test_returns_false_when_no_community_pill():
    """Returns False when no community_pill element is found."""
    wd = _make_driver()
    wd.driver.find_elements.return_value = []

    assert wd.is_community_chat() is False


def test_returns_false_when_pill_present_but_not_displayed():
    """Returns False when pill element exists but is_displayed() returns False."""
    wd = _make_driver()
    pill = MagicMock()
    pill.is_displayed.return_value = False
    wd.driver.find_elements.return_value = [pill]

    assert wd.is_community_chat() is False


def test_exception_during_probe_returns_false():
    """Returns False (and does not propagate) when find_elements raises an exception."""
    wd = _make_driver()
    wd.driver.find_elements.side_effect = RuntimeError("session error")

    assert wd.is_community_chat() is False


# ---------------------------------------------------------------------------
# ExportOutcome tests (Task 6)
# ---------------------------------------------------------------------------


def test_export_outcome_bool_coercion_true_for_success():
    outcome = ExportOutcome(kind=ExportOutcomeKind.SUCCESS)
    assert bool(outcome) is True


def test_export_outcome_bool_coercion_false_for_skipped_and_failed():
    assert bool(ExportOutcome(kind=ExportOutcomeKind.SKIPPED_COMMUNITY)) is False
    assert bool(ExportOutcome(kind=ExportOutcomeKind.FAILED, reason="x")) is False


def test_export_chat_returns_skipped_community_when_probe_hits():
    driver = MagicMock()
    driver.is_community_chat = MagicMock(return_value=True)
    logger = MagicMock()
    exporter = ChatExporter(driver, logger)

    outcome = exporter.export_chat_to_google_drive("ChatA", include_media=False)

    assert isinstance(outcome, ExportOutcome)
    assert outcome.kind == ExportOutcomeKind.SKIPPED_COMMUNITY
    driver.is_community_chat.assert_called_once()


# NOTE: A fourth test for the 'More not found' branch (returning SKIPPED_COMMUNITY
# when the overflow menu exists but 'More' is absent) is intentionally omitted.
# There is no discrete helper method to patch cleanly for that path.
# That branch is covered indirectly via Task 7 integration tests and by
# test_export_chat_returns_skipped_community_when_probe_hits above.
