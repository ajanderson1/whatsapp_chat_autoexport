"""
Transcript Parser module for WhatsApp Chat Auto-Export.

Parses WhatsApp transcript files to extract messages, detect media references,
and correlate them with actual media files.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from ..utils.logger import Logger


@dataclass
class Message:
    """Represents a single WhatsApp message."""
    timestamp: datetime
    sender: str
    content: str
    is_media: bool = False
    media_type: Optional[str] = None  # 'image', 'audio', 'video', 'document', etc.
    raw_line: str = ""
    line_number: int = 0


@dataclass(frozen=True)
class MediaReference:
    """Represents a media reference in the transcript."""
    message: Message
    media_type: str
    timestamp: datetime
    sender: str
    line_number: int


class TranscriptParser:
    """Parser for WhatsApp transcript files."""

    # Common WhatsApp transcript patterns
    # Format: M/D/YY, H:MM AM/PM - Sender: Message
    # Examples:
    #   1/15/24, 10:30 AM - Alice: Hey!
    #   12/5/23, 9:05 PM - Bob: audio omitted
    TIMESTAMP_PATTERNS = [
        # US format: M/D/YY, H:MM AM/PM
        r'^(\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}\s+[AP]M)\s+-\s+([^:]+):\s*(.*)$',
        # European format: DD/MM/YYYY, HH:MM
        r'^(\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2})\s+-\s+([^:]+):\s*(.*)$',
        # ISO format: YYYY-MM-DD HH:MM:SS
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+([^:]+):\s*(.*)$',
    ]

    # Media reference patterns (case-insensitive)
    MEDIA_PATTERNS = {
        'image': [
            r'<media omitted>',
            r'image omitted',
            r'IMG-\d+',
            r'photo omitted',
            r'picture omitted',
        ],
        'audio': [
            r'audio omitted',
            r'PTT-\d+',  # Push-to-talk
            r'AUD-\d+',
            r'voice message',
        ],
        'video': [
            r'video omitted',
            r'VID-\d+',
        ],
        'document': [
            r'document omitted',
            r'DOC-\d+',
            r'PDF-\d+',
            r'\.pdf',
            r'\.docx?',
            r'\.xlsx?',
        ],
        'sticker': [
            r'sticker omitted',
            r'STK-\d+',
        ],
        'gif': [
            r'GIF omitted',
            r'\.gif',
        ],
    }

    def __init__(self, logger: Optional[Logger] = None):
        """
        Initialize the transcript parser.

        Args:
            logger: Logger instance for output
        """
        self.logger = logger or Logger()
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile all media patterns for efficient matching."""
        compiled = {}
        for media_type, patterns in self.MEDIA_PATTERNS.items():
            compiled[media_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
        return compiled

    def parse_transcript(self, transcript_path: Path) -> Tuple[List[Message], List[MediaReference]]:
        """
        Parse a WhatsApp transcript file.

        Args:
            transcript_path: Path to the transcript file

        Returns:
            Tuple of (messages, media_references)
        """
        if not transcript_path.exists():
            self.logger.error(f"Transcript file not found: {transcript_path}")
            return [], []

        if not transcript_path.is_file():
            self.logger.error(f"Path is not a file: {transcript_path}")
            return [], []

        self.logger.info(f"Parsing transcript: {transcript_path.name}")

        messages = []
        media_references = []

        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, start=1):
                line = line.rstrip('\n')

                # Skip empty lines
                if not line.strip():
                    continue

                # Try to parse as a message
                message = self._parse_message_line(line, line_num)

                if message:
                    messages.append(message)

                    # Check if this message contains media
                    if message.is_media:
                        media_ref = MediaReference(
                            message=message,
                            media_type=message.media_type or 'unknown',
                            timestamp=message.timestamp,
                            sender=message.sender,
                            line_number=line_num
                        )
                        media_references.append(media_ref)
                else:
                    # If not a valid message, it might be a continuation of the previous message
                    if messages:
                        # Append to the last message's content
                        messages[-1].content += '\n' + line

        except Exception as e:
            self.logger.error(f"Error parsing transcript: {e}")
            return [], []

        self.logger.success(f"Parsed {len(messages)} messages, found {len(media_references)} media references")
        return messages, media_references

    def _parse_message_line(self, line: str, line_num: int) -> Optional[Message]:
        """
        Parse a single line as a WhatsApp message.

        Args:
            line: Line of text to parse
            line_num: Line number in the file

        Returns:
            Message object if successfully parsed, None otherwise
        """
        # Try each timestamp pattern
        for pattern in self.TIMESTAMP_PATTERNS:
            match = re.match(pattern, line)
            if match:
                timestamp_str, sender, content = match.groups()

                # Parse timestamp
                timestamp = self._parse_timestamp(timestamp_str)
                if not timestamp:
                    continue

                # Clean up sender and content
                sender = sender.strip()
                content = content.strip()

                # Check if this is a media message
                is_media, media_type = self._detect_media(content)

                return Message(
                    timestamp=timestamp,
                    sender=sender,
                    content=content,
                    is_media=is_media,
                    media_type=media_type,
                    raw_line=line,
                    line_number=line_num
                )

        return None

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parse timestamp string into datetime object.

        Args:
            timestamp_str: Timestamp string to parse

        Returns:
            datetime object or None if parsing fails
        """
        # Common timestamp formats
        formats = [
            '%m/%d/%y, %I:%M %p',      # 1/15/24, 10:30 AM
            '%m/%d/%Y, %I:%M %p',      # 1/15/2024, 10:30 AM
            '%d/%m/%y, %H:%M',         # 15/01/24, 10:30
            '%d/%m/%Y, %H:%M',         # 15/01/2024, 10:30
            '%Y-%m-%d %H:%M:%S',       # 2024-01-15 10:30:00
            '%Y-%m-%d %H:%M',          # 2024-01-15 10:30
        ]

        for fmt in formats:
            try:
                return datetime.strptime(timestamp_str, fmt)
            except ValueError:
                continue

        # If none of the formats work, log a debug message
        self.logger.debug_msg(f"Could not parse timestamp: {timestamp_str}")
        return None

    def _detect_media(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        Detect if a message contains a media reference.

        Args:
            content: Message content to check

        Returns:
            Tuple of (is_media: bool, media_type: Optional[str])
        """
        content_lower = content.lower()

        # Check each media type
        for media_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(content):
                    return True, media_type

        return False, None

    def correlate_media_files(
        self,
        media_references: List[MediaReference],
        media_dir: Path,
        time_tolerance_seconds: int = 300
    ) -> List[Tuple[MediaReference, Optional[Path]]]:
        """
        Correlate media references in transcript with actual media files.

        Uses timestamp proximity to match transcript references with files.

        Args:
            media_references: List of media references from transcript
            media_dir: Directory containing media files
            time_tolerance_seconds: Maximum time difference for matching (default: 5 minutes)

        Returns:
            List of tuples (MediaReference, Optional[Path]) mapping references to files
        """
        if not media_dir.exists() or not media_dir.is_dir():
            self.logger.warning(f"Media directory not found: {media_dir}")
            return []

        self.logger.info(f"Correlating {len(media_references)} media references with files in {media_dir}")

        # Get all media files in directory
        media_files = self._get_media_files(media_dir)

        if not media_files:
            self.logger.warning(f"No media files found in {media_dir}")
            return []

        correlation_list = []

        for ref in media_references:
            # Find the best matching file based on:
            # 1. Media type
            # 2. Timestamp proximity
            # 3. File naming patterns

            best_match = None
            best_score = float('inf')

            for file_path in media_files:
                score = self._calculate_match_score(ref, file_path, time_tolerance_seconds)

                if score < best_score:
                    best_score = score
                    best_match = file_path

            # Only accept match if it's within tolerance
            if best_match and best_score < float('inf'):
                correlation_list.append((ref, best_match))
                self.logger.debug_msg(f"Matched {ref.media_type} from {ref.sender} -> {best_match.name}")
            else:
                correlation_list.append((ref, None))
                self.logger.debug_msg(f"No match found for {ref.media_type} from {ref.sender} at {ref.timestamp}")

        matched_count = sum(1 for _, path in correlation_list if path is not None)
        self.logger.success(f"Matched {matched_count}/{len(media_references)} media references")

        return correlation_list

    def _get_media_files(self, media_dir: Path) -> List[Path]:
        """
        Get all media files from directory.

        Args:
            media_dir: Directory to scan

        Returns:
            List of media file paths
        """
        media_extensions = {
            # Images
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic',
            # Audio
            '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus', '.amr',
            # Video
            '.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp',
            # Documents
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt',
        }

        media_files = []

        for file_path in media_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in media_extensions:
                media_files.append(file_path)

        return sorted(media_files, key=lambda p: p.stat().st_mtime)

    def _calculate_match_score(
        self,
        ref: MediaReference,
        file_path: Path,
        time_tolerance: int
    ) -> float:
        """
        Calculate match score between a media reference and a file.

        Lower score = better match. Returns infinity if no match.

        Matching strategy:
        1. First try exact filename match from transcript (e.g., "IMG-20170811-WA0013.jpg")
        2. Fall back to timestamp proximity (for files with accurate mtime)

        Args:
            ref: Media reference from transcript
            file_path: Candidate file path
            time_tolerance: Maximum time difference in seconds

        Returns:
            Match score (lower is better)
        """
        # Check media type compatibility
        if not self._is_compatible_type(ref.media_type, file_path):
            return float('inf')

        # Strategy 1: Try exact filename match from transcript content
        # Extract filename from media reference content
        # Common extensions: jpg, jpeg, png, gif, opus, aac, oga, m4a, mp4, pdf, doc, docx, xls, xlsx, ppt, pptx
        import re
        
        # First try WhatsApp-style filenames (IMG/PTT/VID/AUD-YYYYMMDD-WAXXXX.ext)
        whatsapp_pattern = r'([A-Z]{3}-\d{8}-WA\d{4}\.(jpg|jpeg|png|gif|opus|aac|oga|m4a|mp4|pdf|docx?|xlsx?|pptx?))'
        match = re.search(whatsapp_pattern, ref.message.content, re.IGNORECASE)
        
        if match:
            expected_filename = match.group(1)
            if file_path.name == expected_filename:
                # Perfect match - return score of 0
                return 0.0
        
        # Try generic filename pattern: "filename.ext (file attached)"
        # Use .+? (non-greedy any char) instead of \S+ to handle spaces in filenames
        # Examples: "null.pdf (file attached)", "Fringe 22.doc (file attached)"
        generic_pattern = r'(.+?\.(jpg|jpeg|png|gif|opus|aac|oga|m4a|mp4|pdf|docx?|xlsx?|pptx?))\s*\(file attached\)'
        match = re.search(generic_pattern, ref.message.content, re.IGNORECASE)
        
        if match:
            expected_filename = match.group(1).strip()
            if file_path.name == expected_filename:
                # Perfect match - return score of 0
                return 0.0

        # Strategy 2: Fall back to timestamp proximity
        # (This works for freshly exported files but not copied files)
        try:
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        except Exception:
            return float('inf')

        # Calculate time difference in seconds
        time_diff = abs((ref.timestamp - file_mtime).total_seconds())

        # If outside tolerance, no match
        if time_diff > time_tolerance:
            return float('inf')

        # Score is the time difference (lower is better)
        # Add 1.0 to ensure filename matches (score=0) are preferred
        return time_diff + 1.0

    def _is_compatible_type(self, media_type: str, file_path: Path) -> bool:
        """
        Check if file type is compatible with media type.

        Args:
            media_type: Media type from transcript ('image', 'audio', 'video', etc.)
            file_path: File path to check

        Returns:
            True if compatible, False otherwise
        """
        ext = file_path.suffix.lower()

        type_extensions = {
            'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic'},
            'audio': {'.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus', '.amr'},
            'video': {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.3gp'},
            'document': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'},
            'sticker': {'.webp', '.png'},
            'gif': {'.gif'},
        }

        compatible_exts = type_extensions.get(media_type, set())
        return ext in compatible_exts

    def generate_summary(
        self,
        messages: List[Message],
        media_references: List[MediaReference],
        correlation_list: Optional[List[Tuple[MediaReference, Optional[Path]]]] = None
    ) -> Dict:
        """
        Generate a summary of the parsed transcript.

        Args:
            messages: List of parsed messages
            media_references: List of media references
            correlation_list: Optional list of (reference, file) tuples

        Returns:
            Dictionary with summary statistics
        """
        # Count messages by sender
        sender_counts = {}
        for msg in messages:
            sender_counts[msg.sender] = sender_counts.get(msg.sender, 0) + 1

        # Count media by type
        media_type_counts = {}
        for ref in media_references:
            media_type_counts[ref.media_type] = media_type_counts.get(ref.media_type, 0) + 1

        # Calculate date range
        if messages:
            timestamps = [msg.timestamp for msg in messages]
            date_range = {
                'first': min(timestamps),
                'last': max(timestamps),
                'days': (max(timestamps) - min(timestamps)).days + 1
            }
        else:
            date_range = None

        # Correlation stats
        correlation_stats = None
        if correlation_list:
            matched = sum(1 for _, path in correlation_list if path is not None)
            correlation_stats = {
                'total_references': len(correlation_list),
                'matched': matched,
                'unmatched': len(correlation_list) - matched,
                'match_rate': matched / len(correlation_list) if correlation_list else 0.0
            }

        return {
            'total_messages': len(messages),
            'media_messages': len(media_references),
            'text_messages': len(messages) - len(media_references),
            'senders': list(sender_counts.keys()),
            'sender_counts': sender_counts,
            'media_type_counts': media_type_counts,
            'date_range': date_range,
            'correlation_stats': correlation_stats
        }
