"""
Pipeline Orchestrator for WhatsApp Chat Auto-Export.

Coordinates the complete end-to-end workflow from Google Drive to organized output.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import tempfile
import shutil

from .utils.logger import Logger
from .google_drive.drive_manager import GoogleDriveManager
from .processing.archive_extractor import (
    find_whatsapp_chat_files,
    move_files_to_processed,
    add_zip_extension,
    extract_zip_files,
    organize_extracted_content
)
from .transcription import TranscriptionManager
from .transcription.transcriber_factory import TranscriberFactory
from .output import OutputBuilder


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""

    # Google Drive settings
    google_drive_folder: Optional[str] = None
    delete_from_drive: bool = False
    skip_download: bool = False
    
    # Google Drive polling settings (for waiting after phone export)
    poll_interval: int = 8  # Seconds between polls
    poll_timeout: int = 300  # Maximum wait time (5 minutes)
    created_within_seconds: int = 300  # Only consider files created within last 5 minutes

    # Processing settings
    download_dir: Optional[Path] = None
    keep_archives: bool = False

    # Transcription settings
    transcribe_audio_video: bool = True
    transcription_language: Optional[str] = None
    transcription_provider: str = 'whisper'  # 'whisper' or 'elevenlabs'
    skip_existing_transcriptions: bool = True
    convert_opus_to_m4a: bool = True  # Convert Opus files to M4A for better API compatibility

    # Output settings
    output_dir: Path = Path("~/whatsapp_exports").expanduser()
    include_media: bool = True
    include_transcriptions: bool = True

    # General settings
    cleanup_temp: bool = True
    dry_run: bool = False


class WhatsAppPipeline:
    """
    Complete end-to-end pipeline for WhatsApp chat export processing.

    Phases:
    1. Download from Google Drive (optional)
    2. Extract ZIP archives
    3. Organize files (transcripts, media)
    4. Transcribe audio/video (optional)
    5. Build final output
    6. Cleanup temporary files
    """

    def __init__(self, config: PipelineConfig, logger: Optional[Logger] = None):
        """
        Initialize pipeline.

        Args:
            config: Pipeline configuration
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or Logger()
        self.temp_dir: Optional[Path] = None

        # Initialize components
        self.drive_manager = None
        self.transcriber = None
        self.transcription_manager = None
        self.output_builder = OutputBuilder(logger=self.logger)

    def process_single_export(self, chat_name: str, google_drive_folder: Optional[str] = None) -> Dict:
        """
        Process a single chat export immediately after it's been exported to Google Drive.
        
        This method:
        1. Waits for and downloads the specific chat export from Google Drive
        2. Extracts and organizes the content
        3. Transcribes audio/video (if enabled)
        4. Builds the final organized output
        5. Deletes from Drive (if configured)
        6. Cleans up temporary files
        
        Args:
            chat_name: Name of the chat that was just exported
            google_drive_folder: Optional specific Google Drive folder (unused, for compatibility)
            
        Returns:
            Dictionary with processing results
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"Processing export: '{chat_name}'")
        self.logger.info("=" * 70)
        
        results = {
            'success': False,
            'chat_name': chat_name,
            'output_path': None,
            'phases_completed': [],
            'errors': []
        }
        
        temp_dir = None
        
        try:
            # Create temp directory for this chat's processing
            temp_dir = Path(tempfile.mkdtemp(prefix=f"whatsapp_{chat_name.replace(' ', '_')}_"))
            self.logger.debug_msg(f"Temp directory: {temp_dir}")
            
            # Phase 1: Wait for and download this specific chat from Google Drive
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 1: Wait for Export & Download from Google Drive")
            self.logger.info("-" * 70)
            
            # Initialize Google Drive manager
            self.drive_manager = GoogleDriveManager(logger=self.logger)

            if not self.drive_manager.connect():
                raise RuntimeError("Failed to connect to Google Drive")

            # Use the new polling method to wait for the export to appear
            # WhatsApp uploads files to Drive root WITHOUT .zip extension
            self.logger.info(f"Waiting for '{chat_name}' export to appear on Google Drive...")
            
            matching_file = self.drive_manager.wait_for_new_export(
                poll_interval=getattr(self.config, 'poll_interval', 8),
                timeout=getattr(self.config, 'poll_timeout', 300),
                created_within_seconds=getattr(self.config, 'created_within_seconds', 300)
            )
            
            # Download the file
            download_dir = temp_dir / "downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            
            downloaded = self.drive_manager.batch_download_exports(
                [matching_file],
                download_dir,
                delete_after=self.config.delete_from_drive
            )
            
            if not downloaded:
                raise RuntimeError(f"Failed to download export for '{chat_name}'")
            
            self.logger.success(f"Downloaded: {matching_file['name']}")
            results['phases_completed'].append('download')
            
            # Phase 2: Extract and organize
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 2: Extract and Organize")
            self.logger.info("-" * 70)
            
            transcript_files = self._phase2_extract_and_organize(download_dir)
            
            if not transcript_files:
                raise RuntimeError(f"No transcript found after extraction for '{chat_name}'")
            
            results['phases_completed'].append('extract')
            
            # Phase 3: Transcribe (optional)
            if self.config.transcribe_audio_video:
                self.logger.info("\n" + "-" * 70)
                self.logger.info("Phase 3: Transcribe Audio/Video")
                self.logger.info("-" * 70)
                
                self._phase3_transcribe(transcript_files)
                results['phases_completed'].append('transcribe')
            
            # Phase 4: Build output
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 4: Build Output")
            self.logger.info("-" * 70)
            
            outputs = self._phase4_build_outputs(transcript_files)
            
            if outputs:
                results['output_path'] = outputs[0]
                results['phases_completed'].append('build_output')
            
            # Phase 5: Cleanup
            if self.config.cleanup_temp:
                self.logger.debug_msg("Cleaning up temporary files...")
                results['phases_completed'].append('cleanup')
            
            results['success'] = True
            self.logger.success(f"\n✅ Successfully processed '{chat_name}'")
            if results['output_path']:
                self.logger.info(f"   Output: {results['output_path']}")
            
        except Exception as e:
            self.logger.error(f"Failed to process '{chat_name}': {e}")
            results['errors'].append(str(e))
            import traceback
            traceback.print_exc()
        
        finally:
            # Always cleanup temp directory
            if temp_dir and temp_dir.exists() and self.config.cleanup_temp:
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temp directory: {e}")
        
        return results

    def run(self, source_dir: Optional[Path] = None) -> Dict:
        """
        Run complete pipeline.

        Args:
            source_dir: Source directory with ZIP files (if skipping download)

        Returns:
            Dictionary with pipeline results
        """
        self.logger.info("=" * 70)
        self.logger.info("WhatsApp Chat Export Pipeline")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.warning("DRY RUN MODE - No files will be modified")

        results = {
            'success': False,
            'phases_completed': [],
            'outputs_created': [],
            'errors': []
        }

        try:
            # Create temp directory for processing
            self.temp_dir = Path(tempfile.mkdtemp(prefix="whatsapp_pipeline_"))
            self.logger.debug_msg(f"Temp directory: {self.temp_dir}")

            # Phase 1: Download from Google Drive (optional)
            if not self.config.skip_download:
                download_dir = self._phase1_download()
                results['phases_completed'].append('download')
            else:
                download_dir = source_dir or self.config.download_dir
                self.logger.info("Skipping download phase (using existing files)")

            if not download_dir:
                raise ValueError("No source directory specified")

            # Phase 2: Extract and organize
            transcript_files = self._phase2_extract_and_organize(download_dir)
            results['phases_completed'].append('extract')

            if not transcript_files:
                self.logger.warning("No WhatsApp exports found to process")
                return results

            # Phase 3: Transcribe audio/video (optional)
            if self.config.transcribe_audio_video:
                self._phase3_transcribe(transcript_files)
                results['phases_completed'].append('transcribe')

            # Phase 4: Build final outputs
            outputs = self._phase4_build_outputs(transcript_files)
            results['phases_completed'].append('build_output')
            results['outputs_created'] = outputs

            # Phase 5: Cleanup
            if self.config.cleanup_temp:
                self._phase5_cleanup()
                results['phases_completed'].append('cleanup')

            results['success'] = True

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            results['errors'].append(str(e))
            import traceback
            traceback.print_exc()

        finally:
            # Always cleanup temp directory
            if self.temp_dir and self.temp_dir.exists() and self.config.cleanup_temp:
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temp directory: {e}")

        # Print summary
        self._print_summary(results)

        return results

    def _phase1_download(self) -> Path:
        """
        Phase 1: Download exports from Google Drive.

        Returns:
            Path to download directory
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 1: Download from Google Drive")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would download from Google Drive")
            return self.temp_dir / "downloads"

        # Initialize Google Drive manager
        self.drive_manager = GoogleDriveManager(logger=self.logger)

        # Connect
        if not self.drive_manager.connect():
            raise RuntimeError("Failed to connect to Google Drive")

        # List exports
        folder_id = None
        if self.config.google_drive_folder:
            folder_id, _ = self.drive_manager.find_exports_in_folder(
                self.config.google_drive_folder
            )

        files = self.drive_manager.list_whatsapp_exports(folder_id=folder_id)

        if not files:
            self.logger.warning("No WhatsApp exports found on Google Drive")
            return self.temp_dir / "downloads"

        # Download
        download_dir = self.temp_dir / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        downloaded = self.drive_manager.batch_download_exports(
            files,
            download_dir,
            delete_after=self.config.delete_from_drive
        )

        self.logger.success(f"Downloaded {len(downloaded)} file(s)")
        return download_dir

    def _phase2_extract_and_organize(self, source_dir: Path) -> List[tuple]:
        """
        Phase 2: Extract ZIP files and organize content.

        Args:
            source_dir: Directory containing ZIP files

        Returns:
            List of (transcript_path, media_dir) tuples
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 2: Extract and Organize")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would extract and organize files")
            return []

        # Find WhatsApp chat files
        chat_files = find_whatsapp_chat_files(source_dir, self.logger)

        if not chat_files:
            self.logger.warning(f"No WhatsApp chat files found in {source_dir}")
            return []

        # Create processed folder
        processed_folder = source_dir / "WhatsApp Chats Processed"
        processed_folder.mkdir(exist_ok=True)

        # Move files to processed folder
        moved_files = move_files_to_processed(chat_files, processed_folder, self.logger)

        # Add .zip extension if needed
        zip_files = add_zip_extension(moved_files, self.logger)

        # Extract ZIP files
        extracted_folders = extract_zip_files(zip_files, self.logger)

        # Organize content (creates transcripts/ and media/ folders)
        organize_extracted_content(extracted_folders, processed_folder, self.logger)

        # Find all transcript files and their media directories
        transcripts_dir = processed_folder / "transcripts"
        media_base_dir = processed_folder / "media"
        transcript_files = []

        # Debug: List what's actually in the media directory
        if media_base_dir.exists():
            media_subdirs = [d.name for d in media_base_dir.iterdir() if d.is_dir()]
            self.logger.debug_msg(f"Media subdirectories found: {media_subdirs}")
        else:
            self.logger.warning(f"Media base directory doesn't exist: {media_base_dir}")

        if transcripts_dir.exists():
            for transcript_path in transcripts_dir.glob("*.txt"):
                # Use the full transcript filename (without extension) as chat name
                # This matches how archive_extractor organizes media: media/WhatsApp Chat with {name}/
                chat_name = transcript_path.stem
                media_dir = processed_folder / "media" / chat_name

                self.logger.debug_msg(f"Transcript: {transcript_path.name}")
                self.logger.debug_msg(f"  Chat name: {chat_name}")
                self.logger.debug_msg(f"  Media dir: {media_dir}")
                self.logger.debug_msg(f"  Media dir exists: {media_dir.exists()}")
                if media_dir.exists():
                    media_count = len(list(media_dir.iterdir()))
                    self.logger.debug_msg(f"  Media files in dir: {media_count}")

                transcript_files.append((transcript_path, media_dir))

        self.logger.success(f"Organized {len(transcript_files)} chat(s)")
        return transcript_files

    def _phase3_transcribe(self, transcript_files: List[tuple]):
        """
        Phase 3: Transcribe audio and video files.

        Args:
            transcript_files: List of (transcript_path, media_dir) tuples
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 3: Transcribe Audio/Video")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would transcribe audio/video files")
            return

        # Initialize transcription service using factory
        self.logger.info(f"Initializing {self.config.transcription_provider} transcription service...")

        try:
            self.transcriber = TranscriberFactory.create_transcriber(
                provider=self.config.transcription_provider,
                logger=self.logger,
                convert_opus=self.config.convert_opus_to_m4a
            )
        except ValueError as e:
            self.logger.error(f"Failed to create transcriber: {e}")
            self.logger.warning("Skipping transcription phase")
            return

        if not self.transcriber.is_available():
            provider_upper = self.config.transcription_provider.upper()
            env_var = 'OPENAI_API_KEY' if self.config.transcription_provider == 'whisper' else 'ELEVENLABS_API_KEY'
            self.logger.warning(f"Transcription service not available (check {env_var})")
            self.logger.warning("Skipping transcription phase")
            return

        # Import OutputBuilder to get contact name extractor
        from .output.output_builder import OutputBuilder
        output_builder = OutputBuilder(logger=self.logger)

        self.transcription_manager = TranscriptionManager(
            self.transcriber,
            logger=self.logger,
            output_dir=self.config.output_dir,
            contact_name_extractor=output_builder._extract_contact_name
        )

        # Transcribe files in each media directory
        total_transcribed = 0

        for transcript_path, media_dir in transcript_files:
            if not media_dir.exists():
                continue

            # Find transcribable files
            media_files = self.transcription_manager.get_transcribable_files(
                media_dir,
                recursive=False
            )

            if not media_files:
                continue

            self.logger.info(f"\nTranscribing {len(media_files)} file(s) for: {transcript_path.stem}")

            # Transcribe
            results = self.transcription_manager.batch_transcribe(
                media_files,
                skip_existing=self.config.skip_existing_transcriptions,
                show_progress=True,
                transcript_path=transcript_path,
                language=self.config.transcription_language
            )

            total_transcribed += results['successful']

        self.logger.success(f"Total transcriptions: {total_transcribed}")

    def _phase4_build_outputs(self, transcript_files: List[tuple]) -> List[Path]:
        """
        Phase 4: Build final organized outputs.

        Args:
            transcript_files: List of (transcript_path, media_dir) tuples

        Returns:
            List of output directory paths
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 4: Build Final Outputs")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would build final outputs")
            return []

        # Create output directory
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Build outputs
        results = self.output_builder.batch_build_outputs(
            transcript_files,
            self.config.output_dir,
            include_transcriptions=self.config.include_transcriptions,
            copy_media=self.config.include_media
        )

        output_dirs = [r['output_dir'] for r in results]

        self.logger.success(f"Created {len(output_dirs)} output(s) in: {self.config.output_dir}")
        return output_dirs

    def _phase5_cleanup(self):
        """Phase 5: Cleanup temporary files."""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Phase 5: Cleanup")
        self.logger.info("=" * 70)

        if self.config.dry_run:
            self.logger.info("[DRY RUN] Would cleanup temporary files")
            return

        # Cleanup handled in finally block
        self.logger.success("Cleanup complete")

    def _print_summary(self, results: Dict):
        """Print pipeline execution summary."""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("Pipeline Summary")
        self.logger.info("=" * 70)

        if results['success']:
            self.logger.success("Pipeline completed successfully!")
        else:
            self.logger.error("Pipeline failed")

        self.logger.info(f"Phases completed: {', '.join(results['phases_completed'])}")
        self.logger.info(f"Outputs created: {len(results['outputs_created'])}")

        if results['outputs_created']:
            for output_dir in results['outputs_created']:
                self.logger.info(f"  - {output_dir}")

        if results['errors']:
            self.logger.error(f"Errors: {len(results['errors'])}")
            for error in results['errors']:
                self.logger.error(f"  - {error}")

        self.logger.info("=" * 70)


def create_default_config() -> PipelineConfig:
    """Create default pipeline configuration."""
    return PipelineConfig(
        output_dir=Path("~/whatsapp_exports").expanduser(),
        delete_from_drive=False,
        transcribe_audio_video=True,
        cleanup_temp=True,
        dry_run=False
    )
