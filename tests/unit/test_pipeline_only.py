"""Tests for pipeline-only mode (headless.run_pipeline_only)."""

import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _make_args(source="/tmp/src", output="/tmp/out", **overrides):
    """Build a minimal argparse Namespace for run_pipeline_only."""
    defaults = dict(
        source=source,
        pipeline_output=output,
        no_transcribe=False,
        force_transcribe=False,
        transcription_provider="whisper",
        no_output_media=False,
        delete_from_drive=False,
        skip_drive_download=False,
        limit=None,
        debug=False,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=True)
def test_happy_path_returns_zero(mock_validate, mock_pipeline_cls, tmp_path):
    """Successful pipeline run returns exit code 0."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "output"

    mock_instance = MagicMock()
    mock_instance.run.return_value = {"success": True, "errors": []}
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(source=str(source), output=str(output))
    code = run_pipeline_only(args)

    assert code == 0
    mock_pipeline_cls.assert_called_once()
    mock_instance.run.assert_called_once_with(source_dir=source)


# ---------------------------------------------------------------------------
# No-transcribe path
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
def test_no_transcribe_skips_api_validation(mock_pipeline_cls, tmp_path):
    """With --no-transcribe, API key validation is skipped entirely."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()

    mock_instance = MagicMock()
    mock_instance.run.return_value = {"success": True, "errors": []}
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(source=str(source), output=str(tmp_path / "out"), no_transcribe=True)

    with patch("whatsapp_chat_autoexport.headless._validate_api_key") as mock_val:
        code = run_pipeline_only(args)
        mock_val.assert_not_called()

    assert code == 0

    # Verify PipelineConfig has transcribe disabled
    config = mock_pipeline_cls.call_args[0][0]
    assert config.transcribe_audio_video is False


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=False)
def test_missing_api_key_returns_two(mock_validate, tmp_path):
    """Missing API key with transcription enabled returns exit code 2."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()

    args = _make_args(source=str(source), output=str(tmp_path / "out"))
    code = run_pipeline_only(args)

    assert code == 2
    mock_validate.assert_called_once()


# ---------------------------------------------------------------------------
# Invalid source path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_invalid_source_returns_two(tmp_path):
    """Non-existent source directory returns exit code 2."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    args = _make_args(
        source=str(tmp_path / "does_not_exist"),
        output=str(tmp_path / "out"),
    )
    code = run_pipeline_only(args)

    assert code == 2


# ---------------------------------------------------------------------------
# Pipeline error
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=True)
def test_pipeline_failure_returns_one(mock_validate, mock_pipeline_cls, tmp_path):
    """Pipeline returning success=False yields exit code 1."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()

    mock_instance = MagicMock()
    mock_instance.run.return_value = {"success": False, "errors": ["something went wrong"]}
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(source=str(source), output=str(tmp_path / "out"))
    code = run_pipeline_only(args)

    assert code == 1


# ---------------------------------------------------------------------------
# Fatal exception
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=True)
def test_fatal_exception_returns_two(mock_validate, mock_pipeline_cls, tmp_path):
    """Unhandled exception in pipeline.run() returns exit code 2."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()

    mock_instance = MagicMock()
    mock_instance.run.side_effect = RuntimeError("boom")
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(source=str(source), output=str(tmp_path / "out"))
    code = run_pipeline_only(args)

    assert code == 2


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=True)
def test_config_wiring(mock_validate, mock_pipeline_cls, tmp_path):
    """Verify args are correctly mapped to PipelineConfig fields."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only

    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "out"

    mock_instance = MagicMock()
    mock_instance.run.return_value = {"success": True, "errors": []}
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(
        source=str(source),
        output=str(output),
        no_output_media=True,
        force_transcribe=True,
        transcription_provider="elevenlabs",
        limit=5,
        delete_from_drive=True,
    )
    run_pipeline_only(args)

    config = mock_pipeline_cls.call_args[0][0]
    assert config.skip_download is True
    assert config.output_dir == output
    assert config.include_media is False
    assert config.transcribe_audio_video is True
    assert config.skip_existing_transcriptions is False  # force_transcribe inverts this
    assert config.transcription_provider == "elevenlabs"
    assert config.limit == 5
    assert config.delete_from_drive is True


# ---------------------------------------------------------------------------
# Progress callback is wired
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.WhatsAppPipeline")
@patch("whatsapp_chat_autoexport.headless._validate_api_key", return_value=True)
def test_progress_callback_wired(mock_validate, mock_pipeline_cls, tmp_path):
    """Pipeline is constructed with a progress callback."""
    from whatsapp_chat_autoexport.headless import run_pipeline_only, _log_progress

    source = tmp_path / "source"
    source.mkdir()

    mock_instance = MagicMock()
    mock_instance.run.return_value = {"success": True, "errors": []}
    mock_pipeline_cls.return_value = mock_instance

    args = _make_args(source=str(source), output=str(tmp_path / "out"))
    run_pipeline_only(args)

    # on_progress kwarg should be _log_progress
    call_kwargs = mock_pipeline_cls.call_args[1]
    assert call_kwargs["on_progress"] is _log_progress


# ---------------------------------------------------------------------------
# CLI integration: cli_entry dispatches to headless.run_pipeline_only
# ---------------------------------------------------------------------------

@pytest.mark.unit
@patch("whatsapp_chat_autoexport.headless.run_pipeline_only", return_value=0)
def test_cli_entry_dispatches(mock_run, tmp_path):
    """cli_entry.main dispatches --pipeline-only to headless.run_pipeline_only."""
    from whatsapp_chat_autoexport.cli_entry import main

    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "out"

    code = main(["--pipeline-only", str(source), str(output)])
    assert code == 0
    mock_run.assert_called_once()
