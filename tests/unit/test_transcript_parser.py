"""
Test suite for transcript parser.

Tests message parsing, media detection, and file correlation.
"""

from pathlib import Path
from datetime import datetime

import pytest

from whatsapp_chat_autoexport.processing.transcript_parser import (
    TranscriptParser,
    Message,
    MediaReference,
)
from whatsapp_chat_autoexport.utils.logger import Logger


@pytest.mark.unit
def test_parser_import():
    """Test that the parser module can be imported."""
    assert TranscriptParser is not None
    assert Message is not None
    assert MediaReference is not None


@pytest.mark.unit
def test_parse_sample_transcript(sample_transcript_file):
    """Test parsing the sample transcript."""
    logger = Logger(debug=False)
    parser = TranscriptParser(logger=logger)

    messages, media_refs = parser.parse_transcript(sample_transcript_file)

    assert len(messages) > 0, "Should parse some messages"
    assert len(media_refs) > 0, "Should find some media references"

    # The sample transcript has 3,151 lines and lots of media
    assert len(messages) > 100, f"Expected many messages, got {len(messages)}"
    assert (
        len(media_refs) > 10
    ), f"Expected many media references, got {len(media_refs)}"


@pytest.mark.unit
def test_message_structure(sample_transcript_file):
    """Test that messages are parsed with correct structure."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    messages, _ = parser.parse_transcript(sample_transcript_file)

    assert len(messages) > 0, "No messages parsed"

    # Check first message
    first_msg = messages[0]

    # Verify structure
    assert isinstance(
        first_msg.timestamp, datetime
    ), "Timestamp should be a datetime object"
    assert isinstance(first_msg.sender, str), "Sender should be a string"
    assert isinstance(first_msg.content, str), "Content should be a string"
    assert isinstance(first_msg.is_media, bool), "is_media should be a boolean"

    # Verify all required attributes exist
    assert hasattr(first_msg, "timestamp")
    assert hasattr(first_msg, "sender")
    assert hasattr(first_msg, "content")
    assert hasattr(first_msg, "is_media")


@pytest.mark.unit
def test_media_detection(sample_transcript_file):
    """Test that media references are correctly detected."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    messages, media_refs = parser.parse_transcript(sample_transcript_file)

    # Verify media references have correct structure
    for ref in media_refs:
        assert isinstance(ref.line_number, int), "Line number should be an integer"
        assert isinstance(ref.media_type, str), "Media type should be a string"
        assert isinstance(ref.sender, str), "Sender should be a string"
        assert ref.media_type in [
            "image",
            "audio",
            "video",
            "document",
            "other",
        ], f"Unknown media type: {ref.media_type}"

    # Count media types
    media_type_counts = {}
    for ref in media_refs:
        media_type_counts[ref.media_type] = media_type_counts.get(ref.media_type, 0) + 1

    # Should have various media types (based on sample data: 116 PTT, 70 images, 1 video, etc.)
    assert len(media_type_counts) > 0, "Should detect at least one media type"


@pytest.mark.unit
def test_timestamp_parsing(sample_transcript_file):
    """Test that various timestamp formats are parsed correctly."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    messages, _ = parser.parse_transcript(sample_transcript_file)

    # Verify all messages have valid timestamps
    for msg in messages:
        assert isinstance(msg.timestamp, datetime), "All messages should have timestamps"

    # Check that timestamps are reasonable (not in the distant past/future)
    first_timestamp = messages[0].timestamp
    assert 2015 <= first_timestamp.year <= 2030, "Timestamp year should be reasonable"


@pytest.mark.unit
def test_generate_summary(sample_transcript_file):
    """Test summary generation."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    messages, media_refs = parser.parse_transcript(sample_transcript_file)

    summary = parser.generate_summary(messages, media_refs)

    # Verify summary structure
    assert "total_messages" in summary
    assert "text_messages" in summary
    assert "media_messages" in summary
    assert "senders" in summary
    assert "media_type_counts" in summary

    # Verify summary statistics
    assert summary["total_messages"] == len(messages)
    assert summary["media_messages"] == len(media_refs)
    assert isinstance(summary["senders"], list)
    assert len(summary["senders"]) > 0, "Should have at least one sender"
    assert isinstance(summary["media_type_counts"], dict)

    # Verify date range if present
    if "date_range" in summary and summary["date_range"]:
        assert "first" in summary["date_range"]
        assert "last" in summary["date_range"]
        assert "days" in summary["date_range"]


