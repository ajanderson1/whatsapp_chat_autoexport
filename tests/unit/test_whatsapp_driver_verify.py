"""Unit tests for WhatsAppDriver.verify_whatsapp_is_open().

Covers the post-fix behaviour: verifier trusts package + activity + lock-screen
checks. The legacy resource-ID probe has been removed (issue #27), so verify
must succeed even when no WhatsApp element IDs are visible.
"""

from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver


def _make_driver(
    *,
    current_package: str = "com.whatsapp",
    current_activity: str = "com.whatsapp.HomeActivity",
    is_locked: bool = False,
    lock_reason: str = "screen on, unlocked",
) -> WhatsAppDriver:
    """Build a WhatsAppDriver with its Appium driver and lock check mocked.

    The verifier reads `driver.current_package` and `driver.current_activity`
    via `safe_driver_call`, and calls `self.check_if_phone_locked()`. Mock
    those three points and the verifier becomes deterministic.
    """
    wd = WhatsAppDriver.__new__(WhatsAppDriver)
    wd.driver = MagicMock()
    wd.driver.current_package = current_package
    wd.driver.current_activity = current_activity
    wd.logger = MagicMock()
    wd.safe_driver_call = MagicMock(side_effect=lambda _label, fn, **_kw: fn())
    wd.check_if_phone_locked = MagicMock(return_value=(is_locked, lock_reason))
    return wd


@pytest.mark.unit
def test_verify_returns_true_when_package_and_activity_safe():
    """Material 3 happy path: no legacy IDs visible, package + activity safe."""
    wd = _make_driver()
    assert wd.verify_whatsapp_is_open() is True


@pytest.mark.unit
def test_verify_returns_false_when_package_not_whatsapp():
    """Settings or another app foregrounded — must hard-fail."""
    wd = _make_driver(current_package="com.android.settings")
    assert wd.verify_whatsapp_is_open() is False


@pytest.mark.unit
def test_verify_returns_false_when_activity_unsafe():
    """Lock screen / system UI / settings activity must hard-fail."""
    wd = _make_driver(current_activity="com.android.systemui.Keyguard")
    assert wd.verify_whatsapp_is_open() is False


@pytest.mark.unit
def test_verify_returns_false_when_phone_locked():
    """Final lock check (Check 4) still fires after package + activity pass."""
    wd = _make_driver(is_locked=True, lock_reason="phone is locked")
    assert wd.verify_whatsapp_is_open() is False
