"""
CLI entry point for WhatsApp Chat Auto-Export.

This module provides backward compatibility with the original whatsapp_export.py script.
"""

#!/usr/bin/env python3

import argparse
import signal
import sys

from pathlib import Path

from .appium_manager import AppiumManager
from .whatsapp_driver import WhatsAppDriver
from .chat_exporter import ChatExporter, validate_resume_directory
from .interactive import interactive_mode
from ..utils.logger import Logger
from ..pipeline import WhatsAppPipeline, PipelineConfig


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Chat Auto-Export - Export chats to Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic usage:
    %(prog)s                    # Interactive mode (export only)
    %(prog)s --debug            # Interactive mode with debug output
    %(prog)s --limit 5          # Limit to 5 chats

  With integrated pipeline (export → download → process):
    %(prog)s --output ~/exports
    # Export, download, transcribe, and organize automatically

    %(prog)s --output ~/exports --no-output-media
    # Export with media, transcribe, but exclude media from final output (RECOMMENDED)

    %(prog)s --output ~/exports --force-transcribe
    # Re-transcribe all audio/video even if transcriptions exist

    %(prog)s --output ~/exports --no-transcribe
    # Export and organize without transcription (faster)

    %(prog)s --output ~/exports --delete-from-drive
    # Delete from Google Drive after processing

    %(prog)s --output ~/exports --google-drive-folder WhatsApp
    # Process exports from specific Drive folder

  Advanced options:
    %(prog)s --without-media    # Export without media
    %(prog)s --resume /path/to/drive  # Skip already exported chats
    %(prog)s --all              # Auto-select all chats after timeout
    %(prog)s --wireless-adb     # Wireless ADB connection

