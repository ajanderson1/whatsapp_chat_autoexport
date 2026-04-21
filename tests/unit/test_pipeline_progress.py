"""
Tests for pipeline progress callback hooks.

Verifies that the WhatsAppPipeline fires on_progress callbacks at each phase
boundary and that callback errors do not crash the pipeline.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig


class TestPipelineProgressCallbacks:
    """Tests for pipeline on_progress callback integration."""

    def _make_pipeline(self, on_progress=None, **config_overrides):
        """Create a pipeline with sensible test defaults."""
        defaults = dict(
            skip_download=True,
            transcribe_audio_video=False,
            cleanup_temp=False,
            dry_run=True,
            output_dir=Path("/tmp/test_output"),
        )
        defaults.update(config_overrides)
        config = PipelineConfig(**defaults)
        return WhatsAppPipeline(config=config, on_progress=on_progress)

    # ------------------------------------------------------------------
    # _fire_progress helper
    # ------------------------------------------------------------------

    def test_fire_progress_calls_callback(self):
        """_fire_progress invokes the callback with correct arguments."""
        cb = MagicMock()
        pipeline = self._make_pipeline(on_progress=cb)

        pipeline._fire_progress("download", "test message", 1, 5, "item")

        cb.assert_called_once_with("download", "test message", 1, 5, "item")

    def test_fire_progress_no_callback(self):
        """_fire_progress is a no-op when on_progress is None."""
        pipeline = self._make_pipeline(on_progress=None)
        # Should not raise
        pipeline._fire_progress("download", "test", 0, 1)

    def test_fire_progress_swallows_callback_exception(self):
        """_fire_progress catches exceptions raised by the callback."""
        cb = MagicMock(side_effect=RuntimeError("boom"))
        pipeline = self._make_pipeline(on_progress=cb)

        # Should not raise
        pipeline._fire_progress("download", "test", 0, 1)
        cb.assert_called_once()

    # ------------------------------------------------------------------
    # run() method - dry_run mode fires phase events
    # ------------------------------------------------------------------

    def test_run_dry_run_fires_phase_events(self, tmp_path):
        """run() in dry_run mode fires progress events for extract, build_output phases."""
        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, message, current, total))

        pipeline = self._make_pipeline(
            on_progress=recorder,
            dry_run=True,
            skip_download=True,
            output_dir=tmp_path / "output",
        )

        # dry_run returns early with empty transcript_files, but still fires extract events
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        pipeline.run(source_dir=source_dir)

        phases_seen = {e[0] for e in events}
        assert "extract" in phases_seen

    def test_run_without_callback_succeeds(self, tmp_path):
        """run() without callback behaves identically (no crash)."""
        pipeline = self._make_pipeline(on_progress=None, dry_run=True)
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        result = pipeline.run(source_dir=source_dir)
        # Should complete without error
        assert isinstance(result, dict)

    def test_run_callback_error_does_not_crash(self, tmp_path):
        """Callback exceptions do not crash the pipeline run."""
        def bad_callback(phase, message, current, total, item_name=""):
            raise ValueError("callback error")

        pipeline = self._make_pipeline(on_progress=bad_callback, dry_run=True)
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        result = pipeline.run(source_dir=source_dir)
        assert isinstance(result, dict)

    # ------------------------------------------------------------------
    # process_single_export() fires phase events
    # ------------------------------------------------------------------

    def test_process_single_export_fires_events(self, tmp_path):
        """process_single_export fires progress events for each phase."""
        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, message, current, total, item_name))

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
        )
        pipeline = WhatsAppPipeline(config=config, on_progress=recorder)

        # Mock Google Drive to avoid real network calls
        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "123", "name": "WhatsApp Chat with Test"}

        # Create a fake downloaded file
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]

        # Patch GoogleDriveManager constructor — process_single_export creates it at line 157
        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                result = pipeline.process_single_export("Test")

        # Should have download start/end events
        download_events = [e for e in events if e[0] == "download"]
        assert len(download_events) >= 1
        # item_name should be the chat name
        assert any("Test" in str(e[4]) for e in download_events)


class TestDriveManagerProgressCallbacks:
    """Tests for GoogleDriveManager.batch_download_exports on_progress."""

    def test_batch_download_fires_progress(self):
        """batch_download_exports calls on_progress for each file."""
        from whatsapp_chat_autoexport.google_drive.drive_manager import GoogleDriveManager

        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, message, current, total, item_name))

        with patch.object(GoogleDriveManager, '__init__', lambda self, **kw: None):
            mgr = GoogleDriveManager.__new__(GoogleDriveManager)
            mgr.logger = MagicMock()

            # Mock download_export to succeed
            mgr.download_export = MagicMock(return_value=(True, Path("/tmp/file.zip")))

            files = [
                {"id": "1", "name": "file1.zip"},
                {"id": "2", "name": "file2.zip"},
            ]

            result = mgr.batch_download_exports(
                files, Path("/tmp/dest"), on_progress=recorder
            )

        assert len(result) == 2
        assert len(events) == 2
        assert events[0] == ("download", "Downloaded file1.zip", 1, 2, "file1.zip")
        assert events[1] == ("download", "Downloaded file2.zip", 2, 2, "file2.zip")

    def test_batch_download_callback_error_does_not_crash(self):
        """Callback errors in batch_download_exports do not crash downloads."""
        from whatsapp_chat_autoexport.google_drive.drive_manager import GoogleDriveManager

        def bad_callback(phase, message, current, total, item_name=""):
            raise RuntimeError("boom")

        with patch.object(GoogleDriveManager, '__init__', lambda self, **kw: None):
            mgr = GoogleDriveManager.__new__(GoogleDriveManager)
            mgr.logger = MagicMock()
            mgr.download_export = MagicMock(return_value=(True, Path("/tmp/f.zip")))

            files = [{"id": "1", "name": "f.zip"}]
            result = mgr.batch_download_exports(
                files, Path("/tmp/dest"), on_progress=bad_callback
            )

        assert len(result) == 1  # Download still succeeded


class TestTranscriptionManagerProgressCallbacks:
    """Tests for TranscriptionManager.batch_transcribe on_progress."""

    def test_batch_transcribe_fires_progress(self, tmp_path):
        """batch_transcribe calls on_progress for each file."""
        from whatsapp_chat_autoexport.transcription.transcription_manager import TranscriptionManager

        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, current, total, item_name))

        mock_transcriber = MagicMock()
        mock_transcriber.is_available.return_value = True
        mock_transcriber.get_supported_formats.return_value = [".opus"]

        mgr = TranscriptionManager(mock_transcriber, logger=MagicMock())

        # Mock transcribe_file to succeed
        mgr.transcribe_file = MagicMock(return_value=(True, tmp_path / "t.txt", None))
        mgr.is_transcribed = MagicMock(return_value=(False, None))

        file1 = tmp_path / "audio1.opus"
        file2 = tmp_path / "audio2.opus"
        file1.touch()
        file2.touch()

        results = mgr.batch_transcribe([file1, file2], on_progress=recorder)

        assert len(events) == 2
        assert events[0] == ("transcribe", 1, 2, "audio1.opus")
        assert events[1] == ("transcribe", 2, 2, "audio2.opus")

    def test_batch_transcribe_callback_error_does_not_crash(self, tmp_path):
        """Callback errors in batch_transcribe do not crash transcription."""
        from whatsapp_chat_autoexport.transcription.transcription_manager import TranscriptionManager

        mock_transcriber = MagicMock()
        mock_transcriber.is_available.return_value = True

        mgr = TranscriptionManager(mock_transcriber, logger=MagicMock())
        mgr.transcribe_file = MagicMock(return_value=(True, tmp_path / "t.txt", None))
        mgr.is_transcribed = MagicMock(return_value=(False, None))

        file1 = tmp_path / "audio1.opus"
        file1.touch()

        def bad_cb(*args, **kwargs):
            raise RuntimeError("boom")

        results = mgr.batch_transcribe([file1], on_progress=bad_cb)
        assert results['total'] == 1
        assert results['successful'] == 1


class TestOutputBuilderProgressCallbacks:
    """Tests for OutputBuilder.batch_build_outputs on_progress."""

    def test_batch_build_outputs_fires_progress(self, tmp_path):
        """batch_build_outputs calls on_progress for each chat."""
        from whatsapp_chat_autoexport.output.output_builder import OutputBuilder

        events = []

        def recorder(phase, message, current, total, item_name=""):
            events.append((phase, current, total, item_name))

        builder = OutputBuilder(logger=MagicMock())

        # Mock build_output to succeed
        builder.build_output = MagicMock(return_value={
            'contact_name': 'Test',
            'output_dir': tmp_path / 'Test',
            'transcript_path': tmp_path / 'transcript.txt',
            'total_messages': 10,
            'media_messages': 2,
            'media_copied': 2,
            'transcriptions_copied': 1,
        })

        transcript_files = [
            (tmp_path / "chat1.txt", tmp_path / "media1"),
            (tmp_path / "chat2.txt", tmp_path / "media2"),
        ]

        results = builder.batch_build_outputs(
            transcript_files, tmp_path / "output", on_progress=recorder
        )

        assert len(results) == 2
        assert len(events) == 2
        assert events[0] == ("build_output", 1, 2, "chat1")
        assert events[1] == ("build_output", 2, 2, "chat2")

    def test_batch_build_outputs_callback_error_does_not_crash(self, tmp_path):
        """Callback errors in batch_build_outputs do not crash output building."""
        from whatsapp_chat_autoexport.output.output_builder import OutputBuilder

        builder = OutputBuilder(logger=MagicMock())
        builder.build_output = MagicMock(return_value={
            'contact_name': 'Test',
            'output_dir': tmp_path / 'Test',
            'transcript_path': tmp_path / 'transcript.txt',
            'total_messages': 10,
            'media_messages': 0,
            'media_copied': 0,
            'transcriptions_copied': 0,
        })

        def bad_cb(*args, **kwargs):
            raise RuntimeError("boom")

        transcript_files = [(tmp_path / "chat.txt", tmp_path / "media")]
        results = builder.batch_build_outputs(
            transcript_files, tmp_path / "output", on_progress=bad_cb
        )
        assert len(results) == 1


class TestCleanupDuplicatesConfig:
    """Tests for the cleanup_drive_duplicates config flag on PipelineConfig."""

    def test_pipeline_config_default_is_true(self):
        """PipelineConfig.cleanup_drive_duplicates defaults to True."""
        from whatsapp_chat_autoexport.pipeline import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.cleanup_drive_duplicates is True

    def test_pipeline_config_can_be_disabled(self):
        """PipelineConfig accepts cleanup_drive_duplicates=False."""
        from whatsapp_chat_autoexport.pipeline import PipelineConfig
        cfg = PipelineConfig(cleanup_drive_duplicates=False)
        assert cfg.cleanup_drive_duplicates is False

    def test_pipeline_calls_cleanup_after_successful_download(self, tmp_path):
        """When cleanup_drive_duplicates=True, process_single_export calls
        drive_manager.delete_sibling_exports(chat_name) after a successful download."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=True,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                pipeline.process_single_export("Test")

        mock_drive.delete_sibling_exports.assert_called_once_with("Test")

    def test_pipeline_skips_cleanup_when_flag_off(self, tmp_path):
        """When cleanup_drive_duplicates=False, cleanup is not called."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=False,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                pipeline.process_single_export("Test")

        mock_drive.delete_sibling_exports.assert_not_called()


class TestCleanupFailureDoesNotFailChat:
    def test_cleanup_raising_does_not_abort_pipeline(self, tmp_path):
        """Defensive: even if delete_sibling_exports raises (it shouldn't), the
        chat's pipeline run continues. We guard with try/except in the call site."""
        from unittest.mock import patch, MagicMock
        from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline

        config = PipelineConfig(
            skip_download=False,
            transcribe_audio_video=False,
            cleanup_temp=False,
            output_dir=tmp_path / "output",
            cleanup_drive_duplicates=True,
        )
        pipeline = WhatsAppPipeline(config=config)

        mock_drive = MagicMock()
        mock_drive.connect.return_value = True
        mock_drive.wait_for_new_export.return_value = {"id": "abc", "name": "WhatsApp Chat with Test"}
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        fake_zip = download_dir / "WhatsApp Chat with Test"
        fake_zip.write_text("fake")
        mock_drive.batch_download_exports.return_value = [fake_zip]
        mock_drive.delete_sibling_exports.side_effect = RuntimeError("boom")

        with patch('whatsapp_chat_autoexport.pipeline.GoogleDriveManager', return_value=mock_drive):
            with patch.object(pipeline, '_phase2_extract_and_organize', return_value=[]):
                # Should NOT raise — the RuntimeError from cleanup must be caught.
                result = pipeline.process_single_export("Test")

        # Phase 1 (download) should be marked completed even though cleanup raised.
        assert result is not None
        # Depending on _phase2 mocks this may or may not be "success", but the
        # run did not propagate the cleanup exception.
