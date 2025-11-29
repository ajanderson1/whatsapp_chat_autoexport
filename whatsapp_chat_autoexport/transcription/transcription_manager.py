"""
Transcription Manager for WhatsApp Chat Auto-Export.

Handles batch transcription of media files with resume functionality.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from tqdm import tqdm
import json

from .base_transcriber import BaseTranscriber, TranscriptionResult
from ..utils.logger import Logger


class TranscriptionManager:
    """
    Manages batch transcription of audio/video files.

    Features:
    - Batch processing with progress tracking
    - Resume functionality (skip already transcribed files)
    - Output organization (transcriptions saved alongside media)
    - Summary statistics
    """

    # Transcription file suffix
    TRANSCRIPTION_SUFFIX = "_transcription.txt"

    def __init__(
        self,
        transcriber: BaseTranscriber,
        logger: Optional[Logger] = None,
        output_dir: Optional[Path] = None,
        contact_name_extractor: Optional[Callable[[Path], str]] = None
    ):
        """
        Initialize transcription manager.

        Args:
            transcriber: Transcriber instance to use
            logger: Optional logger for output
            output_dir: Optional output directory to check for existing transcriptions from previous runs
            contact_name_extractor: Optional function to extract contact name from transcript path
        """
        self.transcriber = transcriber
        self.logger = logger or Logger()
        self.output_dir = output_dir
        self.contact_name_extractor = contact_name_extractor

    def get_transcription_path(self, media_file: Path) -> Path:
        """
        Get the output path for a transcription file.

        Args:
            media_file: Path to the media file

        Returns:
            Path where transcription should be saved
            Example: media/audio.opus -> media/audio_transcription.txt
        """
        return media_file.parent / f"{media_file.stem}{self.TRANSCRIPTION_SUFFIX}"

    def is_transcribed(self, media_file: Path, transcript_path: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if a media file has already been transcribed.

        Checks TWO locations:
        1. Temp processing directory (current run)
        2. Final output directory (previous runs) - if output_dir is configured

        Args:
            media_file: Path to the media file
            transcript_path: Optional transcript path for extracting contact name

        Returns:
            Tuple of (is_transcribed: bool, location: Optional[str])
            location is "temp" or "output" if found, None if not found
        """
        # Check Location 1: Temp processing directory
        temp_transcription_path = self.get_transcription_path(media_file)
        if temp_transcription_path.exists() and temp_transcription_path.stat().st_size > 0:
            return True, "temp"

        # Check Location 2: Final output directory (from previous runs)
        if self.output_dir and transcript_path and self.contact_name_extractor:
            try:
                contact_name = self.contact_name_extractor(transcript_path)
                output_transcription_path = (
                    self.output_dir / contact_name / "transcriptions" /
                    f"{media_file.stem}{self.TRANSCRIPTION_SUFFIX}"
                )
                if output_transcription_path.exists() and output_transcription_path.stat().st_size > 0:
                    return True, "output"
            except Exception as e:
                self.logger.debug_msg(f"Could not check output directory for {media_file.name}: {e}")

        return False, None

    def save_transcription(
        self,
        media_file: Path,
        result: TranscriptionResult,
        include_metadata: bool = True
    ) -> Optional[Path]:
        """
        Save transcription result to file.

        Args:
            media_file: Path to the media file
            result: Transcription result
            include_metadata: Whether to include metadata header

        Returns:
            Path to saved transcription file, or None if failed
        """
        if not result.success or not result.text:
            self.logger.error(f"Cannot save failed transcription for {media_file.name}")
            return None

        transcription_path = self.get_transcription_path(media_file)

        try:
            with open(transcription_path, 'w', encoding='utf-8') as f:
                # Optional metadata header
                if include_metadata:
                    f.write(f"# Transcription of: {media_file.name}\n")
                    f.write(f"# Transcribed at: {result.timestamp}\n")

                    if result.language:
                        f.write(f"# Language: {result.language}\n")

                    if result.duration_seconds:
                        f.write(f"# Processing time: {result.duration_seconds:.2f}s\n")

                    if result.metadata:
                        f.write(f"# Model: {result.metadata.get('model', 'unknown')}\n")

                    f.write("\n")

                # Write transcription text
                f.write(result.text)
                f.write("\n")

            self.logger.success(f"Saved transcription: {transcription_path.name}")
            return transcription_path

        except Exception as e:
            self.logger.error(f"Failed to save transcription: {e}")
            return None

    def transcribe_file(
        self,
        media_file: Path,
        skip_existing: bool = True,
        transcript_path: Optional[Path] = None,
        **transcribe_kwargs
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Transcribe a single media file.

        Args:
            media_file: Path to media file
            skip_existing: Skip if transcription already exists
            transcript_path: Optional transcript path (for checking output directory)
            **transcribe_kwargs: Additional arguments passed to transcriber

        Returns:
            Tuple of (success: bool, transcription_path: Optional[Path], error: Optional[str])
        """
        # Check if already transcribed (in temp or output directory)
        if skip_existing:
            is_transcribed, location = self.is_transcribed(media_file, transcript_path)
            if is_transcribed:
                # Show where transcription was found
                if location == "output" and self.contact_name_extractor and transcript_path:
                    contact_name = self.contact_name_extractor(transcript_path)
                    self.logger.info(f"⏭️  Skipping (found in output): {contact_name}/{media_file.name}")
                else:
                    folder_name = media_file.parent.name
                    self.logger.info(f"⏭️  Skipping (found in temp): {folder_name}/{media_file.name}")
                transcription_path = self.get_transcription_path(media_file)
                return True, transcription_path, None

        # Validate file
        is_valid, error_msg = self.transcriber.validate_file(media_file)
        if not is_valid:
            self.logger.error(f"Invalid file: {error_msg}")
            return False, None, error_msg

        # Transcribe (pass skip_existing to allow force re-transcription)
        result = self.transcriber.transcribe(media_file, skip_existing=skip_existing, **transcribe_kwargs)

        if not result.success:
            return False, None, result.error

        # Save transcription
        transcription_path = self.save_transcription(media_file, result)

        if transcription_path:
            return True, transcription_path, None
        else:
            return False, None, "Failed to save transcription"

    def batch_transcribe(
        self,
        media_files: List[Path],
        skip_existing: bool = True,
        show_progress: bool = True,
        transcript_path: Optional[Path] = None,
        **transcribe_kwargs
    ) -> Dict[str, any]:
        """
        Transcribe multiple media files in batch.

        Args:
            media_files: List of media file paths
            skip_existing: Skip files that are already transcribed
            show_progress: Show progress bar
            transcript_path: Optional transcript path (for checking output directory)
            **transcribe_kwargs: Additional arguments passed to transcriber

        Returns:
            Dictionary with results:
            {
                'total': int,
                'successful': int,
                'skipped': int,
                'failed': int,
                'transcriptions': List[Path],
                'skipped_files': List[Path],
                'errors': List[Tuple[Path, str]]
            }
        """
        if not media_files:
            self.logger.warning("No media files to transcribe")
            return {
                'total': 0,
                'successful': 0,
                'skipped': 0,
                'failed': 0,
                'transcriptions': [],
                'errors': []
            }

        self.logger.info(f"Transcribing {len(media_files)} file(s)...")

        # Check if transcriber is available
        if not self.transcriber.is_available():
            self.logger.error("Transcription service not available")
            return {
                'total': len(media_files),
                'successful': 0,
                'skipped': 0,
                'failed': len(media_files),
                'transcriptions': [],
                'errors': [(f, "Transcription service not available") for f in media_files]
            }

        results = {
            'total': len(media_files),
            'successful': 0,
            'skipped': 0,
            'failed': 0,
            'transcriptions': [],
            'skipped_files': [],  # Track skipped files for reporting
            'errors': []
        }

        # Process files with progress bar
        iterator = tqdm(media_files, desc="Transcribing", unit="file") if show_progress else media_files

        for media_file in iterator:
            if show_progress:
                iterator.set_description(f"Transcribing {media_file.name[:30]}")

            # Check if already transcribed (for skipped count)
            already_transcribed, _ = self.is_transcribed(media_file, transcript_path) if skip_existing else (False, None)

            # Transcribe file
            success, transcription_path_result, error = self.transcribe_file(
                media_file,
                skip_existing=skip_existing,
                transcript_path=transcript_path,
                **transcribe_kwargs
            )

            if success:
                if already_transcribed:
                    results['skipped'] += 1
                    results['skipped_files'].append(media_file)
                else:
                    results['successful'] += 1

                if transcription_path_result:
                    results['transcriptions'].append(transcription_path_result)
            else:
                results['failed'] += 1
                results['errors'].append((media_file, error or "Unknown error"))

        # Log summary
        self.logger.info("=" * 70)
        self.logger.info("Transcription Summary")
        self.logger.info("=" * 70)
        self.logger.info(f"Total files: {results['total']}")
        self.logger.success(f"Successful: {results['successful']}")

        if results['skipped'] > 0:
            self.logger.info(f"Skipped (existing): {results['skipped']}")

            # Show first few skipped files with folder paths
            for media_file in results['skipped_files'][:5]:
                folder_name = media_file.parent.name
                self.logger.info(f"  - {folder_name}/{media_file.name}")

            if len(results['skipped_files']) > 5:
                self.logger.info(f"  ... and {len(results['skipped_files']) - 5} more")

        if results['failed'] > 0:
            self.logger.error(f"Failed: {results['failed']}")

            # Show first few errors
            for media_file, error in results['errors'][:5]:
                self.logger.error(f"  - {media_file.name}: {error}")

            if len(results['errors']) > 5:
                self.logger.error(f"  ... and {len(results['errors']) - 5} more")

        self.logger.info("=" * 70)

        return results

    def get_transcribable_files(
        self,
        directory: Path,
        recursive: bool = True
    ) -> List[Path]:
        """
        Find all transcribable media files in a directory.

        Args:
            directory: Directory to scan
            recursive: Whether to search subdirectories

        Returns:
            List of media file paths
        """
        if not directory.exists() or not directory.is_dir():
            self.logger.error(f"Invalid directory: {directory}")
            return []

        supported_formats = set(self.transcriber.get_supported_formats())
        media_files = []

        pattern = "**/*" if recursive else "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                # Skip transcription files
                if file_path.name.endswith(self.TRANSCRIPTION_SUFFIX):
                    continue

                media_files.append(file_path)

        self.logger.info(f"Found {len(media_files)} transcribable file(s) in {directory}")
        return sorted(media_files)

    def get_progress_summary(self, directory: Path) -> Dict:
        """
        Get summary of transcription progress in a directory.

        Args:
            directory: Directory to analyze

        Returns:
            Dictionary with progress statistics
        """
        transcribable_files = self.get_transcribable_files(directory)

        transcribed = 0
        pending = 0

        for media_file in transcribable_files:
            if self.is_transcribed(media_file):
                transcribed += 1
            else:
                pending += 1

        return {
            'total': len(transcribable_files),
            'transcribed': transcribed,
            'pending': pending,
            'progress_percent': (transcribed / len(transcribable_files) * 100) if transcribable_files else 0
        }

    def cleanup_empty_transcriptions(self, directory: Path) -> int:
        """
        Remove empty or invalid transcription files.

        Args:
            directory: Directory to clean

        Returns:
            Number of files removed
        """
        removed = 0

        for file_path in directory.rglob(f"*{self.TRANSCRIPTION_SUFFIX}"):
            if file_path.is_file():
                # Check if empty or very small
                if file_path.stat().st_size < 10:  # Less than 10 bytes
                    self.logger.debug_msg(f"Removing empty transcription: {file_path.name}")
                    file_path.unlink()
                    removed += 1

        if removed > 0:
            self.logger.info(f"Removed {removed} empty transcription file(s)")

        return removed
