"""Tests for the headless mode orchestrator (whatsapp_chat_autoexport.headless.run_headless)."""

import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from whatsapp_chat_autoexport.export.models import ChatMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(**overrides) -> Namespace:
    """Build a minimal args Namespace for headless mode."""
    defaults = {
        "output": "/tmp/test_output",
        "debug": False,
        "no_transcribe": True,       # skip transcription by default in tests
        "force_transcribe": False,
        "transcription_provider": "whisper",
        "transcription_language": None,
        "auto_select": True,
        "resume": None,
        "limit": None,
        "without_media": False,
        "no_output_media": False,
        "delete_from_drive": False,
        "skip_appium": False,
        "wireless_adb": None,
        "google_drive_folder": None,
        "poll_interval": 8,
        "poll_timeout": 300,
        "skip_opus_conversion": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


# Patch the *source* modules, since run_headless does lazy local imports.
_APPIUM = "whatsapp_chat_autoexport.export.appium_manager.AppiumManager"
_DRIVER = "whatsapp_chat_autoexport.export.whatsapp_driver.WhatsAppDriver"
_EXPORTER = "whatsapp_chat_autoexport.export.chat_exporter.ChatExporter"
_VALIDATE_RESUME = "whatsapp_chat_autoexport.export.chat_exporter.validate_resume_directory"
_PIPELINE = "whatsapp_chat_autoexport.headless.WhatsAppPipeline"
_VALIDATE_API = "whatsapp_chat_autoexport.headless._validate_api_key"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """All steps succeed — exit code 0."""

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_full_success_returns_0(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        # Appium
        appium = MockAppium.return_value
        appium.start_appium.return_value = True

        # Driver
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A"), ChatMetadata(name="Chat B")]

        # Exporter — all succeed
        exporter = MockExporter.return_value
        exporter.export_chats.return_value = (
            {"Chat A": True, "Chat B": True},  # results
            {"Chat A": 5.0, "Chat B": 3.0},    # timings
            8.0,                                 # total_time
            {},                                  # skipped
        )

        args = _make_args()
        code = run_headless(args)

        assert code == 0
        appium.start_appium.assert_called_once()
        driver.check_device_connection.assert_called_once()
        driver.connect.assert_called_once()
        driver.collect_all_chats.assert_called_once()
        exporter.export_chats.assert_called_once()

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_cleanup_called_on_success(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        appium = MockAppium.return_value
        appium.start_appium.return_value = True

        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A")]

        exporter = MockExporter.return_value
        exporter.export_chats.return_value = ({"Chat A": True}, {"Chat A": 1.0}, 1.0, {})

        run_headless(_make_args())

        driver.quit.assert_called_once()
        appium.stop_appium.assert_called_once()


# ---------------------------------------------------------------------------
# Partial failure
# ---------------------------------------------------------------------------

class TestPartialFailure:
    """Some exports fail — exit code 1."""

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_partial_failure_returns_1(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        appium = MockAppium.return_value
        appium.start_appium.return_value = True

        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A"), ChatMetadata(name="Chat B")]

        exporter = MockExporter.return_value
        exporter.export_chats.return_value = (
            {"Chat A": True, "Chat B": False},
            {"Chat A": 5.0, "Chat B": 0.5},
            5.5,
            {},
        )

        code = run_headless(_make_args())
        assert code == 1


# ---------------------------------------------------------------------------
# Fatal errors — exit code 2
# ---------------------------------------------------------------------------

class TestFatalErrors:
    """Various fatal error conditions that should exit with code 2."""

    def test_no_auto_select_or_resume_returns_2(self):
        from whatsapp_chat_autoexport.headless import run_headless

        args = _make_args(auto_select=False, resume=None)
        code = run_headless(args)
        assert code == 2

    @patch(_APPIUM)
    def test_appium_failure_returns_2(self, MockAppium):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = False

        code = run_headless(_make_args())
        assert code == 2

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_no_device_returns_2(self, MockAppium, MockDriver):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        MockDriver.return_value.check_device_connection.return_value = False

        code = run_headless(_make_args())
        assert code == 2

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_whatsapp_connect_failure_returns_2(self, MockAppium, MockDriver):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = False

        code = run_headless(_make_args())
        assert code == 2

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_navigate_failure_returns_2(self, MockAppium, MockDriver):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = False

        code = run_headless(_make_args())
        assert code == 2

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_no_chats_found_returns_2(self, MockAppium, MockDriver):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = []

        code = run_headless(_make_args())
        assert code == 2

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_all_chats_fail_returns_2(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A")]

        MockExporter.return_value.export_chats.return_value = (
            {"Chat A": False}, {"Chat A": 0.5}, 0.5, {},
        )

        code = run_headless(_make_args())
        assert code == 2


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

class TestApiKeyValidation:

    @patch(_VALIDATE_API)
    def test_api_key_failure_with_transcription_returns_2(self, mock_validate):
        from whatsapp_chat_autoexport.headless import run_headless

        mock_validate.return_value = False
        args = _make_args(no_transcribe=False)
        code = run_headless(args)
        assert code == 2

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_no_transcribe_skips_api_validation(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        """When --no-transcribe is set, API key is not checked."""
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A")]
        MockExporter.return_value.export_chats.return_value = (
            {"Chat A": True}, {"Chat A": 1.0}, 1.0, {},
        )

        # No API key set — should still succeed because transcription is off
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            code = run_headless(_make_args(no_transcribe=True))

        assert code == 0


# ---------------------------------------------------------------------------
# Cleanup on failure
# ---------------------------------------------------------------------------

class TestCleanup:

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_cleanup_on_exception(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.side_effect = RuntimeError("boom")

        code = run_headless(_make_args())

        assert code == 2
        driver.quit.assert_called_once()
        MockAppium.return_value.stop_appium.assert_called_once()

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_cleanup_when_driver_quit_raises(self, MockAppium, MockDriver):
        """Cleanup must not propagate exceptions from driver.quit()."""
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = False
        driver.quit.side_effect = RuntimeError("quit failed")

        code = run_headless(_make_args())
        assert code == 2
        # Should not raise — the RuntimeError from quit is swallowed


# ---------------------------------------------------------------------------
# Skip-appium flag
# ---------------------------------------------------------------------------

class TestSkipAppium:

    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_skip_appium_does_not_start(self, MockAppium, MockDriver):
        from whatsapp_chat_autoexport.headless import run_headless

        driver = MockDriver.return_value
        driver.check_device_connection.return_value = False  # fail fast

        run_headless(_make_args(skip_appium=True))

        MockAppium.return_value.start_appium.assert_not_called()


# ---------------------------------------------------------------------------
# Resume mode
# ---------------------------------------------------------------------------

class TestResumeMode:

    @patch(_VALIDATE_RESUME, return_value=None)
    def test_invalid_resume_dir_returns_2(self, mock_validate):
        from whatsapp_chat_autoexport.headless import run_headless

        args = _make_args(auto_select=False, resume="/bad/path")
        code = run_headless(args)
        assert code == 2

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    @patch(_VALIDATE_RESUME)
    def test_resume_folder_passed_to_exporter(
        self, mock_validate, MockAppium, MockDriver, MockExporter, MockPipeline,
    ):
        from whatsapp_chat_autoexport.headless import run_headless

        resume_dir = Path("/valid/resume")
        mock_validate.return_value = resume_dir

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A")]

        MockExporter.return_value.export_chats.return_value = (
            {"Chat A": True}, {"Chat A": 1.0}, 1.0, {},
        )

        code = run_headless(_make_args(auto_select=False, resume="/valid/resume"))
        assert code == 0

        # Verify resume_folder was passed through
        call_kwargs = MockExporter.return_value.export_chats.call_args
        assert call_kwargs[1]["resume_folder"] == resume_dir


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------

class TestProgressCallback:

    def test_log_progress_to_stderr(self, capsys):
        from whatsapp_chat_autoexport.headless import _log_progress

        _log_progress("download", "Downloading", 1, 5, "file.zip")
        captured = capsys.readouterr()
        assert "[download]" in captured.err
        assert "(1/5)" in captured.err
        assert "file.zip" in captured.err

    def test_log_progress_without_item(self, capsys):
        from whatsapp_chat_autoexport.headless import _log_progress

        _log_progress("extract", "Extracting", 0, 1)
        captured = capsys.readouterr()
        assert "[extract]" in captured.err
        assert "Extracting" in captured.err


# ---------------------------------------------------------------------------
# Pipeline config wiring
# ---------------------------------------------------------------------------

class TestPipelineConfigWiring:

    @patch(_PIPELINE)
    @patch(_EXPORTER)
    @patch(_DRIVER)
    @patch(_APPIUM)
    def test_pipeline_receives_correct_config(self, MockAppium, MockDriver, MockExporter, MockPipeline):
        from whatsapp_chat_autoexport.headless import run_headless

        MockAppium.return_value.start_appium.return_value = True
        driver = MockDriver.return_value
        driver.check_device_connection.return_value = True
        driver.connect.return_value = True
        driver.navigate_to_main.return_value = True
        driver.collect_all_chats.return_value = [ChatMetadata(name="Chat A")]
        MockExporter.return_value.export_chats.return_value = (
            {"Chat A": True}, {"Chat A": 1.0}, 1.0, {},
        )

        args = _make_args(
            no_output_media=True,
            delete_from_drive=True,
            force_transcribe=True,
            no_transcribe=False,
        )

        # Patch _validate_api_key so we don't need a real key
        with patch(_VALIDATE_API, return_value=True):
            run_headless(args)

        # Check PipelineConfig passed to WhatsAppPipeline
        config = MockPipeline.call_args[0][0]
        assert config.include_media is False
        assert config.delete_from_drive is True
        assert config.skip_existing_transcriptions is False  # force_transcribe=True
        assert config.transcribe_audio_video is True
