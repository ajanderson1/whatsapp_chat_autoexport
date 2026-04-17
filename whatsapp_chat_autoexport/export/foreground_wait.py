"""
Pre-verify settle wait.

Polls the Appium driver's `current_package` for up to `timeout` seconds,
returning True as soon as WhatsApp becomes the foreground package.
Targets the race where `verify_whatsapp_is_open()` runs before Android
has handed focus back from the Google Drive share activity.
"""

import time
from typing import Any


WHATSAPP_PACKAGE = "com.whatsapp"


def wait_for_whatsapp_foreground(
    driver_wrapper: Any,
    timeout: float = 8.0,
    poll_interval: float = 0.25,
) -> bool:
    """
    Wait up to `timeout` seconds for `com.whatsapp` to be the foreground package.

    Args:
        driver_wrapper: Object exposing `.driver.current_package` and `.logger`.
                        In production this is `WhatsAppDriver`.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between package probes.

    Returns:
        True as soon as the package is `com.whatsapp`. False if the timeout
        elapses without WhatsApp becoming foreground. Exceptions during the
        probe are swallowed and treated as "not yet foreground".
    """
    logger = getattr(driver_wrapper, "logger", None)
    deadline = time.monotonic() + timeout
    attempts = 0
    last_seen = None

    while True:
        attempts += 1
        try:
            pkg = driver_wrapper.driver.current_package
        except Exception as e:
            pkg = None
            if logger is not None:
                logger.debug_msg(f"[settle] probe {attempts} raised: {e}")

        if pkg == WHATSAPP_PACKAGE:
            if attempts > 1 and logger is not None:
                logger.info(
                    f"[settle] WhatsApp foreground after {attempts} probe(s)"
                )
            return True

        if pkg != last_seen:
            last_seen = pkg
            if logger is not None:
                logger.debug_msg(f"[settle] current_package={pkg!r}; waiting")

        if time.monotonic() >= deadline:
            if logger is not None:
                logger.debug_msg(
                    f"[settle] timeout after {attempts} probe(s); last_seen={last_seen!r}"
                )
            return False

        time.sleep(poll_interval)
