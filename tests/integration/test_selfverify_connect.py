"""Tests for the C1 connect-verify harness (scripts/selfverify_connect.py).

The harness exercises the driver's real connection path and STOPS before
any export. We mock WhatsAppDriver so this runs without a device.
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from scripts.selfverify_connect import _build_driver, connect_and_verify


@pytest.mark.integration
def test_connect_and_verify_returns_zero_and_never_exports():
    driver = MagicMock()
    driver.check_device_connection.return_value = True
    driver.connect.return_value = True
    driver.device_id = "192.168.1.50:5555"

    rc = connect_and_verify(driver)

    assert rc == 0
    driver.check_device_connection.assert_called_once()
    driver.connect.assert_called_once()
    # The whole point of C1: only these two methods may have been called.
    # This catches any real export method added in future (not just export_chats).
    called = {c[0] for c in driver.mock_calls}
    assert called == {"check_device_connection", "connect"}


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_device_absent():
    driver = MagicMock()
    driver.check_device_connection.return_value = False

    rc = connect_and_verify(driver)

    assert rc == 2
    driver.connect.assert_not_called()


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_connect_fails():
    driver = MagicMock()
    driver.check_device_connection.return_value = True
    driver.connect.return_value = False

    rc = connect_and_verify(driver)

    assert rc == 3


@pytest.mark.integration
def test_build_driver_passes_project_logger_with_debug_msg():
    """Regression guard: the harness must hand WhatsAppDriver the project's
    Logger (which has debug_msg), not a stdlib logging.Logger.

    A live run with a stdlib logger crashed at the driver's first
    `self.logger.debug_msg(...)` call. A bare MagicMock would have hidden
    this by fabricating debug_msg, so we assert the real interface instead.
    """
    with patch("whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver") as mock_driver_cls:
        args = argparse.Namespace(wireless_adb="192.168.1.50:5555")
        _build_driver(args)

    # WhatsAppDriver was constructed exactly once, with a logger keyword.
    mock_driver_cls.assert_called_once()
    logger = mock_driver_cls.call_args.kwargs["logger"]

    # The logger must satisfy the driver's real contract: debug_msg is the
    # method whose absence broke the live run. Assert it exists and is callable.
    assert hasattr(logger, "debug_msg"), "harness logger lacks debug_msg"
    assert callable(logger.debug_msg)
    # And it must be the project's Logger, not stdlib logging.Logger.
    import logging as _stdlib_logging

    from whatsapp_chat_autoexport.utils.logger import Logger as ProjectLogger

    assert isinstance(logger, ProjectLogger)
    assert not isinstance(logger, _stdlib_logging.Logger)

    # wireless_adb arg is forwarded as the List[str] the driver expects.
    assert mock_driver_cls.call_args.kwargs["wireless_adb"] == ["192.168.1.50:5555"]
