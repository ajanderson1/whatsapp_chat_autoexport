"""
Headless and pipeline-only execution modes.

No Textual imports — this module handles non-interactive CLI modes:
- run_headless():      Full export + pipeline (device required)
- run_pipeline_only(): Pipeline processing on existing local files

Exit codes:
    0 — all chats exported/processed successfully
    1 — partial failure (some chats failed)
    2 — fatal error (no useful work completed)
"""

import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional

from .pipeline import WhatsAppPipeline, PipelineConfig
from .utils.logger import Logger


# ---------------------------------------------------------------------------
# Progress callback
# ---------------------------------------------------------------------------

def _log_progress(phase: str, message: str, current: int, total: int,
                  item_name: str = "") -> None:
    """Simple stderr progress callback for non-interactive modes."""
    prefix = f"[{phase}]"
    if total > 0:
        prefix += f" ({current}/{total})"
    if item_name:
        print(f"{prefix} {item_name}: {message}", file=sys.stderr)
    else:
        print(f"{prefix} {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# API-key validation (mirrors export/cli.py logic)
# ---------------------------------------------------------------------------

def _validate_api_key(provider: str, logger: Logger) -> bool:
    """
    Validate that the required API key is set for the given transcription provider.

    Returns True if valid, False otherwise.
    """
    env_var_map = {
        "whisper": "OPENAI_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
    }
    required_env_var = env_var_map.get(provider.lower(), "OPENAI_API_KEY")
    api_key = os.environ.get(required_env_var)

    if not api_key:
        logger.error(
            f"{required_env_var} is not set. "
            f"Set it with: export {required_env_var}='your-key-here'"
        )
        return False

    # Validate via factory
    from .transcription.transcriber_factory import TranscriberFactory

    success, error_msg = TranscriberFactory.validate_provider(provider)
    if not success:
        logger.error(f"API key validation failed: {error_msg}")
        return False

    logger.success(f"{provider} API key validated")
    return True


# ---------------------------------------------------------------------------
# Headless mode: full export + pipeline
# ---------------------------------------------------------------------------

def run_headless(args: Namespace) -> int:
    """Run full export + pipeline in headless (non-interactive) mode.

    Mirrors the orchestration flow of ``export/cli.py`` but without
    interactive prompts or TUI.  Chat selection is driven by
    ``--auto-select`` (all chats) or ``--resume PATH`` (skip existing).

    Args:
        args: Parsed argparse Namespace from ``cli_entry.py``.

    Returns:
        Exit code: 0 = success, 1 = partial failure, 2 = fatal error.
    """
    # Lazy imports — keep Appium/Selenium out of module-level scope so that
    # pipeline-only mode (which shares this file) never needs them installed.
    from .export.appium_manager import AppiumManager
    from .export.chat_exporter import ChatExporter, validate_resume_directory
    from .export.whatsapp_driver import WhatsAppDriver

    logger = Logger(debug=getattr(args, "debug", False))

    logger.info("=" * 70)
    logger.info("WhatsApp Chat Auto-Export — Headless Mode")
    logger.info("=" * 70)

    output_dir = Path(args.output).expanduser()

    # --- API-key validation -----------------------------------------------
    no_transcribe = getattr(args, "no_transcribe", False)
    if not no_transcribe:
        provider = getattr(args, "transcription_provider", "whisper")
        if not _validate_api_key(provider, logger):
            logger.error(
                "Cannot proceed without a valid API key for transcription. "
                "Set the key or use --no-transcribe to skip."
            )
            logger.close()
            return 2

    # --- Chat selection strategy ------------------------------------------
    auto_select = getattr(args, "auto_select", False)
    resume_path: Optional[str] = getattr(args, "resume", None)

    if not auto_select and not resume_path:
        logger.error(
            "Headless mode requires either --auto-select (export all chats) "
            "or --resume PATH (skip already-exported chats)."
        )
        logger.error("Example: whatsapp --headless --output DIR --auto-select")
        logger.close()
        return 2

    # --- Resume validation ------------------------------------------------
    resume_folder: Optional[Path] = None
    if resume_path:
        resume_folder = validate_resume_directory(resume_path, logger)
        if resume_folder is None:
            logger.error("Invalid resume directory. Exiting.")
            logger.close()
            return 2

    appium_manager: Optional[AppiumManager] = None
    driver: Optional[WhatsAppDriver] = None

    try:
        # Step 1: Appium ---------------------------------------------------
        skip_appium = getattr(args, "skip_appium", False)
        if not skip_appium:
            logger.step(1, "Starting Appium server...")
            appium_manager = AppiumManager(logger)
            if not appium_manager.start_appium():
                logger.error("Failed to start Appium. Is it installed?")
                return 2
        else:
            logger.info("Skipping Appium startup (--skip-appium)")

        # Step 2: Device connection ----------------------------------------
        logger.step(2, "Connecting to device...")
        wireless_adb = getattr(args, "wireless_adb", None)
        driver = WhatsAppDriver(logger, wireless_adb=wireless_adb)

        if not driver.check_device_connection():
            logger.error(
                "No Android device found. Connect via USB or "
                "use --wireless-adb IP:PORT."
            )
            return 2

        # Step 3: WhatsApp -------------------------------------------------
        logger.step(3, "Connecting to WhatsApp...")
        if not driver.connect():
            logger.error("Failed to connect to WhatsApp. Is the app open and unlocked?")
            return 2

        # Step 4: Navigate -------------------------------------------------
        logger.step(4, "Navigating to main chats screen...")
        if not driver.navigate_to_main():
            logger.error("Failed to navigate to WhatsApp main screen.")
            return 2

        # Step 5: Collect chats --------------------------------------------
        logger.step(5, "Collecting chat list...")
        limit = getattr(args, "limit", None)
        all_chats = driver.collect_all_chats(limit=limit, sort_alphabetical=False)

        if not all_chats:
            logger.error("No chats found on device.")
            return 2

        logger.info(f"Found {len(all_chats)} chat(s)")

        # Step 6: Pipeline config ------------------------------------------
        logger.step(6, "Configuring pipeline...")

        pipeline_config = PipelineConfig(
            google_drive_folder=getattr(args, "google_drive_folder", None),
            delete_from_drive=getattr(args, "delete_from_drive", False),
            skip_download=False,
            poll_interval=getattr(args, "poll_interval", 8),
            poll_timeout=getattr(args, "poll_timeout", 300),
            transcribe_audio_video=not no_transcribe,
            transcription_language=getattr(args, "transcription_language", None),
            transcription_provider=getattr(args, "transcription_provider", "whisper"),
            skip_existing_transcriptions=not getattr(args, "force_transcribe", False),
            convert_opus_to_m4a=not getattr(args, "skip_opus_conversion", False),
            output_dir=output_dir,
            include_media=not getattr(args, "no_output_media", False),
            include_transcriptions=True,
            cleanup_temp=True,
            dry_run=False,
        )

        pipeline = WhatsAppPipeline(
            pipeline_config, logger=logger, on_progress=_log_progress,
        )
        logger.success(f"Pipeline configured — output: {output_dir}")

        # Step 7: Export + pipeline ----------------------------------------
        logger.step(7, "Exporting chats...")
        include_media = not getattr(args, "without_media", False)
        google_drive_folder = getattr(args, "google_drive_folder", None)

        exporter = ChatExporter(driver, logger, pipeline=pipeline)

        chat_names = [c.name for c in all_chats]
        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=chat_names,
            include_media=include_media,
            resume_folder=resume_folder,
            google_drive_folder=google_drive_folder,
        )

        # --- Summary ------------------------------------------------------
        logger.info("")
        logger.info("=" * 70)
        logger.info("Export Summary")
        logger.info("=" * 70)

        succeeded = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v) - len(skipped)
        skipped_count = len(skipped)

        logger.info(f"Total chats:  {len(all_chats)}")
        logger.info(f"Succeeded:    {succeeded}")
        logger.info(f"Failed:       {max(0, failed)}")
        logger.info(f"Skipped:      {skipped_count}")
        logger.info(f"Total time:   {total_time:.1f}s")
        logger.info(f"Output:       {output_dir}")
        logger.info("=" * 70)

        if succeeded == 0 and (failed > 0 or len(results) == 0):
            return 2  # Nothing worked
        elif failed > 0:
            return 1  # Partial success
        else:
            return 0  # All good

    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 2
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if getattr(args, "debug", False):
            import traceback
            traceback.print_exc()
        return 2
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if appium_manager:
            try:
                appium_manager.stop_appium()
            except Exception:
                pass
        logger.close()


