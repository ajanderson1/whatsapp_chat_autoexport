"""Tests for deprecated entry point wrappers."""

import pytest

from whatsapp_chat_autoexport.deprecated_entry import (
    DEPRECATION_MAP,
    whatsapp_drive_main,
    whatsapp_export_main,
    whatsapp_logs_main,
    whatsapp_pipeline_main,
    whatsapp_process_main,
)


@pytest.mark.parametrize(
    "func,old_cmd",
    [
        (whatsapp_export_main, "whatsapp-export"),
        (whatsapp_pipeline_main, "whatsapp-pipeline"),
        (whatsapp_process_main, "whatsapp-process"),
        (whatsapp_drive_main, "whatsapp-drive"),
        (whatsapp_logs_main, "whatsapp-logs"),
    ],
)
def test_deprecation_wrapper_exits_zero(func, old_cmd):
    with pytest.raises(SystemExit) as exc_info:
        func()
    assert exc_info.value.code == 0


@pytest.mark.parametrize(
    "func,old_cmd",
    [
        (whatsapp_export_main, "whatsapp-export"),
        (whatsapp_pipeline_main, "whatsapp-pipeline"),
        (whatsapp_process_main, "whatsapp-process"),
        (whatsapp_drive_main, "whatsapp-drive"),
        (whatsapp_logs_main, "whatsapp-logs"),
    ],
)
def test_deprecation_wrapper_prints_notice(func, old_cmd, capsys):
    with pytest.raises(SystemExit):
        func()
    captured = capsys.readouterr()
    assert old_cmd in captured.out
    assert "deprecated" in captured.out
    assert DEPRECATION_MAP[old_cmd] in captured.out


def test_all_commands_in_deprecation_map():
    expected = {"whatsapp-export", "whatsapp-pipeline", "whatsapp-process", "whatsapp-drive", "whatsapp-logs"}
    assert set(DEPRECATION_MAP.keys()) == expected
