"""
CLI for WhatsApp Pipeline.

Provides command-line interface for the complete end-to-end pipeline.
"""

#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from ..pipeline import WhatsAppPipeline, PipelineConfig, create_default_config
from ..utils.logger import Logger


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Chat Export Pipeline - Complete end-to-end processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete pipeline (download from Drive, transcribe, organize)
  %(prog)s --output ~/exports

  # Skip download, process local files
  %(prog)s --skip-download --source ~/Downloads

  # Transcriptions only (no media in final output) - RECOMMENDED
  %(prog)s --no-media --output ~/exports

  # Download and organize without transcription
  %(prog)s --no-transcribe --output ~/exports

  # Minimal output (no media, no transcriptions)
  %(prog)s --no-media --no-transcribe --output ~/exports

  # Delete from Google Drive after download
  %(prog)s --delete-from-drive --output ~/exports

  # Dry run (no changes)
  %(prog)s --dry-run --output ~/exports
        """
    )

    # Source options
    source_group = parser.add_argument_group('Source Options')
    source_group.add_argument(
        '--source',
        type=str,
        metavar='DIR',
        help='Source directory with ZIP files (if skipping download)'
    )
    source_group.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip Google Drive download, use local files'
    )
    source_group.add_argument(
        '--google-drive-folder',
        type=str,
        metavar='NAME',
        help='Google Drive folder name to download from'
    )
    source_group.add_argument(
        '--delete-from-drive',
        action='store_true',
        help='Delete files from Google Drive after download'
    )

    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--output',
        type=str,
        metavar='DIR',
        required=True,
        help='Output directory for organized exports'
    )
    output_group.add_argument(
        '--no-media',
        action='store_true',
        help='Exclude media files from final output (transcriptions still created)'
    )
    output_group.add_argument(
        '--no-transcriptions',
        action='store_true',
        help='Do not include transcriptions in output'
    )

    # Transcription options
    transcribe_group = parser.add_argument_group('Transcription Options')
    transcribe_group.add_argument(
        '--no-transcribe',
        action='store_true',
        help='Skip audio/video transcription'
    )
    transcribe_group.add_argument(
        '--transcription-language',
        type=str,
        metavar='LANG',
        help='Language code for transcription (e.g., en, es, fr)'
    )
    transcribe_group.add_argument(
        '--transcription-provider',
        type=str,
        choices=['whisper', 'elevenlabs'],
        default='whisper',
        metavar='PROVIDER',
        help='Transcription service provider (whisper or elevenlabs, default: whisper)'
    )
    transcribe_group.add_argument(
        '--force-transcribe',
        action='store_true',
        help='Re-transcribe even if transcription exists'
    )
    transcribe_group.add_argument(
        '--skip-opus-conversion',
        action='store_true',
        help='Skip Opus to M4A conversion (requires FFmpeg)'
    )

    # General options
    parser.add_argument(
        '--keep-temp',
        action='store_true',
        help='Keep temporary files after processing'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (no file modifications)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose output)'
    )

    return parser


def main():
    """Main entry point for pipeline CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Create logger
    logger = Logger(debug=args.debug)

    # Validate arguments
    if not args.skip_download and not args.source:
        # Will download from Google Drive
        pass
    elif args.skip_download and not args.source:
        logger.error("--source required when using --skip-download")
        return 1

    # Validate API key if transcription is enabled
    if not args.no_transcribe:
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
                return 1

            logger.success(f"✅ {args.transcription_provider} API key validated")
        else:
            # API key not set - skip validation but warn user
            logger.warning(f"⚠️  {required_env_var} not set - skipping validation")
            logger.info(f"   Transcription will require {required_env_var} to be set at runtime")
            logger.info(f"   Set it with: export {required_env_var}='your-api-key-here'")

    # Create configuration
    config = PipelineConfig(
        # Source
        google_drive_folder=args.google_drive_folder,
        delete_from_drive=args.delete_from_drive,
        skip_download=args.skip_download,
        download_dir=Path(args.source).expanduser() if args.source else None,

        # Output
        output_dir=Path(args.output).expanduser(),
        include_media=not args.no_media,
        include_transcriptions=not args.no_transcriptions,

        # Transcription
        transcribe_audio_video=not args.no_transcribe,
        transcription_language=args.transcription_language,
        transcription_provider=args.transcription_provider,
        skip_existing_transcriptions=not args.force_transcribe,
        convert_opus_to_m4a=not args.skip_opus_conversion,

        # General
        cleanup_temp=not args.keep_temp,
        dry_run=args.dry_run
    )

    # Create and run pipeline
    pipeline = WhatsAppPipeline(config, logger=logger)

    try:
        source_dir = Path(args.source).expanduser() if args.source else None
        results = pipeline.run(source_dir=source_dir)

        if results['success']:
            logger.success("\n✓ Pipeline completed successfully!")
            logger.info(f"\nOutputs created in: {config.output_dir}")
            return 0
        else:
            logger.error("\n✗ Pipeline failed")
            return 1

    except KeyboardInterrupt:
        logger.warning("\n\nInterrupted by user")
        return 1
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