# ---------------------------------------------------------------------------
# Pipeline-only mode
# ---------------------------------------------------------------------------

def run_pipeline_only(args: Namespace) -> int:
    """
    Run the pipeline on existing local files (no device export).

    Args:
        args: Parsed argparse Namespace with at minimum:
              - source: source directory path
              - pipeline_output: output directory path
              - no_transcribe, force_transcribe, transcription_provider
              - no_output_media, delete_from_drive, skip_drive_download
              - limit, debug

    Returns:
        Exit code: 0 = success, 1 = partial failure, 2 = fatal error
    """
    logger = Logger(debug=getattr(args, "debug", False))

    # Validate source directory
    source_dir = Path(args.source).expanduser()
    if not source_dir.is_dir():
        logger.error(f"Source directory does not exist: {source_dir}")
        return 2

    output_dir = Path(args.pipeline_output).expanduser()

    # Validate API key if transcription is enabled
    no_transcribe = getattr(args, "no_transcribe", False)
    if not no_transcribe:
        provider = getattr(args, "transcription_provider", "whisper")
        if not _validate_api_key(provider, logger):
            return 2

    # Build PipelineConfig mirroring pipeline_cli/cli.py
    config = PipelineConfig(
        # Source — pipeline-only always skips Drive download
        skip_download=True,
        download_dir=source_dir,
        delete_from_drive=getattr(args, "delete_from_drive", False),

        # Output
        output_dir=output_dir,
        include_media=not getattr(args, "no_output_media", False),
        include_transcriptions=True,

        # Transcription
        transcribe_audio_video=not no_transcribe,
        transcription_provider=getattr(args, "transcription_provider", "whisper"),
        skip_existing_transcriptions=not getattr(args, "force_transcribe", False),

        # General
        limit=getattr(args, "limit", None),
    )

    pipeline = WhatsAppPipeline(config, logger=logger, on_progress=_log_progress)

    try:
        results = pipeline.run(source_dir=source_dir)

        if results["success"]:
            logger.success("Pipeline completed successfully!")
            logger.info(f"Outputs created in: {config.output_dir}")
            return 0
        else:
            logger.error("Pipeline completed with errors")
            return 1

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Fatal pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return 2
