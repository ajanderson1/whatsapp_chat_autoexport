"""
Audio conversion utilities using FFmpeg.

Handles conversion of audio formats not supported by transcription APIs
(e.g., Opus) to supported formats (e.g., M4A/AAC).

Also handles extraction of audio from WhatsApp video messages for transcription.
"""

import subprocess
import shutil
import re
from pathlib import Path
from typing import Optional

from .logger import Logger


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

    def __init__(self, logger: Optional[Logger] = None):
        """
        Initialize the audio converter.

        Args:
            logger: Logger instance for output
        """
        self.logger = logger or Logger()
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

    def extract_audio_from_video(
        self,
        video_file: Path,
        temp_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Extract audio track from a video file to M4A format.

        This is used to extract audio from WhatsApp video messages
        for transcription API compatibility.

        Args:
            video_file: Path to video file (typically MP4)
            temp_dir: Directory for temporary M4A file (default: same as video_file)

        Returns:
            Path to temporary M4A file if successful, None otherwise
        """
        if not self.is_ffmpeg_available():
            self.logger.error("Cannot extract audio: FFmpeg not available")
            return None

        if not video_file.exists():
            self.logger.error(f"Video file not found: {video_file}")
            return None

        # Check if video has an audio stream before attempting extraction
        if not self._has_audio_stream(video_file):
            self.logger.error(f"Video file has no audio track: {video_file.name}")
            return None

        # Create temp M4A path
        if temp_dir:
            temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = temp_dir / f"{video_file.stem}_audio.m4a"
        else:
            output_path = video_file.parent / f"{video_file.stem}_audio.m4a"

        try:
            self.logger.debug_msg(f"Extracting audio from {video_file.name}...")

            # FFmpeg command to extract audio:
            # -i: input file
            # -vn: no video (audio only)
            # -c:a aac: use AAC audio codec
            # -b:a 128k: audio bitrate 128 kbps
            # -y: overwrite output file if exists
            # -loglevel error: only show errors
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for video processing
            )

            if result.returncode != 0:
                self.logger.error(f"FFmpeg audio extraction failed: {result.stderr}")
                return None

            if not output_path.exists():
                self.logger.error("Audio extraction appeared to succeed but output file not found")
                return None

            # Log success
            video_size_mb = video_file.stat().st_size / (1024 * 1024)
            audio_size_mb = output_path.stat().st_size / (1024 * 1024)
            self.logger.debug_msg(
                f"Extracted audio from {video_file.name} ({video_size_mb:.2f} MB) "
                f"to {output_path.name} ({audio_size_mb:.2f} MB)"
            )

            return output_path

        except subprocess.TimeoutExpired:
            self.logger.error(f"FFmpeg audio extraction timed out after 120s")
            return None
        except Exception as e:
            self.logger.error(f"Error during audio extraction: {e}")
            return None

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
