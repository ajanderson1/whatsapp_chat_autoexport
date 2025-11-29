"""
Archive Extractor module for WhatsApp Chat Auto-Export.

Handles ZIP extraction, file organization, and transcript processing.
"""

import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..utils.logger import Logger


def is_zip_file(file_path: Path) -> bool:
    """
    Check if a file is actually a zip archive by examining its magic bytes.
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        True if file is a zip archive, False otherwise
    """
    try:
        # Check magic bytes (PK header - zip files start with "PK")
        with open(file_path, 'rb') as f:
            header = f.read(4)
            # ZIP files start with "PK\x03\x04" or "PK\x05\x06" (empty zip)
            if header[:2] == b'PK':
                # Try to open as zip to verify it's valid
                try:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.testzip()  # Test if zip is valid
                    return True
                except (zipfile.BadZipFile, zipfile.LargeZipFile):
                    return False
    except Exception as e:
        return False
    return False


def validate_directory(directory_path: str, logger: Logger) -> Optional[Path]:
    """
    Validate source directory path with robust validation.
    
    Args:
        directory_path: Directory path string to validate
        logger: Logger instance for output
        
    Returns:
        Path to validated directory, or None if validation fails
    """
    # Handle empty input
    if not directory_path:
        logger.error("Directory path is required")
        return None
    
    directory_path = directory_path.strip()
    
    # Expand user home directory (~)
    if directory_path.startswith('~'):
        directory_path = os.path.expanduser(directory_path)
    
    # Remove quotes if present
    directory_path = directory_path.strip('"').strip("'")
    
    # Convert to Path
    try:
        path_obj = Path(directory_path).resolve()
    except Exception as e:
        logger.error(f"Invalid path format: {e}")
        return None
    
    # Validate directory exists
    if not path_obj.exists():
        logger.error(f"Directory does not exist: {path_obj}")
        return None
    
    # Validate it's actually a directory
    if not path_obj.is_dir():
        logger.error(f"Path is not a directory: {path_obj}")
        return None
    
    # Validate readable
    if not os.access(path_obj, os.R_OK):
        logger.error(f"Directory is not readable: {path_obj}")
        return None
    
    logger.success(f"Directory validated: {path_obj}")
    return path_obj


def find_whatsapp_chat_files(directory: Path, logger: Logger) -> List[Path]:
    """
    Find files matching "WhatsApp Chat with ..." pattern and verify they are zip files.
    
    Args:
        directory: Directory to search in
        logger: Logger instance for output
        
    Returns:
        List of Path objects for matching zip files
    """
    logger.info("Scanning for WhatsApp chat files...")
    logger.debug_msg(f"Searching in: {directory}")
    
    matching_files = []
    pattern = "WhatsApp Chat with "
    
    try:
        # Get all files (not directories) in the directory
        all_files = [f for f in directory.iterdir() if f.is_file()]
        logger.debug_msg(f"Found {len(all_files)} total files in directory")
        
        for file_path in all_files:
            file_name = file_path.name
            
            # Check if file matches pattern
            if file_name.startswith(pattern):
                logger.debug_msg(f"Found matching file: {file_name}")
                
                # Verify it's actually a zip file
                if is_zip_file(file_path):
                    matching_files.append(file_path)
                    logger.debug_msg(f"Verified as zip file: {file_name}")
                else:
                    logger.warning(f"File matches pattern but is not a valid zip: {file_name}")
        
        logger.success(f"Found {len(matching_files)} WhatsApp chat export file(s)")
        
    except Exception as e:
        logger.error(f"Error scanning directory: {e}")
        return []
    
    return matching_files


def display_files_for_verification(files: List[Path], logger: Logger) -> bool:
    """
    Display list of files and prompt user for confirmation.
    
    Args:
        files: List of file paths to display
        logger: Logger instance for output
        
    Returns:
        True if user confirms, False if user aborts
    """
    if not files:
        logger.warning("No files found to process.")
        return False
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("Files found for processing:")
    logger.info("=" * 70)
    
    for i, file_path in enumerate(files, 1):
        logger.info(f"{i:3d}. {file_path.name}")
    
    logger.info("")
    logger.info("These files will be:")
    logger.info("  1. Moved to 'WhatsApp Chats Processed' folder")
    logger.info("  2. Renamed with .zip extension")
    logger.info("  3. Extracted and organized")
    logger.info("")
    
    while True:
        response = input("Proceed with processing? (yes/no/q): ").strip().lower()
        
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', 'q', 'quit', 'exit']:
            logger.info("Processing cancelled.")
            return False
        else:
            logger.warning("Please enter 'yes', 'no', or 'q' to quit")


