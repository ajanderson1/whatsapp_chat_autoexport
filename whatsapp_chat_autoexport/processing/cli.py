"""
CLI entry point for WhatsApp Chat Processing.

This module provides backward compatibility with the original whatsapp_process.py script.
"""

#!/usr/bin/env python3

import sys
from pathlib import Path

from .archive_extractor import (
    validate_directory,
    find_whatsapp_chat_files,
    display_files_for_verification,
    create_processed_folder,
    move_files_to_processed,
    add_zip_extension,
    extract_zip_files,
    organize_extracted_content,
    cleanup_zip_files_and_folders,
    move_transcripts_to_directory
)
from ..utils.logger import Logger


def main():
    """Main entry point for the processing CLI."""
    # Get command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(
        description="WhatsApp Chat Processor - Process exported WhatsApp chat files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/downloads
  %(prog)s --debug /path/to/downloads
  %(prog)s --transcripts-dir ~/Documents/WhatsApp /path/to/downloads

This script will:
  1. Find WhatsApp chat export files in the specified directory
  2. Move them to a 'WhatsApp Chats Processed' subfolder
  3. Add .zip extension if needed
  4. Extract the zip files
  5. Organize content into transcripts/ and media/ folders
  6. Optionally clean up zip files and extraction folders
  7. Optionally move transcripts to a custom directory
        """
    )
    
    parser.add_argument(
        'directory',
        help='Directory containing WhatsApp chat export files'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose output)'
    )
    
    parser.add_argument(
        '--transcripts-dir',
        type=str,
        metavar='DIR',
        help='Optional: Move transcripts to this directory after processing'
    )
    
    args = parser.parse_args()
    
    # Create logger
    logger = Logger(debug=args.debug)
    
    # Welcome message
    print("=" * 70)
    logger.info("WhatsApp Chat Processor")
    print("=" * 70)
    
    try:
        # Step 1: Validate source directory
        logger.info("Step 1: Validating source directory...")
        source_dir = validate_directory(args.directory, logger)
        if source_dir is None:
            logger.error("Invalid source directory. Exiting.")
            sys.exit(1)
        
        # Step 2: Find WhatsApp chat files
        logger.info("Step 2: Finding WhatsApp chat files...")
        chat_files = find_whatsapp_chat_files(source_dir, logger)
        
        if not chat_files:
            logger.warning("No WhatsApp chat files found. Exiting.")
            sys.exit(0)
        
        # Step 3: Display files for verification
        logger.info("Step 3: Verifying found files...")
        if not display_files_for_verification(chat_files, logger):
            logger.info("Processing cancelled by user.")
            sys.exit(0)
        
        # Step 4: Create processed folder
        logger.info("Step 4: Creating processed folder...")
        processed_folder = create_processed_folder(source_dir, logger)
        if processed_folder is None:
            logger.error("Failed to create processed folder. Exiting.")
            sys.exit(1)
        
        # Step 5: Move files to processed folder
        logger.info("Step 5: Moving files to processed folder...")
        moved_files = move_files_to_processed(chat_files, processed_folder, logger)
        
        if not moved_files:
            logger.error("No files were moved. Exiting.")
            sys.exit(1)
        
        # Step 6: Add .zip extension if needed
        logger.info("Step 6: Adding .zip extension where needed...")
        zip_files = add_zip_extension(moved_files, logger)
        
        # Step 7: Extract zip files
        logger.info("Step 7: Extracting zip files...")
        extracted_folders = extract_zip_files(zip_files, logger)
        
        if not extracted_folders:
            logger.warning("No files were extracted. Exiting.")
            sys.exit(0)
        
        # Step 8: Organize extracted content
        logger.info("Step 8: Organizing extracted content...")
        organize_extracted_content(extracted_folders, processed_folder, logger)
        
        # Step 9: Optional cleanup
        logger.info("Step 9: Optional cleanup...")
        cleanup_zip_files_and_folders(zip_files, extracted_folders, logger)
        
        # Step 10: Optional move transcripts
        if args.transcripts_dir:
            logger.info("Step 10: Moving transcripts to custom directory...")
            transcripts_folder = processed_folder / "transcripts"
            if transcripts_folder.exists():
                target_dir = Path(args.transcripts_dir)
                move_transcripts_to_directory(transcripts_folder, target_dir, logger)
            else:
                logger.warning("Transcripts folder not found. Skipping move.")
        
        print("=" * 70)
        logger.success("✅ PROCESSING COMPLETE!")
        print("=" * 70)
        
        # Show summary
        transcripts_path = processed_folder / "transcripts"
        media_path = processed_folder / "media"
        
        if transcripts_path.exists():
            transcript_count = len(list(transcripts_path.glob("*.txt")))
            logger.info(f"📄 Transcripts: {transcript_count} files in {transcripts_path}")
        
        if media_path.exists():
            media_folders = [d for d in media_path.iterdir() if d.is_dir()]
            logger.info(f"📁 Media: {len(media_folders)} chat folders in {media_path}")
        
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
