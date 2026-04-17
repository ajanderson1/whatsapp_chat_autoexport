"""Tests for the foreground-settle helper used before verify_whatsapp_is_open()."""

import pytest
from unittest.mock import MagicMock

from whatsapp_chat_autoexport.export.foreground_wait import (
    wait_for_whatsapp_foreground,
)


class FakeAppiumDriver:
    """Minimal stand-in for the Appium driver with scripted current_package values."""

    def __init__(self, packages):
        # packages: list consumed one per read; last value sticks
        self._packages = list(packages)

    @property
    def current_package(self):
        if len(self._packages) > 1:
            return self._packages.pop(0)
        return self._packages[0]


class FakeDriverWrapper:
    """Stand-in for WhatsAppDriver exposing the .driver attribute and a logger."""

    def __init__(self, packages):
        self.driver = FakeAppiumDriver(packages)
        self.logger = MagicMock()


def test_returns_true_when_already_foreground():
    wrapper = FakeDriverWrapper(["com.whatsapp"])
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_returns_true_after_transient_non_whatsapp_package():
    wrapper = FakeDriverWrapper(
        ["com.android.intentresolver", "com.android.intentresolver", "com.whatsapp"]
    )
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_returns_false_on_timeout():
    wrapper = FakeDriverWrapper(["com.google.android.apps.docs"])
    assert wait_for_whatsapp_foreground(wrapper, timeout=0.5, poll_interval=0.05) is False


def test_exceptions_during_probe_are_treated_as_not_foreground():
    wrapper = FakeDriverWrapper(["com.whatsapp"])
    # Replace current_package with a raising property for the first N calls
    calls = {"n": 0}

    class RaisingDriver:
        @property
        def current_package(self):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("session flaking")
            return "com.whatsapp"

    wrapper.driver = RaisingDriver()
    assert wait_for_whatsapp_foreground(wrapper, timeout=1.0, poll_interval=0.01) is True


def test_logs_when_wait_occurs(caplog):
    wrapper = FakeDriverWrapper(["com.android.intentresolver", "com.whatsapp"])
    wait_for_whatsapp_foreground(wrapper, timeout=0.5, poll_interval=0.01)
    # Logger is a MagicMock on the wrapper; ensure at least one debug/info call happened
    assert wrapper.logger.debug_msg.called or wrapper.logger.info.called


from unittest.mock import patch


def test_whatsappdriver_method_delegates_to_helper():
    """WhatsAppDriver.wait_for_whatsapp_foreground should call the helper."""
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

    # Build a WhatsAppDriver without actually connecting
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.driver = MagicMock()
    wd.driver.current_package = "com.whatsapp"
    wd.logger = MagicMock()

    with patch(
        "whatsapp_chat_autoexport.export.whatsapp_driver.wait_for_whatsapp_foreground",
        return_value=True,
    ) as mock_helper:
        result = wd.wait_for_whatsapp_foreground(timeout=2.0, poll_interval=0.05)

    assert result is True
    mock_helper.assert_called_once_with(wd, timeout=2.0, poll_interval=0.05)
