"""Deprecation wrappers for old entry points.

Each function prints a migration notice and exits.
"""

import sys

DEPRECATION_MAP = {
    "whatsapp-export": "whatsapp --headless --output DIR",
    "whatsapp-pipeline": "whatsapp --pipeline-only SOURCE OUTPUT",
    "whatsapp-process": "whatsapp --pipeline-only SOURCE OUTPUT",
    "whatsapp-drive": "whatsapp --headless --output DIR",
    "whatsapp-logs": "whatsapp --debug",
}


def _deprecation_notice(old_command: str) -> None:
    new_command = DEPRECATION_MAP[old_command]
    print(
        f"\n\u26a0\ufe0f  '{old_command}' is deprecated.\n"
        f"\n"
        f"  Use instead:  {new_command}\n"
        f"\n"
        f"  Run 'whatsapp --help' for all available options.\n"
    )
    sys.exit(0)


def whatsapp_export_main() -> None:
    _deprecation_notice("whatsapp-export")


def whatsapp_pipeline_main() -> None:
    _deprecation_notice("whatsapp-pipeline")


def whatsapp_process_main() -> None:
    _deprecation_notice("whatsapp-process")


def whatsapp_drive_main() -> None:
    _deprecation_notice("whatsapp-drive")


def whatsapp_logs_main() -> None:
    _deprecation_notice("whatsapp-logs")