def create_processed_folder(source_dir: Path, logger: Logger) -> Optional[Path]:
    """
    Create 'WhatsApp Chats Processed' folder in source directory.
    
    Args:
        source_dir: Source directory path
        logger: Logger instance for output
        
    Returns:
        Path to created folder, or None if creation failed
    """
    folder_name = "WhatsApp Chats Processed"
    processed_folder = source_dir / folder_name
    
    try:
        if processed_folder.exists():
            logger.warning(f"Folder already exists: {processed_folder}")
            # Check if it's a directory
            if not processed_folder.is_dir():
                logger.error(f"Path exists but is not a directory: {processed_folder}")
                return None
        else:
            processed_folder.mkdir(parents=True, exist_ok=True)
            logger.success(f"Created folder: {processed_folder}")
        
        return processed_folder
    except Exception as e:
        logger.error(f"Failed to create processed folder: {e}")
        return None


def move_files_to_processed(files: List[Path], processed_folder: Path, logger: Logger) -> List[Path]:
    """
    Move files to processed folder using parallel processing.
    
    Args:
        files: List of source file paths
        processed_folder: Destination folder path
        logger: Logger instance for output
    
    Returns:
        List of paths to moved files in processed folder
    """
    moved_files = []
    
    logger.info("Moving files to processed folder...")
    
    def move_file(file_path: Path) -> Tuple[Path, bool, Optional[str]]:
        """Move a single file. Returns (dest_path, success, error_msg)."""
        try:
            dest_path = processed_folder / file_path.name
            
            # Check if destination already exists
            if dest_path.exists():
                return (dest_path, False, f"File already exists in destination: {dest_path.name}")
            
            shutil.move(str(file_path), str(dest_path))
            logger.debug_msg(f"Moved: {file_path.name} -> {dest_path}")
            return (dest_path, True, None)
        except Exception as e:
            return (processed_folder / file_path.name, False, str(e))
    
    # Use ThreadPoolExecutor for parallel file moves
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all move tasks
        future_to_file = {executor.submit(move_file, file_path): file_path for file_path in files}
        
        # Process results as they complete
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                dest_path, success, error_msg = future.result()
                if success:
                    moved_files.append(dest_path)
                else:
                    if error_msg:
                        if "already exists" in error_msg:
                            logger.warning(f"File already exists in destination: {dest_path.name}")
                            logger.info(f"  Skipping: {file_path.name}")
                        else:
                            logger.error(f"Failed to move {file_path.name}: {error_msg}")
            except Exception as e:
                logger.error(f"Failed to move {file_path.name}: {e}")
    
    logger.success(f"Moved {len(moved_files)} file(s) to processed folder")
    return moved_files


def add_zip_extension(files: List[Path], logger: Logger) -> List[Path]:
    """
    Add .zip extension to files.
    
    Args:
        files: List of file paths
        logger: Logger instance for output
        
    Returns:
        List of paths to renamed files
    """
    renamed_files = []
    
    logger.info("Adding .zip extension to files...")
    
    for file_path in files:
        try:
            # Check if already has .zip extension
            if file_path.suffix.lower() == '.zip':
                logger.debug_msg(f"Already has .zip extension: {file_path.name}")
                renamed_files.append(file_path)
                continue
            
            new_path = file_path.with_suffix(file_path.suffix + '.zip')
            
            # Check if new path already exists
            if new_path.exists():
                logger.warning(f"File with .zip extension already exists: {new_path.name}")
                renamed_files.append(new_path)  # Use existing file
                continue
            
            file_path.rename(new_path)
            renamed_files.append(new_path)
            logger.debug_msg(f"Renamed: {file_path.name} -> {new_path.name}")
        except Exception as e:
            logger.error(f"Failed to rename {file_path.name}: {e}")
    
    logger.success(f"Added .zip extension to {len(renamed_files)} file(s)")
    return renamed_files


