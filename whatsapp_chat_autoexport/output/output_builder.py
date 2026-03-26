"""
Output Builder module for WhatsApp Chat Auto-Export.

Creates organized output structure with transcripts, media, and transcriptions.

Supports two output formats:
- ``"legacy"`` (default): original transcript.txt with plain-text header
- ``"v2"``: spec-conformant transcript.md + index.md companion notes
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Callable
from datetime import datetime

from ..processing.transcript_parser import TranscriptParser, Message, MediaReference
from ..utils.logger import Logger
from .spec_formatter import SpecFormatter
from .index_builder import IndexBuilder


class OutputBuilder:
    """
    Builds organized output structure for WhatsApp chat exports.

    Creates (legacy mode):
    - destination/Contact Name/transcript.txt (merged conversation)
    - destination/Contact Name/media/ (all media files)
    - destination/Contact Name/transcriptions/ (audio/video transcriptions)

    Creates (v2 mode):
    - destination/Contact Name/transcript.md (spec-conformant transcript)
    - destination/Contact Name/index.md (companion note with frontmatter)
    - destination/Contact Name/media/ (all media files)
    - destination/Contact Name/transcriptions/ (audio/video transcriptions)
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
        format_version: str = "legacy",
    ):
        """
        Initialize output builder.

        Args:
            logger: Optional logger for output
            format_version: ``"legacy"`` (default) or ``"v2"``
        """
        if format_version not in ("legacy", "v2"):
            raise ValueError(f"Unsupported format_version: {format_version!r} (expected 'legacy' or 'v2')")
        self.logger = logger or Logger()
        self.parser = TranscriptParser(logger=logger)
        self.format_version = format_version
        self._spec_formatter = SpecFormatter()
        self._index_builder = IndexBuilder()

    def build_output(
        self,
        transcript_path: Path,
        media_dir: Path,
        dest_dir: Path,
        contact_name: Optional[str] = None,
        include_transcriptions: bool = True,
        copy_media: bool = True,
        format_version: Optional[str] = None,
        chat_jid: Optional[str] = None,
    ) -> Dict:
        """
        Build complete output structure for a chat.

        Args:
            transcript_path: Path to WhatsApp transcript (.txt file)
            media_dir: Directory containing media files
            dest_dir: Destination directory for output
            contact_name: Contact name (extracted from transcript filename if None)
            include_transcriptions: Include audio/video transcriptions in output
            copy_media: Copy media files to output (if False, only transcript is created)
            format_version: Override instance-level format_version for this call.
                            ``"legacy"`` or ``"v2"``.  ``None`` uses instance default.
            chat_jid: WhatsApp JID for the chat (required for v2 format; defaults
                      to ``"unknown@s.whatsapp.net"`` if omitted).

        Returns:
            Dictionary with output paths and statistics
        """
        effective_format = format_version or self.format_version

        # Extract contact name from transcript filename if not provided
        if not contact_name:
            contact_name = self._extract_contact_name(transcript_path)

        self.logger.info("=" * 70)
        self.logger.info(f"Building output for: {contact_name}")
        self.logger.info("=" * 70)

        # Create output directory structure
        contact_dir = dest_dir / contact_name
        media_out_dir = contact_dir / "media"
        transcriptions_out_dir = contact_dir / "transcriptions"

        contact_dir.mkdir(parents=True, exist_ok=True)

        if copy_media:
            media_out_dir.mkdir(exist_ok=True)

        if include_transcriptions:
            transcriptions_out_dir.mkdir(exist_ok=True)

        # Parse transcript
        self.logger.info(f"Parsing transcript: {transcript_path.name}")
        messages, media_refs = self.parser.parse_transcript(transcript_path)

        # -----------------------------------------------------------------
        # Build transcript (format-dependent)
        # -----------------------------------------------------------------
        if effective_format == "v2":
            transcript_out_path = self._build_v2_transcript(
                messages=messages,
                contact_dir=contact_dir,
                contact_name=contact_name,
                chat_jid=chat_jid or "unknown@s.whatsapp.net",
            )
        else:
            # Legacy path — completely unchanged
            transcript_out_path = contact_dir / "transcript.txt"
            self._build_merged_transcript(
                messages,
                media_refs,
                transcript_out_path,
                contact_name,
                include_transcriptions,
                transcriptions_out_dir if include_transcriptions else None,
                media_dir  # Pass source media_dir to read transcriptions from
            )

        # Copy media files and/or transcriptions
        copied_media = []
        copied_transcriptions = []

        # Correlate media references with actual files (needed for both media and transcriptions)
        correlation_list = self.parser.correlate_media_files(
            media_refs,
            media_dir,
            time_tolerance_seconds=86400  # 24 hours tolerance
        )

        if copy_media:
            # Copy media files
            copied_media = self._copy_media_files(
                correlation_list,
                media_dir,
                media_out_dir
            )

        # Copy transcriptions if requested (independent of media copying)
        if include_transcriptions:
            # Get list of media files (either copied ones or correlated ones)
            if copy_media:
                media_file_list = copied_media
            else:
                # When not copying media, get the list from correlated files
                # correlation_list is List[Tuple[MediaReference, Optional[Path]]]
                media_file_list = [file_path
                                   for ref, file_path in correlation_list
                                   if file_path is not None]

            copied_transcriptions = self._copy_transcriptions(
                media_file_list,
                media_dir,
                transcriptions_out_dir
            )

        # Generate summary
        summary = {
            'contact_name': contact_name,
            'output_dir': contact_dir,
            'transcript_path': transcript_out_path,
            'total_messages': len(messages),
            'media_messages': len(media_refs),
            'media_copied': len(copied_media),
            'transcriptions_copied': len(copied_transcriptions),
            'format_version': effective_format,
        }

        self.logger.info("=" * 70)
        self.logger.success(f"Output created: {contact_dir}")
        self.logger.info(f"  Messages: {summary['total_messages']}")
        self.logger.info(f"  Media references: {summary['media_messages']}")
        if copy_media:
            self.logger.info(f"  Media files copied: {summary['media_copied']}")
        if include_transcriptions:
            self.logger.info(f"  Transcriptions copied: {summary['transcriptions_copied']}")
        self.logger.info("=" * 70)

        return summary

    def _extract_contact_name(self, transcript_path: Path) -> str:
        """
        Extract contact name from transcript filename.

        Args:
            transcript_path: Path to transcript file

        Returns:
            Contact name
        """
        filename = transcript_path.stem  # Remove .txt extension

        # Remove "WhatsApp Chat with " prefix if present
        if filename.startswith("WhatsApp Chat with "):
            return filename.replace("WhatsApp Chat with ", "")

        return filename

    def _build_merged_transcript(
        self,
        messages: List[Message],
        media_refs: List[MediaReference],
        output_path: Path,
        contact_name: str,
        include_transcriptions: bool,
        transcriptions_dir: Optional[Path],
        source_media_dir: Optional[Path] = None
    ):
        """
        Build merged transcript with transcription references.

        Args:
            messages: List of parsed messages
            media_refs: List of media references
            output_path: Path to save merged transcript
            contact_name: Contact name
            include_transcriptions: Whether to include transcription references
            transcriptions_dir: Directory where transcriptions will be saved
            source_media_dir: Source directory containing original media and transcription files
        """
        self.logger.info(f"Building merged transcript: {output_path.name}")

        # Create media reference lookup by line number
        media_by_line = {ref.line_number: ref for ref in media_refs}

        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write(f"# WhatsApp Chat with {contact_name}\n")
            f.write(f"# Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Total messages: {len(messages)}\n")
            f.write(f"# Media messages: {len(media_refs)}\n")
            f.write("\n")

            # Write messages
            for msg in messages:
                # Format timestamp
                timestamp_str = msg.timestamp.strftime('%d/%m/%Y, %H:%M')

                # Write message
                f.write(f"{timestamp_str} - {msg.sender}: {msg.content}\n")

                # If this is a media message with transcription, add reference
                if include_transcriptions and msg.is_media and msg.media_type in ['audio', 'video']:
                    # Try to find corresponding transcription
                    # Extract filename from content if present
                    transcription_ref = self._format_transcription_reference(
                        msg.content,
                        msg.media_type
                    )
                    if transcription_ref:
                        # Look for transcription in source directory first (they haven't been copied yet)
                        transcription_text = None

                        if source_media_dir:
                            source_transcription_file = source_media_dir / transcription_ref
                            transcription_text = self._read_transcription_text(source_transcription_file)

                        # Fallback to output directory (for backward compatibility)
                        if not transcription_text and transcriptions_dir:
                            output_transcription_file = transcriptions_dir / transcription_ref
                            transcription_text = self._read_transcription_text(output_transcription_file)

                        if transcription_text:
                            # Write inline transcription
                            f.write(f"  [Transcription]: {transcription_text}\n")

                            # Write the file reference if transcriptions_dir exists
                            if transcriptions_dir:
                                f.write(f"  → Transcription file: transcriptions/{transcription_ref}\n")

        self.logger.success(f"Merged transcript created: {output_path.name}")

    # ------------------------------------------------------------------
    # V2 format helpers
    # ------------------------------------------------------------------

    def _build_v2_transcript(
        self,
        messages: List[Message],
        contact_dir: Path,
        contact_name: str,
        chat_jid: str,
    ) -> Path:
        """
        Build v2 spec-conformant transcript.md + index.md using atomic writes.

        Args:
            messages: Parsed message list.
            contact_dir: Output directory for this contact.
            contact_name: Display name.
            chat_jid: WhatsApp JID.

        Returns:
            Path to the written transcript.md file.
        """
        transcript_path = contact_dir / "transcript.md"
        index_path = contact_dir / "index.md"

        # Format content via delegates
        transcript_content = self._spec_formatter.format_transcript(
            messages=messages,
            chat_jid=chat_jid,
            contact_name=contact_name,
        )
        index_content = self._index_builder.build_index(
            messages=messages,
            chat_jid=chat_jid,
            contact_name=contact_name,
        )

        # Atomic writes: write to .tmp, then rename
        self._atomic_write(transcript_path, transcript_content)
        self._atomic_write(index_path, index_content)

        self.logger.success(f"V2 transcript created: {transcript_path.name}")
        self.logger.success(f"V2 index created: {index_path.name}")

        return transcript_path

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        """
        Write *content* to *target* atomically.

        Strategy: write to ``<target>.tmp``, then ``os.replace`` so the
        operation is atomic on POSIX (and best-effort on Windows).  If the
        write or rename fails, the original file (if any) is preserved and
        the temp file is cleaned up.
        """
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(str(tmp_path), str(target))
        except Exception:
            # Clean up temp file on failure; preserve original
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def _format_transcription_reference(self, content: str, media_type: str) -> Optional[str]:
        """
        Format transcription reference from media message content.

        Args:
            content: Message content
            media_type: Type of media

        Returns:
            Transcription filename or None
        """
        # If content has filename (e.g., "AUD-20250711-WA0007.aac (file attached)")
        if "(file attached)" in content:
            filename = content.replace("(file attached)", "").strip()
            # Remove extension and add _transcription.txt
            base_name = Path(filename).stem
            return f"{base_name}_transcription.txt"

        # For generic media references
        return None

    def _read_transcription_text(self, transcription_file: Path) -> Optional[str]:
        """
        Read transcription text from file, skipping metadata headers.

        Args:
            transcription_file: Path to transcription file

        Returns:
            Transcription text content or None if file doesn't exist/can't be read
        """
        try:
            if not transcription_file.exists():
                return None
            
            with open(transcription_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Extract text, skipping metadata lines (starting with #)
            text_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip metadata headers and empty lines
                if stripped and not stripped.startswith('#'):
                    text_lines.append(stripped)
            
            # Join all text lines with space
            transcription_text = ' '.join(text_lines)
            
            return transcription_text if transcription_text else None
            
        except Exception as e:
            self.logger.debug(f"Could not read transcription file {transcription_file.name}: {e}")
            return None

    def _copy_media_files(
        self,
        correlation_list: List[Tuple[MediaReference, Optional[Path]]],
        source_dir: Path,
        dest_dir: Path
    ) -> List[Path]:
        """
        Copy media files to destination.
        
        Uses skip-if-exists strategy: if a file with the same name already exists
        in the destination, it is skipped (not overwritten).

        Args:
            correlation_list: List of (MediaReference, file_path) tuples
            source_dir: Source directory
            dest_dir: Destination directory

        Returns:
            List of copied file paths
        """
        self.logger.info(f"Copying media files to: {dest_dir}")

        copied_files = []
        skipped_count = 0

        for ref, file_path in correlation_list:
            if file_path is None:
                continue

            # Destination path
            dest_path = dest_dir / file_path.name

            # Skip if already exists (by name)
            if dest_path.exists():
                self.logger.debug_msg(f"Skipping (exists): {file_path.name}")
                copied_files.append(dest_path)
                skipped_count += 1
                continue

            # Copy file
            try:
                shutil.copy2(file_path, dest_path)
                copied_files.append(dest_path)
                self.logger.debug_msg(f"Copied: {file_path.name}")
            except Exception as e:
                self.logger.error(f"Failed to copy {file_path.name}: {e}")

        if skipped_count > 0:
            self.logger.info(f"Skipped {skipped_count} existing file(s)")
        self.logger.success(f"Copied {len(copied_files) - skipped_count} new media file(s)")
        return copied_files

    def _copy_transcriptions(
        self,
        media_files: List[Path],
        source_dir: Path,
        dest_dir: Path
    ) -> List[Path]:
        """
        Copy transcription files for media files.
        
        Uses skip-if-exists strategy: if a transcription file with the same name
        already exists in the destination, it is skipped (not overwritten).

        Args:
            media_files: List of media file paths
            source_dir: Source directory containing transcriptions
            dest_dir: Destination directory for transcriptions

        Returns:
            List of copied transcription paths
        """
        self.logger.info(f"Copying transcriptions to: {dest_dir}")

        copied_transcriptions = []
        skipped_count = 0
        transcription_suffix = "_transcription.txt"

        for media_file in media_files:
            # Look for transcription file in source directory
            transcription_name = f"{media_file.stem}{transcription_suffix}"
            source_transcription = source_dir / transcription_name

            if not source_transcription.exists():
                # Try in same directory as media file (might have been moved)
                source_transcription = media_file.parent / transcription_name

            if not source_transcription.exists():
                continue

            # Destination path
            dest_transcription = dest_dir / transcription_name

            # Skip if already exists (by name)
            if dest_transcription.exists():
                self.logger.debug_msg(f"Skipping (exists): {transcription_name}")
                copied_transcriptions.append(dest_transcription)
                skipped_count += 1
                continue

            # Copy transcription
            try:
                shutil.copy2(source_transcription, dest_transcription)
                copied_transcriptions.append(dest_transcription)
                self.logger.debug_msg(f"Copied: {transcription_name}")
            except Exception as e:
                self.logger.error(f"Failed to copy {transcription_name}: {e}")

        if skipped_count > 0:
            self.logger.info(f"Skipped {skipped_count} existing transcription(s)")
        self.logger.success(f"Copied {len(copied_transcriptions) - skipped_count} new transcription(s)")
        return copied_transcriptions

    def batch_build_outputs(
        self,
        transcript_files: List[Tuple[Path, Path]],
        dest_dir: Path,
        include_transcriptions: bool = True,
        copy_media: bool = True,
        on_progress: Optional[Callable] = None,
        format_version: Optional[str] = None,
    ) -> List[Dict]:
        """
        Build outputs for multiple chats.

        Args:
            transcript_files: List of (transcript_path, media_dir) tuples
            dest_dir: Destination directory for all outputs
            include_transcriptions: Include audio/video transcriptions
            copy_media: Copy media files
            on_progress: Optional callback for progress updates.
                         Signature: on_progress(phase, message, current, total, item_name="")
            format_version: Override instance-level format_version.
                            ``"legacy"`` or ``"v2"``.  ``None`` uses instance default.

        Returns:
            List of summary dictionaries
        """
        self.logger.info(f"Building outputs for {len(transcript_files)} chat(s)")

        results = []
        total = len(transcript_files)

        for i, (transcript_path, media_dir) in enumerate(transcript_files, 1):
            self.logger.info(f"\n[{i}/{total}] Processing: {transcript_path.name}")

            try:
                summary = self.build_output(
                    transcript_path,
                    media_dir,
                    dest_dir,
                    include_transcriptions=include_transcriptions,
                    copy_media=copy_media,
                    format_version=format_version,
                )
                results.append(summary)
            except Exception as e:
                self.logger.error(f"Failed to build output for {transcript_path.name}: {e}")
                import traceback
                traceback.print_exc()

            if on_progress:
                try:
                    on_progress("build_output", f"Built output for {transcript_path.stem}", i, total, transcript_path.stem)
                except Exception:
                    pass  # Never let callback errors crash output building

        # Overall summary
        total_messages = sum(r['total_messages'] for r in results)
        total_media = sum(r['media_copied'] for r in results)
        total_transcriptions = sum(r['transcriptions_copied'] for r in results)

        self.logger.info("\n" + "=" * 70)
        self.logger.info("Batch Build Summary")
        self.logger.info("=" * 70)
        self.logger.info(f"Chats processed: {len(results)}/{len(transcript_files)}")
        self.logger.info(f"Total messages: {total_messages}")
        self.logger.info(f"Total media files: {total_media}")
        if include_transcriptions:
            self.logger.info(f"Total transcriptions: {total_transcriptions}")
        self.logger.info("=" * 70)

        return results

    def verify_output(self, contact_dir: Path) -> Dict:
        """
        Verify output structure is correct.

        Args:
            contact_dir: Contact output directory

        Returns:
            Dictionary with verification results
        """
        results = {
            'contact_dir_exists': contact_dir.exists(),
            'transcript_exists': False,
            'media_dir_exists': False,
            'transcriptions_dir_exists': False,
            'media_count': 0,
            'transcriptions_count': 0,
            'valid': False
        }

        if not contact_dir.exists():
            return results

        # Check transcript
        transcript_path = contact_dir / "transcript.txt"
        results['transcript_exists'] = transcript_path.exists()

        # Check media directory
        media_dir = contact_dir / "media"
        results['media_dir_exists'] = media_dir.exists()
        if media_dir.exists():
            results['media_count'] = len(list(media_dir.iterdir()))

        # Check transcriptions directory
        transcriptions_dir = contact_dir / "transcriptions"
        results['transcriptions_dir_exists'] = transcriptions_dir.exists()
        if transcriptions_dir.exists():
            results['transcriptions_count'] = len(list(transcriptions_dir.iterdir()))

        # Valid if at least transcript exists
        results['valid'] = results['transcript_exists']

        return results
