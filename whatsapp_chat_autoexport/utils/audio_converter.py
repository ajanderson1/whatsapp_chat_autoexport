"""
Audio conversion utilities using FFmpeg.

Handles conversion of audio formats not supported by transcription APIs
(e.g., Opus) to supported formats (e.g., M4A/AAC).

Also handles extraction of audio from WhatsApp video messages for transcription.
"""

import subprocess
import shutil
import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from .logger import Logger


class ExtractionErrorCode(Enum):
    """Error codes for audio extraction failures."""
    SUCCESS = "success"
    FFMPEG_NOT_AVAILABLE = "ffmpeg_not_available"
    FILE_NOT_FOUND = "file_not_found"
    NO_AUDIO_STREAM = "no_audio_stream"
    FFMPEG_EXTRACTION_FAILED = "ffmpeg_extraction_failed"
    OUTPUT_FILE_MISSING = "output_file_missing"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ExtractionResult:
    """Result of audio extraction from video."""
    success: bool
    output_path: Optional[Path] = None
    error_code: ExtractionErrorCode = ExtractionErrorCode.SUCCESS
    error_message: str = ""
    ffmpeg_stderr: str = ""
    video_info: dict = field(default_factory=dict)

    @property
    def user_friendly_message(self) -> str:
        """Get a user-friendly error message based on the error code."""
        messages = {
            ExtractionErrorCode.SUCCESS: "Audio extracted successfully",
            ExtractionErrorCode.FFMPEG_NOT_AVAILABLE: "FFmpeg is not installed. Install with: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)",
            ExtractionErrorCode.FILE_NOT_FOUND: f"Video file not found: {self.error_message}",
            ExtractionErrorCode.NO_AUDIO_STREAM: "Video has no audio track. This is a silent video - nothing to transcribe.",
            ExtractionErrorCode.FFMPEG_EXTRACTION_FAILED: f"FFmpeg failed to extract audio: {self.error_message}",
            ExtractionErrorCode.OUTPUT_FILE_MISSING: "Audio extraction appeared to succeed but output file was not created",
            ExtractionErrorCode.TIMEOUT: "Audio extraction timed out after 120 seconds (video may be too long or corrupted)",
            ExtractionErrorCode.UNKNOWN_ERROR: f"Unexpected error during extraction: {self.error_message}",
        }
        return messages.get(self.error_code, self.error_message)


# WhatsApp video message filename pattern: VID-YYYYMMDD-WA####.mp4
WHATSAPP_VIDEO_PATTERN = re.compile(r'^VID-\d{8}-WA\d+\.mp4$', re.IGNORECASE)


def is_whatsapp_video_message(filename: str) -> bool:
    """
    Check if a filename matches the WhatsApp video message pattern.

    WhatsApp video messages follow the pattern: VID-YYYYMMDD-WA####.mp4
    - VID: Video file prefix
    - YYYYMMDD: Date (year, month, day)
    - WA: WhatsApp identifier
    - ####: Sequential number (e.g., 0000, 0001)

    Examples:
        - VID-20251004-WA0011.mp4 -> True
        - VID-20231115-WA0000.mp4 -> True
        - video.mp4 -> False
        - movie.avi -> False

    Args:
        filename: The filename to check (not the full path)

    Returns:
        True if the filename matches the WhatsApp video message pattern
    """
    return bool(WHATSAPP_VIDEO_PATTERN.match(filename))