def extract_zip_files(zip_files: List[Path], logger: Logger) -> List[Path]:
    """
    Extract all zip files using parallel processing.
    
    Args:
        zip_files: List of zip file paths
        logger: Logger instance for output
    
    Returns:
        List of paths to extracted folders
    """
    extracted_folders = []
    
    logger.info("Extracting zip files...")
    
    def extract_zip(zip_path: Path) -> Tuple[Path, bool, Optional[str]]:
        """Extract a single zip file. Returns (extract_folder, success, error_msg)."""
        try:
            # Extract to folder with same name (without .zip extension)
            extract_folder = zip_path.parent / zip_path.stem
            
            # Check if folder already exists
            if extract_folder.exists():
                return (extract_folder, False, f"Extraction folder already exists: {extract_folder.name}")
            
            extract_folder.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Log ZIP contents for debugging
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                
                # Count file types
                txt_files = [f for f in file_list if f.lower().endswith('.txt')]
                media_files = [f for f in file_list if not f.lower().endswith('.txt') and not f.endswith('/')]
                
                logger.info(f"📦 ZIP contents for '{zip_path.name}':")
                logger.info(f"   Total files: {total_files}")
                logger.info(f"   Transcript files (.txt): {len(txt_files)}")
                logger.info(f"   Media files: {len(media_files)}")
                
                if logger.debug and media_files:
                    logger.debug_msg(f"   Media file types in ZIP:")
                    extensions = {}
                    for f in media_files:
                        ext = Path(f).suffix.lower()
                        extensions[ext] = extensions.get(ext, 0) + 1
                    for ext, count in sorted(extensions.items()):
                        logger.debug_msg(f"     {ext}: {count}")
                
                # Extract all files
                zip_ref.extractall(extract_folder)
            
            logger.success(f"✓ Extracted: {zip_path.name} → {total_files} files")
            return (extract_folder, True, None)
        except zipfile.BadZipFile:
            return (zip_path.parent / zip_path.stem, False, f"Invalid or corrupted zip file: {zip_path.name}")
        except Exception as e:
            return (zip_path.parent / zip_path.stem, False, str(e))
    
    # Use ThreadPoolExecutor for parallel zip extraction (max_workers=2 to avoid I/O bottleneck)
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit all extraction tasks
        future_to_zip = {executor.submit(extract_zip, zip_path): zip_path for zip_path in zip_files}
        
        # Process results as they complete
        for future in as_completed(future_to_zip):
            zip_path = future_to_zip[future]
            try:
                extract_folder, success, error_msg = future.result()
                if success:
                    extracted_folders.append(extract_folder)
                else:
                    if error_msg:
                        if "already exists" in error_msg:
                            logger.warning(f"Extraction folder already exists: {extract_folder.name}")
                            logger.info(f"  Skipping extraction of: {zip_path.name}")
                            extracted_folders.append(extract_folder)  # Include existing folder
                        elif "corrupted" in error_msg.lower() or "invalid" in error_msg.lower():
                            logger.error(error_msg)
                        else:
                            logger.error(f"Failed to extract {zip_path.name}: {error_msg}")
            except Exception as e:
                logger.error(f"Failed to extract {zip_path.name}: {e}")
    
    logger.success(f"Extracted {len(extracted_folders)} archive(s)")
    return extracted_folders


def cleanup_zip_files_and_folders(zip_files: List[Path], extracted_folders: List[Path], logger: Logger):
    """
    Clean up zip files and extracted folders after organization is complete.
    Prompts user for confirmation before deletion.
    
    Args:
        zip_files: List of zip file paths to delete
        extracted_folders: List of extracted folder paths to delete
        logger: Logger instance for output
    """
    if not zip_files and not extracted_folders:
        logger.info("No files or folders to clean up.")
        return
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("Cleanup: Remove zip files and extracted folders")
    logger.info("=" * 70)
    
    if zip_files:
        logger.info(f"\nZip files to delete ({len(zip_files)}):")
        for zip_file in zip_files:
            logger.info(f"  - {zip_file.name}")
    
    if extracted_folders:
        logger.info(f"\nExtracted folders to delete ({len(extracted_folders)}):")
        for folder in extracted_folders:
            logger.info(f"  - {folder.name}")
    
    logger.info("")
    logger.warning("⚠️  This will permanently delete the zip files and extracted folders.")
    logger.info("   Organized content (transcripts/ and media/) will remain.")
    logger.info("")
    
    while True:
        response = input("Proceed with cleanup? (yes/no/q): ").strip().lower()
        
        if response in ['y', 'yes']:
            break
        elif response in ['n', 'no', 'q', 'quit', 'exit']:
            logger.info("Cleanup cancelled. Files and folders will remain.")
            return
        else:
            logger.warning("Please enter 'yes', 'no', or 'q' to quit")
    
    # Delete zip files
    deleted_zips = 0
    for zip_file in zip_files:
        try:
            if zip_file.exists():
                zip_file.unlink()
                deleted_zips += 1
                logger.debug_msg(f"Deleted zip file: {zip_file.name}")
        except Exception as e:
            logger.error(f"Failed to delete zip file {zip_file.name}: {e}")
    
    # Delete extracted folders
    deleted_folders = 0
    for folder in extracted_folders:
        try:
            if folder.exists() and folder.is_dir():
                shutil.rmtree(folder)
                deleted_folders += 1
                logger.debug_msg(f"Deleted folder: {folder.name}")
        except Exception as e:
            logger.error(f"Failed to delete folder {folder.name}: {e}")
    
    logger.success(f"Cleanup complete:")
    logger.info(f"  Zip files deleted: {deleted_zips}")
    logger.info(f"  Folders deleted: {deleted_folders}")


