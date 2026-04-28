"""
Tests for the unified CLI entry point (cli_entry.py).

Covers:
- Mode detection for TUI, headless, and pipeline-only
- Argument validation (missing required args, conflicting flags)
- All R7 flags are parsed correctly
- Dispatch to correct mode function
"""

import argparse
import pytest
from unittest.mock import patch, MagicMock

from whatsapp_chat_autoexport.cli_entry import (
    create_parser,
    detect_mode,
    validate_args,
    main,
    run_headless,
    run_pipeline_only,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(args_list):
    """Parse a list of CLI args and return the namespace."""
    parser = create_parser()
    return parser.parse_args(args_list)


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------

class TestDetectMode:
    """Tests for detect_mode()."""

    def test_default_is_tui(self):
        args = parse([])
        assert detect_mode(args) == "tui"

    def test_headless_mode(self):
        args = parse(["--headless", "--output", "/tmp/out"])
        assert detect_mode(args) == "headless"

    def test_pipeline_only_mode(self):
        args = parse(["--pipeline-only", "/src", "/out"])
        assert detect_mode(args) == "pipeline-only"

    def test_conflict_headless_and_pipeline_only(self):
        args = parse(["--headless", "--pipeline-only", "/src", "/out"])
        assert detect_mode(args) == "error:conflict"

    def test_tui_with_flags(self):
        args = parse(["--debug", "--limit", "5"])
        assert detect_mode(args) == "tui"


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

class TestValidateArgs:
    """Tests for validate_args()."""

    def test_headless_without_output_is_error(self):
        args = parse(["--headless"])
        mode = detect_mode(args)
        error = validate_args(args, mode)
        assert error is not None
        assert "--output" in error

    def test_headless_with_output_is_valid(self):
        args = parse(["--headless", "--output", "/tmp/out"])
        mode = detect_mode(args)
        assert validate_args(args, mode) is None

    def test_pipeline_only_without_source_is_error(self):
        args = parse(["--pipeline-only"])
        mode = detect_mode(args)
        error = validate_args(args, mode)
        assert error is not None
        assert "source" in error.lower() or "positional" in error.lower()

    def test_pipeline_only_without_output_is_error(self):
        args = parse(["--pipeline-only", "/src"])
        mode = detect_mode(args)
        error = validate_args(args, mode)
        assert error is not None
        assert "output" in error.lower() or "positional" in error.lower()

    def test_pipeline_only_with_both_args_is_valid(self):
        args = parse(["--pipeline-only", "/src", "/out"])
        mode = detect_mode(args)
        assert validate_args(args, mode) is None

    def test_conflict_is_error(self):
        args = parse(["--headless", "--pipeline-only", "/src", "/out"])
        mode = detect_mode(args)
        error = validate_args(args, mode)
        assert error is not None
        assert "Cannot" in error

    def test_tui_no_args_is_valid(self):
        args = parse([])
        mode = detect_mode(args)
        assert validate_args(args, mode) is None


# ---------------------------------------------------------------------------
# R7 flag parsing
# ---------------------------------------------------------------------------

class TestR7FlagParsing:
    """All R7 flags must be parsed and accessible on the namespace."""

    def test_limit(self):
        args = parse(["--limit", "10"])
        assert args.limit == 10

    def test_limit_default_none(self):
        args = parse([])
        assert args.limit is None

    def test_without_media(self):
        args = parse(["--without-media"])
        assert args.without_media is True

    def test_no_output_media(self):
        args = parse(["--no-output-media"])
        assert args.no_output_media is True

    def test_force_transcribe(self):
        args = parse(["--force-transcribe"])
        assert args.force_transcribe is True

    def test_no_transcribe(self):
        args = parse(["--no-transcribe"])
        assert args.no_transcribe is True

    def test_wireless_adb_no_value(self):
        args = parse(["--wireless-adb"])
        assert args.wireless_adb is True

    def test_wireless_adb_with_value(self):
        args = parse(["--wireless-adb", "192.168.1.100:5555"])
        assert args.wireless_adb == "192.168.1.100:5555"

    def test_wireless_adb_default_none(self):
        args = parse([])
        assert args.wireless_adb is None

    def test_debug(self):
        args = parse(["--debug"])
        assert args.debug is True

    def test_resume(self):
        args = parse(["--resume", "/path/to/drive"])
        assert args.resume == "/path/to/drive"

    def test_delete_from_drive(self):
        args = parse(["--delete-from-drive"])
        assert args.delete_from_drive is True

    def test_transcription_provider_default(self):
        args = parse([])
        assert args.transcription_provider == "whisper"

    def test_transcription_provider_elevenlabs(self):
        args = parse(["--transcription-provider", "elevenlabs"])
        assert args.transcription_provider == "elevenlabs"

    def test_skip_drive_download(self):
        args = parse(["--skip-drive-download"])
        assert args.skip_drive_download is True

    def test_auto_select(self):
        args = parse(["--auto-select"])
        assert args.auto_select is True

    def test_output(self):
        args = parse(["--output", "/tmp/exports"])
        assert args.output == "/tmp/exports"

    def test_all_flags_combined(self):
        args = parse([
            "--headless",
            "--output", "/tmp/out",
            "--limit", "5",
            "--without-media",
            "--no-output-media",
            "--force-transcribe",
            "--no-transcribe",
            "--wireless-adb", "192.168.1.100:5555",
            "--debug",
            "--resume", "/drive/path",
            "--delete-from-drive",
            "--transcription-provider", "elevenlabs",
            "--skip-drive-download",
            "--auto-select",
        ])
        assert args.headless is True
        assert args.output == "/tmp/out"
        assert args.limit == 5
        assert args.without_media is True
        assert args.no_output_media is True
        assert args.force_transcribe is True
        assert args.no_transcribe is True
        assert args.wireless_adb == "192.168.1.100:5555"
        assert args.debug is True
        assert args.resume == "/drive/path"
        assert args.delete_from_drive is True
        assert args.transcription_provider == "elevenlabs"
        assert args.skip_drive_download is True
        assert args.auto_select is True


# ---------------------------------------------------------------------------
# Stub mode functions
# ---------------------------------------------------------------------------

class TestModeDelegation:
    """Headless and pipeline-only delegate to their implementations."""

    @patch("whatsapp_chat_autoexport.headless.run_headless", return_value=0)
    def test_run_headless_delegates(self, mock_impl):
        args = parse(["--headless", "--output", "/tmp/out"])
        assert run_headless(args) == 0
        mock_impl.assert_called_once_with(args)

    @patch("whatsapp_chat_autoexport.headless.run_pipeline_only", return_value=0)
    def test_run_pipeline_only_delegates(self, mock_impl):
        args = parse(["--pipeline-only", "/src", "/out"])
        assert run_pipeline_only(args) == 0
        mock_impl.assert_called_once_with(args)


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------

class TestMainDispatch:
    """Tests that main() dispatches to the correct mode function."""

    @patch("whatsapp_chat_autoexport.cli_entry.run_tui", return_value=0)
    def test_main_default_dispatches_to_tui(self, mock_run_tui):
        result = main([])
        mock_run_tui.assert_called_once()
        assert result == 0

    @patch("whatsapp_chat_autoexport.cli_entry.run_headless", return_value=0)
    def test_main_headless_dispatches(self, mock_run_headless):
        result = main(["--headless", "--output", "/tmp/out"])
        mock_run_headless.assert_called_once()
        assert result == 0

    @patch("whatsapp_chat_autoexport.cli_entry.run_pipeline_only", return_value=0)
    def test_main_pipeline_only_dispatches(self, mock_run_pipeline_only):
        result = main(["--pipeline-only", "/src", "/out"])
        mock_run_pipeline_only.assert_called_once()
        assert result == 0

    def test_main_headless_without_output_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--headless"])
        assert exc_info.value.code == 2

    def test_main_pipeline_only_no_args_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--pipeline-only"])
        assert exc_info.value.code == 2

    def test_main_conflict_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--headless", "--pipeline-only", "/src", "/out"])
        assert exc_info.value.code == 2

    @patch("whatsapp_chat_autoexport.cli_entry.run_tui", return_value=0)
    def test_main_forwards_args_to_tui(self, mock_run_tui):
        main(["--limit", "5", "--debug"])
        called_args = mock_run_tui.call_args[0][0]
        assert called_args.limit == 5
        assert called_args.debug is True

    @patch("whatsapp_chat_autoexport.cli_entry.run_headless", return_value=1)
    def test_main_returns_headless_exit_code(self, mock_run_headless):
        result = main(["--headless", "--output", "/tmp/out"])
        assert result == 1


# ---------------------------------------------------------------------------
# TUI launch (with mocked Textual)
# ---------------------------------------------------------------------------

class TestRunTui:
    """Test that run_tui correctly creates and runs the Textual app."""

    @patch("whatsapp_chat_autoexport.cli_entry.WhatsAppExporterApp", create=True)
    def test_run_tui_creates_app_with_defaults(self, MockApp):
        """Patch at the point of import inside run_tui."""
        mock_instance = MagicMock()
        MockApp.return_value = mock_instance

        # We need to patch the import inside run_tui
        with patch.dict("sys.modules", {}):
            # Directly patch the import path used by run_tui
            with patch(
                "whatsapp_chat_autoexport.tui.textual_app.WhatsAppExporterApp",
                MockApp,
            ):
                from whatsapp_chat_autoexport.cli_entry import run_tui

                args = parse([])
                result = run_tui(args)

                MockApp.assert_called_once()
                call_kwargs = MockApp.call_args[1]
                assert call_kwargs["output_dir"] is None
                assert call_kwargs["include_media"] is True
                assert call_kwargs["transcribe_audio"] is True
                assert call_kwargs["debug"] is False
                assert call_kwargs["limit"] is None
                mock_instance.run.assert_called_once()
                assert result == 0

    @patch(
        "whatsapp_chat_autoexport.tui.textual_app.WhatsAppExporterApp",
    )
    def test_run_tui_passes_flags(self, MockApp):
        mock_instance = MagicMock()
        MockApp.return_value = mock_instance

        from whatsapp_chat_autoexport.cli_entry import run_tui

        args = parse([
            "--output", "/tmp/exports",
            "--no-output-media",
            "--no-transcribe",
            "--delete-from-drive",
            "--transcription-provider", "elevenlabs",
            "--limit", "10",
            "--debug",
        ])
        run_tui(args)

        call_kwargs = MockApp.call_args[1]
        assert call_kwargs["include_media"] is False
        assert call_kwargs["transcribe_audio"] is False
        assert call_kwargs["delete_from_drive"] is True
        assert call_kwargs["transcription_provider"] == "elevenlabs"
        assert call_kwargs["limit"] == 10
        assert call_kwargs["debug"] is True


class TestKeepDriveDuplicatesFlag:
    """Tests for the --keep-drive-duplicates CLI flag."""

    def test_flag_defaults_to_not_keeping_duplicates(self):
        """Without the flag, args.keep_drive_duplicates is False (cleanup enabled)."""
        args = parse([])
        assert getattr(args, "keep_drive_duplicates", None) is False

    def test_flag_sets_keep_to_true(self):
        """--keep-drive-duplicates sets args.keep_drive_duplicates=True."""
        args = parse(["--keep-drive-duplicates"])
        assert args.keep_drive_duplicates is True


class TestSkipPreflightFlag:
    """Tests for the --skip-preflight CLI flag."""

    def test_skip_preflight_default_false(self):
        from whatsapp_chat_autoexport.cli_entry import create_parser

        parser = create_parser()
        args = parser.parse_args(["--headless", "--output", "/tmp/out", "--auto-select"])
        assert args.skip_preflight is False

    def test_skip_preflight_set_true(self):
        from whatsapp_chat_autoexport.cli_entry import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["--headless", "--output", "/tmp/out", "--auto-select", "--skip-preflight"]
        )
        assert args.skip_preflight is True