For more information, visit: https://github.com/yourusername/whatsapp_chat_autoexport
        """
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose output)'
    )
    
    parser.add_argument(
        '--skip-appium',
        action='store_true',
        help='Skip starting Appium server (assume it is already running)'
    )
    
    # Limit argument
    parser.add_argument(
        '--limit',
        nargs='?',
        type=int,
        const=10,
        metavar='N',
        help='Limit the number of chats to process (default: 10 if flag used without value, no limit otherwise)'
    )
    
    # Media options (mutually exclusive)
    media_group = parser.add_mutually_exclusive_group()
    media_group.add_argument(
        '--with-media',
        action='store_true',
        default=True,
        help='Export chats with media (default)'
    )
    media_group.add_argument(
        '--without-media',
        dest='with_media',
        action='store_false',
        help='Export chats without media'
    )
    
    # Sort order for chat display
    parser.add_argument(
        '--sort-order',
        choices=['original', 'alphabetical'],
        default='alphabetical',
        help='How to sort/display chats: "original" (WhatsApp order) or "alphabetical" (default)'
    )
    
    # Resume functionality - specify Google Drive folder to check for existing exports
    parser.add_argument(
        '--resume',
        type=str,
        metavar='DRIVE_FOLDER',
        help='Path to Google Drive folder to check for existing exports. Chats already present will be skipped.'
    )
    
    # Auto-select all chats with timeout
    parser.add_argument(
        '--all',
        action='store_true',
        help='Auto-select all chats after timeout if no input provided'
    )

    # Pre-select chat range
    parser.add_argument(
        '--range',
        type=str,
        metavar='RANGE',
        help='Pre-select chat range for export (e.g., "300-500" or "1,5,10-20"). Also becomes default on timeout.'
    )

    # Wireless ADB support
    parser.add_argument(
        '--wireless-adb',
        nargs='*',
        metavar=('ADDRESS', 'CODE'),
        help='Connect to device via wireless ADB. Usage: --wireless-adb [PAIRING_IP:PORT] [6_DIGIT_CODE]'
    )

    # Pipeline options
    pipeline_group = parser.add_argument_group('Pipeline Options', 'Automatically process exports after downloading')
    pipeline_group.add_argument(
        '--output',
        type=str,
        metavar='DIR',
        help='Output directory for processed chats (enables pipeline processing)'
    )
    pipeline_group.add_argument(
        '--google-drive-folder',
        type=str,
        metavar='FOLDER',
        help='Google Drive folder name to download from'
    )
    pipeline_group.add_argument(
        '--delete-from-drive',
        action='store_true',
        help='Delete files from Google Drive after downloading'
    )
    pipeline_group.add_argument(
        '--no-transcribe',
        action='store_true',
        help='Skip audio/video transcription'
    )
    pipeline_group.add_argument(
        '--transcription-language',
        type=str,
        metavar='LANG',
        help='Language code for transcription (e.g., en, es, fr)'
    )
    pipeline_group.add_argument(
        '--transcription-provider',
        type=str,
        choices=['whisper', 'elevenlabs'],
        default='whisper',
        metavar='PROVIDER',
        help='Transcription service provider (whisper or elevenlabs, default: whisper)'
    )
    pipeline_group.add_argument(
        '--poll-interval',
        type=int,
        default=8,
        metavar='SECONDS',
        help='Seconds between Google Drive polls (default: 8)'
    )
    pipeline_group.add_argument(
        '--poll-timeout',
        type=int,
        default=300,
        metavar='SECONDS',
        help='Maximum wait time for Google Drive upload (default: 300 / 5 minutes)'
    )
    pipeline_group.add_argument(
        '--skip-opus-conversion',
        action='store_true',
        help='Skip Opus to M4A conversion (requires FFmpeg)'
    )
    pipeline_group.add_argument(
        '--force-transcribe',
        action='store_true',
        help='Re-transcribe even if transcription already exists'
    )
    pipeline_group.add_argument(
        '--no-output-media',
        action='store_true',
        help='Exclude media files from final output (transcriptions still created if media exported)'
    )

    return parser


def main():
    """Main entry point for the export CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Create logger
    logger = Logger(debug=args.debug)

    # Determine sort order
    # Pipeline mode: use original order (most recent chats first) for automation
    # Normal mode: use alphabetical (easier to find specific chats manually)
    if args.output:
        # Pipeline mode: default to original order (process newest chats first)
        # User can still override with --sort-order alphabetical if desired
        sort_alphabetical = False
    else:
        # Normal mode: respect user's choice (defaults to alphabetical)
        sort_alphabetical = (args.sort_order == 'alphabetical')
    
    # Validate resume directory if provided
    resume_folder = None
    if args.resume:
        resume_folder = validate_resume_directory(args.resume, logger)
        if resume_folder is None:
            logger.error("Invalid resume directory. Exiting.")
            sys.exit(1)

    # Validate API key if transcription is enabled
    if not args.no_transcribe and args.output:
        import os
        from whatsapp_chat_autoexport.transcription.transcriber_factory import TranscriberFactory

        # Determine which environment variable to check
        env_var_map = {
            'whisper': 'OPENAI_API_KEY',
            'elevenlabs': 'ELEVENLABS_API_KEY'
        }
        required_env_var = env_var_map.get(args.transcription_provider.lower(), 'OPENAI_API_KEY')

        # Check if API key is set
        api_key = os.environ.get(required_env_var)

        if api_key:
            # API key is set - validate it
            logger.info(f"Validating {args.transcription_provider} API key...")
            success, error_msg = TranscriberFactory.validate_provider(args.transcription_provider)

            if not success:
                logger.error(f"❌ API key validation failed:")
                logger.error(f"   {error_msg}")
                sys.exit(1)

            logger.success(f"✅ {args.transcription_provider} API key validated")
        else:
            # API key not set - skip validation but warn user
            logger.warning(f"⚠️  {required_env_var} not set - skipping validation")
            logger.info(f"   Transcription will require {required_env_var} to be set at runtime")
            logger.info(f"   Set it with: export {required_env_var}='your-api-key-here'")

    # Welcome message
    logger.info("=" * 70)
    logger.info("🚀 WhatsApp Chat Auto-Export")
    logger.info("=" * 70)
    
    appium_manager = None
    driver = None

    try:
        # Step 1: Start Appium (unless --skip-appium)
        if not args.skip_appium:
            logger.step(1, "Setting up Android environment...")
            appium_manager = AppiumManager(logger)
            if not appium_manager.start_appium():
                logger.error("Failed to start Appium. Exiting.")
                sys.exit(1)
        else:
            logger.info("Skipping Appium startup (--skip-appium flag set)")
            logger.info("Assuming Appium is already running on port 4723")
        
        # Step 2: Connect to device
        driver = WhatsAppDriver(logger, wireless_adb=args.wireless_adb)
        if not driver.check_device_connection():
            logger.error("No device connected. Exiting.")
            sys.exit(1)
        
        # Step 3: Connect to WhatsApp
        logger.step(2, "Connecting to WhatsApp...")
        if not driver.connect():
            logger.error("Failed to connect to WhatsApp. Exiting.")
            sys.exit(1)

        # Step 4: Navigate to main screen
        logger.step(3, "Navigating to main chats screen...")
        if not driver.navigate_to_main():
            logger.error("Failed to navigate to main screen. Exiting.")
            sys.exit(1)
        
        # Step 5: Create pipeline if output directory specified
        pipeline = None
        if args.output:
            logger.info("\n" + "=" * 70)
            logger.info("🔧 Configuring Pipeline")
            logger.info("=" * 70)

            pipeline_config = PipelineConfig(
                google_drive_folder=args.google_drive_folder,
                delete_from_drive=args.delete_from_drive,
                skip_download=False,  # Always download from Drive
                poll_interval=args.poll_interval,
                poll_timeout=args.poll_timeout,
                transcribe_audio_video=not args.no_transcribe,
                transcription_language=args.transcription_language,
                transcription_provider=args.transcription_provider,
                skip_existing_transcriptions=not args.force_transcribe,
                convert_opus_to_m4a=not args.skip_opus_conversion,
                output_dir=Path(args.output).expanduser(),
                include_media=not args.no_output_media,
                include_transcriptions=True,
                cleanup_temp=True,
                dry_run=False
            )

            pipeline = WhatsAppPipeline(pipeline_config, logger=logger)
            logger.success(f"Pipeline configured - output directory: {pipeline_config.output_dir}")
            if args.delete_from_drive:
                logger.info("  ⚠️  Will delete from Google Drive after download")
            if not args.no_transcribe:
                logger.info(f"  🎤 Audio/video transcription enabled ({args.transcription_provider})")
                if args.force_transcribe:
                    logger.info("  🔄 Force re-transcribe mode: Existing transcriptions will be overwritten")
            if args.no_output_media:
                logger.info("  📁 Media will be excluded from final output (used for transcription only)")

        # Step 6: Create exporter
        exporter = ChatExporter(driver, logger, pipeline=pipeline)

        # Step 7: Run interactive mode
        logger.info("=" * 70)
        logger.info("📋 INTERACTIVE MODE")
        logger.info("=" * 70)

        # Auto-enable countdown if pipeline is configured (for automation)
        # or if --all flag is explicitly set
        auto_all = args.all or (pipeline is not None)

        if auto_all and pipeline:
            logger.info("🤖 Pipeline mode: Auto-continuing after 30s timeout")
            logger.info("📋 Chats will be shown in original order (most recent first)")

        interactive_mode(
            driver,
            exporter,
            logger,
            test_limit=args.limit,
            include_media=args.with_media,
            sort_alphabetical=sort_alphabetical,
            resume_folder=resume_folder,
            auto_all=auto_all,
            google_drive_folder=args.google_drive_folder,
            default_range=args.range
        )
        
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user. Cleaning up...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if driver:
            driver.quit()
        if appium_manager:
            appium_manager.stop_appium()
        
        logger.info("=" * 70)
        logger.info("✅ SCRIPT COMPLETE")
        logger.info("=" * 70)


if __name__ == "__main__":
    main()
