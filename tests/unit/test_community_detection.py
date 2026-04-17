"""Tests for WhatsAppDriver.is_community_chat() upfront probe."""

import pytest
from unittest.mock import MagicMock

from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver


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