class AudioConverter:
    """
    Audio format converter using FFmpeg.

    Primarily used to convert Opus format (WhatsApp voice messages) to M4A
    for compatibility with OpenAI Whisper API and ElevenLabs Speech-to-Text.
    """

    def __init__(self, logger: Optional[Logger] = None, debug_dir: Optional[Path] = None):
        """
        Initialize the audio converter.

        Args:
            logger: Logger instance for output
            debug_dir: Optional directory to save failed files for debugging
        """
        self.logger = logger or Logger()
        self.debug_dir = debug_dir
        self._ffmpeg_available = None

    def is_ffmpeg_available(self) -> bool:
        """
        Check if FFmpeg is installed and available.

        Returns:
            True if FFmpeg is available, False otherwise
        """
        if self._ffmpeg_available is not None:
            return self._ffmpeg_available

        self._ffmpeg_available = shutil.which('ffmpeg') is not None

        if not self._ffmpeg_available:
            self.logger.warning("FFmpeg is not installed or not in PATH")
            self.logger.info("Install FFmpeg to enable Opus file transcription:")
            self.logger.info("  macOS: brew install ffmpeg")
            self.logger.info("  Ubuntu/Debian: sudo apt install ffmpeg")
            self.logger.info("  Windows: Download from https://ffmpeg.org/download.html")

        return self._ffmpeg_available

    def convert_to_m4a(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        overwrite: bool = False
    ) -> Optional[Path]:
        """
        Convert audio file to M4A/AAC format.

        Args:
            input_path: Path to input audio file
            output_path: Path for output M4A file (default: same name with .m4a extension)
            overwrite: Whether to overwrite existing output file

        Returns:
            Path to converted M4A file if successful, None otherwise
        """
        if not self.is_ffmpeg_available():
            self.logger.error("Cannot convert audio: FFmpeg not available")
            return None

        if not input_path.exists():
            self.logger.error(f"Input file not found: {input_path}")
            return None

        # Default output path
        if output_path is None:
            output_path = input_path.with_suffix('.m4a')

        # Check if output already exists
        if output_path.exists() and not overwrite:
            self.logger.debug_msg(f"Output file already exists: {output_path}")
            return output_path

        try:
            self.logger.debug_msg(f"Converting {input_path.name} to M4A...")

            # FFmpeg command:
            # -i: input file
            # -vn: no video
            # -c:a aac: use AAC audio codec
            # -b:a 128k: audio bitrate 128 kbps (good quality, reasonable size)
            # -y: overwrite output file if exists
            # -loglevel error: only show errors
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-vn',  # No video
                '-c:a', 'aac',  # AAC codec for M4A
                '-b:a', '128k',  # 128 kbps bitrate (good quality)
                '-loglevel', 'error',  # Only show errors
            ]

            if overwrite:
                cmd.append('-y')

            cmd.append(str(output_path))

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 60 second timeout
            )

            if result.returncode != 0:
                self.logger.error(f"FFmpeg conversion failed: {result.stderr}")
                return None

            if not output_path.exists():
                self.logger.error("Conversion appeared to succeed but output file not found")
                return None

            # Log success
            input_size_mb = input_path.stat().st_size / (1024 * 1024)
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            self.logger.debug_msg(
                f"Converted {input_path.name} ({input_size_mb:.2f} MB) "
                f"to {output_path.name} ({output_size_mb:.2f} MB)"
            )

            return output_path

        except subprocess.TimeoutExpired:
            self.logger.error(f"FFmpeg conversion timed out after 60s")
            return None
        except Exception as e:
            self.logger.error(f"Error during audio conversion: {e}")
            return None

    def convert_opus_to_m4a(
        self,
        opus_file: Path,
        temp_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Convert Opus file to M4A (convenience method).

        This is a specialized wrapper for converting WhatsApp Opus voice messages
        to M4A format for transcription API compatibility.

        Args:
            opus_file: Path to Opus file
            temp_dir: Directory for temporary M4A file (default: same as opus_file)

        Returns:
            Path to temporary M4A file if successful, None otherwise
        """
        if opus_file.suffix.lower() != '.opus':
            self.logger.warning(f"File is not Opus format: {opus_file}")
            return None

        # Create temp M4A path
        if temp_dir:
            temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = temp_dir / f"{opus_file.stem}.m4a"
        else:
            output_path = opus_file.with_suffix('.m4a')

        return self.convert_to_m4a(opus_file, output_path, overwrite=True)

    def _has_audio_stream(self, video_file: Path) -> bool:
        """
        Check if a video file contains an audio stream.

        Uses ffprobe to analyze the video file and detect audio streams.

        Args:
            video_file: Path to video file

        Returns:
            True if the video has an audio stream, False otherwise
        """
        if not self.is_ffmpeg_available():
            # If ffprobe unavailable, assume audio exists and let extraction fail gracefully
            return True

        try:
            # Use ffprobe to check for audio streams
            # -v quiet: suppress output
            # -select_streams a: select only audio streams
            # -show_entries stream=codec_type: show codec type
            # -of csv=p=0: output in CSV format without headers
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'a',
                '-show_entries', 'stream=codec_type',
                '-of', 'csv=p=0',
                str(video_file)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )

            # If ffprobe returns "audio" for any stream, the video has audio
            return 'audio' in result.stdout.lower()

        except subprocess.TimeoutExpired:
            self.logger.debug_msg(f"Timeout checking audio stream in {video_file.name}")
            # Assume audio exists on timeout, let extraction handle it
            return True
        except Exception as e:
            self.logger.debug_msg(f"Error checking audio stream: {e}")
            # Assume audio exists on error, let extraction handle it
            return True

    def _get_video_info(self, video_file: Path) -> dict:
        """
        Get detailed information about a video file using ffprobe.

        Args:
            video_file: Path to video file

        Returns:
            Dict with video info (duration, streams, codec, etc.) or empty dict
        """
        if not self.is_ffmpeg_available():
            return {}

        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(video_file)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return {"error": result.stderr}

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            return {"error": "ffprobe timed out"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid ffprobe JSON output: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _save_debug_file(
        self,
        video_file: Path,
        result: 'ExtractionResult',
        contact_name: Optional[str] = None
    ) -> Optional[Path]:
        """
        Save a failed video file to the debug directory for inspection.

        Creates a subfolder with the video copy and a metadata JSON file
        containing details about why extraction failed.

        Args:
            video_file: Path to the original video file
            result: ExtractionResult with failure details
            contact_name: Optional contact name for organization

        Returns:
            Path to the debug folder if saved, None if debug is disabled
        """
        if not self.debug_dir:
            return None

        try:
            # Create debug subfolder: debug/failed_videos/[contact]/
            failed_videos_dir = self.debug_dir / "failed_videos"
            if contact_name:
                target_dir = failed_videos_dir / contact_name
            else:
                target_dir = failed_videos_dir

            target_dir.mkdir(parents=True, exist_ok=True)

            # Copy the video file
            target_video = target_dir / video_file.name
            if not target_video.exists():
                shutil.copy2(video_file, target_video)
                self.logger.debug_msg(f"Copied failed video to debug folder: {target_video}")

            # Create metadata file
            metadata = {
                "original_path": str(video_file),
                "filename": video_file.name,
                "file_size_bytes": video_file.stat().st_size,
                "file_size_mb": round(video_file.stat().st_size / (1024 * 1024), 2),
                "error_code": result.error_code.value,
                "error_message": result.error_message,
                "user_friendly_message": result.user_friendly_message,
                "ffmpeg_stderr": result.ffmpeg_stderr,
                "video_info": result.video_info,
                "timestamp": datetime.now().isoformat(),
            }

            metadata_file = target_dir / f"{video_file.stem}_debug_info.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)

            self.logger.debug_msg(f"Saved debug metadata: {metadata_file}")

            return target_dir

        except Exception as e:
            self.logger.debug_msg(f"Could not save debug file: {e}")
            return None

    def extract_audio_from_video_detailed(
        self,
        video_file: Path,
        temp_dir: Optional[Path] = None,
        contact_name: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract audio track from a video file to M4A format with detailed error reporting.

        This is used to extract audio from WhatsApp video messages
        for transcription API compatibility. Returns detailed information
        about any failures to help with debugging.

        Args:
            video_file: Path to video file (typically MP4)
            temp_dir: Directory for temporary M4A file (default: same as video_file)
            contact_name: Optional contact name (used for organizing debug files)

        Returns:
            ExtractionResult with success status, output path, and detailed error info
        """
        # Check FFmpeg availability
        if not self.is_ffmpeg_available():
            result = ExtractionResult(
                success=False,
                error_code=ExtractionErrorCode.FFMPEG_NOT_AVAILABLE,
                error_message="FFmpeg not installed"
            )
            self.logger.error(result.user_friendly_message)
            return result

        # Check file exists
        if not video_file.exists():
            result = ExtractionResult(
                success=False,
                error_code=ExtractionErrorCode.FILE_NOT_FOUND,
                error_message=str(video_file)
            )
            self.logger.error(result.user_friendly_message)
            return result

        # Get video info for debugging
        video_info = self._get_video_info(video_file)

        # Check if video has an audio stream
        if not self._has_audio_stream(video_file):
            result = ExtractionResult(
                success=False,
                error_code=ExtractionErrorCode.NO_AUDIO_STREAM,
                error_message=video_file.name,
                video_info=video_info
            )
            self.logger.warning(f"🔇 {video_file.name}: {result.user_friendly_message}")
            # Save debug file if debug_dir is set
            self._save_debug_file(video_file, result, contact_name)
            return result

        # Create temp M4A path
        if temp_dir:
            temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = temp_dir / f"{video_file.stem}_audio.m4a"
        else:
            output_path = video_file.parent / f"{video_file.stem}_audio.m4a"

        try:
            self.logger.debug_msg(f"Extracting audio from {video_file.name}...")

            # FFmpeg command to extract audio
            cmd = [
                'ffmpeg',
                '-i', str(video_file),
                '-vn',  # No video
                '-c:a', 'aac',  # AAC codec for M4A
                '-b:a', '128k',  # 128 kbps bitrate
                '-loglevel', 'error',  # Only show errors
                '-y',  # Overwrite
                str(output_path)
            ]

            # Run FFmpeg
            proc_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for video processing
            )

            if proc_result.returncode != 0:
                result = ExtractionResult(
                    success=False,
                    error_code=ExtractionErrorCode.FFMPEG_EXTRACTION_FAILED,
                    error_message=proc_result.stderr.strip() if proc_result.stderr else "Unknown FFmpeg error",
                    ffmpeg_stderr=proc_result.stderr,
                    video_info=video_info
                )
                self.logger.error(f"FFmpeg audio extraction failed: {proc_result.stderr}")
                self._save_debug_file(video_file, result, contact_name)
                return result

            if not output_path.exists():
                result = ExtractionResult(
                    success=False,
                    error_code=ExtractionErrorCode.OUTPUT_FILE_MISSING,
                    error_message="Output file not created",
                    video_info=video_info
                )
                self.logger.error(result.user_friendly_message)
                self._save_debug_file(video_file, result, contact_name)
                return result

            # Success!
            video_size_mb = video_file.stat().st_size / (1024 * 1024)
            audio_size_mb = output_path.stat().st_size / (1024 * 1024)
            self.logger.debug_msg(
                f"Extracted audio from {video_file.name} ({video_size_mb:.2f} MB) "
                f"to {output_path.name} ({audio_size_mb:.2f} MB)"
            )

            return ExtractionResult(
                success=True,
                output_path=output_path,
                video_info=video_info
            )

        except subprocess.TimeoutExpired:
            result = ExtractionResult(
                success=False,
                error_code=ExtractionErrorCode.TIMEOUT,
                error_message="120 seconds",
                video_info=video_info
            )
            self.logger.error(result.user_friendly_message)
            self._save_debug_file(video_file, result, contact_name)
            return result
        except Exception as e:
            result = ExtractionResult(
                success=False,
                error_code=ExtractionErrorCode.UNKNOWN_ERROR,
                error_message=str(e),
                video_info=video_info
            )
            self.logger.error(f"Error during audio extraction: {e}")
            self._save_debug_file(video_file, result, contact_name)
            return result

    def extract_audio_from_video(
        self,
        video_file: Path,
        temp_dir: Optional[Path] = None,
        contact_name: Optional[str] = None
    ) -> Optional[Path]:
        """
        Extract audio track from a video file to M4A format.

        This is a convenience wrapper around extract_audio_from_video_detailed()
        that returns only the output path for backward compatibility.

        Args:
            video_file: Path to video file (typically MP4)
            temp_dir: Directory for temporary M4A file (default: same as video_file)
            contact_name: Optional contact name (used for organizing debug files)

        Returns:
            Path to temporary M4A file if successful, None otherwise
        """
        result = self.extract_audio_from_video_detailed(video_file, temp_dir, contact_name)
        return result.output_path if result.success else None

    def get_audio_info(self, audio_file: Path) -> Optional[dict]:
        """
        Get information about an audio file using ffprobe.

        Args:
            audio_file: Path to audio file

        Returns:
            Dict with audio info (duration, codec, bitrate, etc.) or None
        """
        if not self.is_ffmpeg_available():
            return None

        if not audio_file.exists():
            self.logger.error(f"Audio file not found: {audio_file}")
            return None

        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(audio_file)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            import json
            return json.loads(result.stdout)

        except Exception as e:
            self.logger.debug_msg(f"Could not get audio info: {e}")
            return None