def organize_extracted_content(extracted_folders: List[Path], processed_folder: Path, logger: Logger):
    """
    Organize extracted content into transcripts/ and media/[chat name]/ folders.
    
    Args:
        extracted_folders: List of paths to extracted folders
        processed_folder: Base processed folder path
        logger: Logger instance for output
    """
    logger.info("Organizing extracted content...")
    
    # Create top-level organization folders
    transcripts_folder = processed_folder / "transcripts"
    media_folder = processed_folder / "media"
    
    try:
        transcripts_folder.mkdir(exist_ok=True)
        media_folder.mkdir(exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create organization folders: {e}")
        return
    
    transcripts_moved = 0
    media_moved = 0
    
    for extract_folder in extracted_folders:
        chat_name = extract_folder.name
        
        logger.debug_msg(f"Processing folder: {chat_name}")
        
        if not extract_folder.is_dir():
            logger.warning(f"Skipping non-directory: {extract_folder}")
            continue
        
        # Process all files in extracted folder
        for item in extract_folder.rglob('*'):
            if item.is_dir():
                continue
            
            try:
                # Identify file type
                if item.suffix.lower() == '.txt':
                    # Check if it's the transcript file (same name as folder)
                    if item.stem == chat_name:
                        dest = transcripts_folder / item.name
                        if dest.exists():
                            logger.warning(f"Transcript already exists: {item.name}")
                        else:
                            shutil.move(str(item), str(dest))
                            transcripts_moved += 1
                            logger.debug_msg(f"  Moved transcript: {item.name}")
                    else:
                        # Other text files - still move to transcripts
                        dest = transcripts_folder / item.name
                        if dest.exists():
                            logger.warning(f"Transcript already exists: {item.name}")
                        else:
                            shutil.move(str(item), str(dest))
                            transcripts_moved += 1
                            logger.debug_msg(f"  Moved text file: {item.name}")
                
                else:
                    # Media file (images, videos, audio, contacts, etc.)
                    chat_media_folder = media_folder / chat_name
                    chat_media_folder.mkdir(exist_ok=True)
                    
                    dest = chat_media_folder / item.name
                    if dest.exists():
                        logger.warning(f"Media file already exists: {chat_name}/{item.name}")
                    else:
                        shutil.move(str(item), str(dest))
                        media_moved += 1
                        logger.debug_msg(f"  Moved media: {chat_name}/{item.name}")
                        
            except Exception as e:
                logger.error(f"Failed to move {item.name}: {e}")
    
    logger.success(f"Organization complete:")
    logger.info(f"  Transcripts moved: {transcripts_moved}")
    logger.info(f"  Media files moved: {media_moved}")


def is_duplicate_file(file_path: Path) -> bool:
    """
    Check if a file is a duplicate based on naming pattern (e.g., file(1).txt, file(2).txt).
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        True if file matches duplicate pattern, False otherwise
    """
    # Pattern: filename ends with (number).txt
    # e.g., "WhatsApp Chat with John(1).txt", "Chat(2).txt"
    pattern = r'\(\d+\)\.txt$'
    return bool(re.search(pattern, file_path.name))


def move_transcripts_to_directory(transcripts_folder: Path, target_dir: Path, logger: Logger):
    """
    Move all .txt files from transcripts folder to target directory.
    Handles duplicate detection and overwrite prompts.
    
    Args:
        transcripts_folder: Source folder containing transcript files
        target_dir: Target directory to move files to
        logger: Logger instance for output
    """
    logger.info("")
    logger.info("=" * 70)
    logger.info("Move Transcripts to Target Directory")
    logger.info("=" * 70)
    
    # Find all .txt files in transcripts folder
    transcript_files = list(transcripts_folder.glob("*.txt"))
    
    if not transcript_files:
        logger.warning("No transcript files found to move.")
        return
    
    logger.info(f"\nFound {len(transcript_files)} transcript file(s) to move:")
    for i, file_path in enumerate(transcript_files, 1):
        logger.info(f"  {i:3d}. {file_path.name}")
    
    logger.info("")
    logger.info(f"Target directory: {target_dir}")
    logger.info("")
    
    # Check for duplicate files
    duplicate_files = [f for f in transcript_files if is_duplicate_file(f)]
    if duplicate_files:
        logger.warning(f"\nFound {len(duplicate_files)} duplicate file(s) (ending with (1), (2), etc.):")
        for dup_file in duplicate_files:
            logger.warning(f"  - {dup_file.name}")
        logger.info("")
        
        while True:
            response = input("Remove duplicate files? (yes/no/q): ").strip().lower()
            if response in ['y', 'yes']:
                # Remove duplicate files
                for dup_file in duplicate_files:
                    try:
                        dup_file.unlink()
                        logger.debug_msg(f"Removed duplicate: {dup_file.name}")
                    except Exception as e:
                        logger.error(f"Failed to remove duplicate {dup_file.name}: {e}")
                # Remove duplicates from transcript_files list
                transcript_files = [f for f in transcript_files if not is_duplicate_file(f)]
                logger.success(f"Removed {len(duplicate_files)} duplicate file(s)")
                break
            elif response in ['n', 'no', 'q', 'quit', 'exit']:
                logger.info("Keeping duplicate files.")
                break
            else:
                logger.warning("Please enter 'yes', 'no', or 'q' to quit")
    
    if not transcript_files:
        logger.info("No files remaining to move.")
        return
    
    # Check for existing files in target directory
    existing_files = []
    files_to_move = []
    
    for file_path in transcript_files:
        dest_path = target_dir / file_path.name
        if dest_path.exists():
            existing_files.append((file_path, dest_path))
        else:
            files_to_move.append((file_path, dest_path))
    
    # Handle existing files
    moved_count = 0
    if existing_files:
        logger.info("")
        logger.warning(f"Found {len(existing_files)} file(s) that already exist in target directory:")
        for src_path, dest_path in existing_files:
            logger.warning(f"  - {src_path.name}")
        logger.info("")
        
        overwrite_all = False
        skip_all = False
        
        for src_path, dest_path in existing_files:
            if skip_all:
                logger.info(f"Skipping: {src_path.name}")
                continue
            
            if not overwrite_all:
                while True:
                    response = input(f"Overwrite '{src_path.name}'? (yes/no/all/skip-all/q): ").strip().lower()
                    if response in ['y', 'yes']:
                        # Overwrite this file
                        try:
                            shutil.move(str(src_path), str(dest_path))
                            moved_count += 1
                            logger.debug_msg(f"Moved (overwritten): {src_path.name}")
                        except Exception as e:
                            logger.error(f"Failed to overwrite {src_path.name}: {e}")
                        break
                    elif response in ['n', 'no']:
                        logger.info(f"Skipping: {src_path.name}")
                        break
                    elif response in ['a', 'all']:
                        overwrite_all = True
                        # Overwrite this file and all remaining
                        try:
                            shutil.move(str(src_path), str(dest_path))
                            moved_count += 1
                            logger.debug_msg(f"Moved (overwritten): {src_path.name}")
                        except Exception as e:
                            logger.error(f"Failed to overwrite {src_path.name}: {e}")
                        break
                    elif response in ['s', 'skip-all']:
                        skip_all = True
                        logger.info(f"Skipping: {src_path.name}")
                        break
                    elif response in ['q', 'quit', 'exit']:
                        logger.info("Cancelled moving transcripts.")
                        return
                    else:
                        logger.warning("Please enter 'yes', 'no', 'all', 'skip-all', or 'q' to quit")
            else:
                # Overwrite all remaining files
                try:
                    shutil.move(str(src_path), str(dest_path))
                    moved_count += 1
                    logger.debug_msg(f"Moved (overwritten): {src_path.name}")
                except Exception as e:
                    logger.error(f"Failed to overwrite {src_path.name}: {e}")
    
    # Move remaining files that don't exist in target
    for src_path, dest_path in files_to_move:
        try:
            if src_path.exists() and not dest_path.exists():
                shutil.move(str(src_path), str(dest_path))
                moved_count += 1
                logger.debug_msg(f"Moved: {src_path.name}")
        except Exception as e:
            logger.error(f"Failed to move {src_path.name}: {e}")
    
    logger.success(f"Moved {moved_count} transcript file(s) to {target_dir}")

