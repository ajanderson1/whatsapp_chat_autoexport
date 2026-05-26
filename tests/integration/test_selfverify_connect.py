"""Tests for the C1 connect-verify harness (scripts/selfverify_connect.py).

The harness exercises the driver's real connection path and STOPS before
any export. We mock WhatsAppDriver so this runs without a device.
"""

from unittest.mock import MagicMock

import pytest

from scripts.selfverify_connect import connect_and_verify


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
    # The whole point of C1: it must never trigger an export.
    driver.export_chats.assert_not_called()


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_device_absent():
    driver = MagicMock()
    driver.check_device_connection.return_value = False

    rc = connect_and_verify(driver)

    assert rc != 0
    driver.connect.assert_not_called()


@pytest.mark.integration
def test_connect_and_verify_returns_nonzero_when_connect_fails():
    driver = MagicMock()
    driver.check_device_connection.return_value = True
    driver.connect.return_value = False

    rc = connect_and_verify(driver)

    assert rc != 0
