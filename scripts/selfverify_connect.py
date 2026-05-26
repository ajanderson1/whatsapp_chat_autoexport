"""C1 self-verification primitive: connect to the device, verify, exit.

Exercises the exact connection path used by headless export
(WhatsAppDriver.check_device_connection -> connect) and STOPS before any
export. Run this in the cmux pane during the self-verification loop; confirm
its claims out-of-band with `adb devices` / screencap (the L0 oracle).

Usage:
    uv run python -m scripts.selfverify_connect [--wireless-adb [IP:PORT]]
"""

from __future__ import annotations

import argparse
import logging
import sys
from logging import Logger
from typing import Protocol


class _ConnectableDriver(Protocol):
    device_id: str | None

    def check_device_connection(self) -> bool: ...

    def connect(self) -> bool: ...


def connect_and_verify(driver: _ConnectableDriver) -> int:
    """Run the driver's connection path and return a shell exit code.

    Returns 0 on a verified connection, non-zero otherwise. Never exports.
    """
    if not driver.check_device_connection():
        return 2
    if not driver.connect():
        return 3
    print(f"C1 OK: connected to device {driver.device_id}")
    return 0


def _wireless_adb_arg(value) -> list[str] | None:
    """Translate the argparse --wireless-adb value into the List[str] the
    WhatsAppDriver constructor expects.

    --wireless-adb absent          -> None (USB / auto)
    --wireless-adb (no value)      -> [] (wireless, auto-discover)
    --wireless-adb IP:PORT         -> ["IP:PORT"]
    """
    if value is None:
        return None
    if value is True:
        return []
    return [value]


def _build_driver(args: argparse.Namespace, logger: Logger):
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

    return WhatsAppDriver(logger=logger, wireless_adb=_wireless_adb_arg(args.wireless_adb))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C1 connect-verify harness")
    parser.add_argument(
        "--wireless-adb",
        nargs="?",
        const=True,
        default=None,
        metavar="IP:PORT",
        help="Use wireless ADB (optionally IP:PORT)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger = logging.getLogger("selfverify_connect")

    driver = _build_driver(args, logger)
    try:
        return connect_and_verify(driver)
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