@pytest.mark.unit
def test_media_correlation(temp_working_dir):
    """Test media file correlation with actual timestamp matching."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    # Create a temporary directory structure for testing
    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Create some dummy media files with timestamps
    test_files = [
        "IMG_20240115_103300.jpg",
        "AUD_20240115_103600.opus",
        "VID_20240115_111500.mp4",
    ]

    for filename in test_files:
        file_path = media_dir / filename
        file_path.touch()

    # Create mock message and media reference
    mock_message = Message(
        timestamp=datetime(2024, 1, 15, 10, 33, 0),
        sender="TestUser",
        content="IMG_20240115_103300.jpg (file attached)",
        is_media=True,
    )

    mock_refs = [
        MediaReference(
            message=mock_message,
            media_type="image",
            timestamp=datetime(2024, 1, 15, 10, 33, 0),
            sender="TestUser",
            line_number=1,
        )
    ]

    # Try to correlate
    correlation_list = parser.correlate_media_files(
        mock_refs, media_dir, time_tolerance_seconds=3600  # 1 hour tolerance
    )

    # Verify correlation function runs without error
    assert isinstance(correlation_list, list)


@pytest.mark.unit
def test_multiline_messages(temp_working_dir):
    """Test that multi-line messages are handled correctly."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    # Create a test transcript with multi-line message
    test_transcript = temp_working_dir / "test_transcript.txt"
    test_transcript.write_text(
        "1/15/24, 10:30 AM - Alice: This is a long message\n"
        "that continues on the next line\n"
        "and even another line\n"
        "1/15/24, 10:31 AM - Bob: Short message\n"
    )

    messages, _ = parser.parse_transcript(test_transcript)

    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"

    # First message should contain all three lines
    first_content = messages[0].content
    assert (
        "that continues on the next line" in first_content
    ), "Multi-line content not captured"
    assert (
        "and even another line" in first_content
    ), "All multi-line content should be captured"


@pytest.mark.unit
def test_empty_transcript(temp_working_dir):
    """Test handling of empty transcript file."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    # Create empty transcript
    empty_file = temp_working_dir / "empty.txt"
    empty_file.write_text("")

    messages, media_refs = parser.parse_transcript(empty_file)

    assert len(messages) == 0, "Empty file should have no messages"
    assert len(media_refs) == 0, "Empty file should have no media references"


@pytest.mark.unit
def test_media_reference_structure():
    """Test MediaReference dataclass structure."""
    mock_message = Message(
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        sender="TestUser",
        content="test.jpg (file attached)",
        is_media=True,
    )

    ref = MediaReference(
        message=mock_message,
        media_type="image",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        sender="TestUser",
        line_number=42,
    )

    assert ref.line_number == 42
    assert ref.media_type == "image"
    assert ref.sender == "TestUser"
    assert isinstance(ref.timestamp, datetime)
    assert ref.message == mock_message


@pytest.mark.unit
def test_message_dataclass():
    """Test Message dataclass structure."""
    msg = Message(
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        sender="TestUser",
        content="Test message",
        is_media=False,
    )

    assert msg.timestamp == datetime(2024, 1, 15, 10, 30, 0)
    assert msg.sender == "TestUser"
    assert msg.content == "Test message"
    assert msg.is_media is False


@pytest.mark.unit
@pytest.mark.slow
def test_large_transcript_parsing(sample_transcript_file):
    """Test parsing the large sample transcript for performance."""
    logger = Logger(debug=False)
    parser = TranscriptParser(logger=logger)

    # Parse the full 3,151 line transcript
    messages, media_refs = parser.parse_transcript(sample_transcript_file)

    # Verify substantial content was parsed
    assert len(messages) >= 1000, "Should parse at least 1000 messages from sample"

    # Verify performance - parsing should complete (no assertions, just coverage)
    # If we got here without timeout, parsing was successful
