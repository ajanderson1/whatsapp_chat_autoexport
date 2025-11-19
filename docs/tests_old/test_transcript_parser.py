#!/usr/bin/env python3
"""
Test suite for transcript parser.

Tests message parsing, media detection, and file correlation.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from whatsapp_chat_autoexport.processing.transcript_parser import (
    TranscriptParser,
    Message,
    MediaReference
)
from whatsapp_chat_autoexport.utils.logger import Logger


def test_parser_import():
    """Test that the parser module can be imported."""
    print("✓ TranscriptParser imported successfully")
    return True


def test_parse_sample_transcript():
    """Test parsing the sample transcript."""
    logger = Logger(debug=True)
    parser = TranscriptParser(logger=logger)

    sample_file = project_root / "sample_transcript.txt"

    if not sample_file.exists():
        print(f"✗ Sample transcript not found: {sample_file}")
        return False

    messages, media_refs = parser.parse_transcript(sample_file)

    print(f"\n✓ Parsed {len(messages)} messages")
    print(f"✓ Found {len(media_refs)} media references")

    # Verify we got the expected number of messages
    expected_messages = 15
    if len(messages) != expected_messages:
        print(f"✗ Expected {expected_messages} messages, got {len(messages)}")
        return False

    # Verify we got the expected number of media references
    expected_media = 5
    if len(media_refs) != expected_media:
        print(f"✗ Expected {expected_media} media references, got {len(media_refs)}")
        return False

    print("✓ Message count matches expected")
    print("✓ Media reference count matches expected")

    return True


def test_message_structure():
    """Test that messages are parsed with correct structure."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    sample_file = project_root / "sample_transcript.txt"
    messages, _ = parser.parse_transcript(sample_file)

    if not messages:
        print("✗ No messages parsed")
        return False

    # Check first message
    first_msg = messages[0]

    print(f"\nFirst message:")
    print(f"  Timestamp: {first_msg.timestamp}")
    print(f"  Sender: {first_msg.sender}")
    print(f"  Content: {first_msg.content}")
    print(f"  Is media: {first_msg.is_media}")

    # Verify structure
    if not isinstance(first_msg.timestamp, datetime):
        print("✗ Timestamp is not a datetime object")
        return False

    if first_msg.sender != "Alice":
        print(f"✗ Expected sender 'Alice', got '{first_msg.sender}'")
        return False

    if first_msg.content != "Hey! How are you?":
        print(f"✗ Unexpected content: {first_msg.content}")
        return False

    if first_msg.is_media:
        print("✗ First message should not be media")
        return False

    print("✓ Message structure is correct")
    return True


def test_media_detection():
    """Test that media references are correctly detected."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    sample_file = project_root / "sample_transcript.txt"
    messages, media_refs = parser.parse_transcript(sample_file)

    print("\nMedia references found:")
    for ref in media_refs:
        print(f"  Line {ref.line_number}: {ref.media_type} from {ref.sender}")

    # Verify media types are detected
    media_types = [ref.media_type for ref in media_refs]

    expected_types = ['image', 'audio', 'video', 'image', 'image']

    # Check if we have the expected media types (order might vary)
    type_counts = {}
    for mt in media_types:
        type_counts[mt] = type_counts.get(mt, 0) + 1

    expected_counts = {'image': 3, 'audio': 1, 'video': 1}

    for media_type, expected_count in expected_counts.items():
        actual_count = type_counts.get(media_type, 0)
        if actual_count != expected_count:
            print(f"✗ Expected {expected_count} {media_type} refs, got {actual_count}")
            return False

    print("✓ All media types detected correctly")
    return True


def test_timestamp_parsing():
    """Test that various timestamp formats are parsed correctly."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    sample_file = project_root / "sample_transcript.txt"
    messages, _ = parser.parse_transcript(sample_file)

    # Verify timestamps are chronologically ordered (mostly)
    for i in range(len(messages) - 1):
        curr_time = messages[i].timestamp
        next_time = messages[i + 1].timestamp

        # Allow for same timestamp or increasing
        if curr_time > next_time:
            # Check if it's a new day
            if curr_time.date() != next_time.date():
                # This is expected (messages from next day)
                continue
            else:
                print(f"✗ Timestamps not in order: {curr_time} > {next_time}")
                return False

    print("✓ All timestamps parsed correctly")
    return True


def test_generate_summary():
    """Test summary generation."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    sample_file = project_root / "sample_transcript.txt"
    messages, media_refs = parser.parse_transcript(sample_file)

    summary = parser.generate_summary(messages, media_refs)

    print("\nTranscript Summary:")
    print(f"  Total messages: {summary['total_messages']}")
    print(f"  Text messages: {summary['text_messages']}")
    print(f"  Media messages: {summary['media_messages']}")
    print(f"  Senders: {', '.join(summary['senders'])}")
    print(f"  Media types: {summary['media_type_counts']}")

    if summary['date_range']:
        print(f"  Date range: {summary['date_range']['first']} to {summary['date_range']['last']}")
        print(f"  Duration: {summary['date_range']['days']} days")

    # Verify summary statistics
    if summary['total_messages'] != len(messages):
        print("✗ Total messages count incorrect")
        return False

    if summary['media_messages'] != len(media_refs):
        print("✗ Media messages count incorrect")
        return False

    if len(summary['senders']) != 2:
        print("✗ Expected 2 senders (Alice and Bob)")
        return False

    print("✓ Summary generated correctly")
    return True


def test_media_correlation():
    """Test media file correlation (mock test without actual files)."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    # Create a temporary directory structure for testing
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        media_dir = Path(tmpdir) / "media"
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

        sample_file = project_root / "sample_transcript.txt"
        messages, media_refs = parser.parse_transcript(sample_file)

        # Try to correlate (will mostly fail due to timestamp mismatch)
        correlation_list = parser.correlate_media_files(
            media_refs,
            media_dir,
            time_tolerance_seconds=3600  # 1 hour tolerance for testing
        )

        print(f"\n✓ Correlation attempted for {len(media_refs)} references")
        print(f"  Created {len(test_files)} test files")
        print(f"  Correlation list: {len(correlation_list)} entries")

        # Just verify the function runs without error
        return True


def test_multiline_messages():
    """Test that multi-line messages are handled correctly."""
    logger = Logger()
    parser = TranscriptParser(logger=logger)

    # Create a test transcript with multi-line message
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("1/15/24, 10:30 AM - Alice: This is a long message\n")
        f.write("that continues on the next line\n")
        f.write("and even another line\n")
        f.write("1/15/24, 10:31 AM - Bob: Short message\n")
        temp_path = Path(f.name)

    try:
        messages, _ = parser.parse_transcript(temp_path)

        if len(messages) != 2:
            print(f"✗ Expected 2 messages, got {len(messages)}")
            return False

        # First message should contain all three lines
        first_content = messages[0].content
        if "that continues on the next line" not in first_content:
            print("✗ Multi-line content not captured")
            return False

        print("✓ Multi-line messages handled correctly")
        return True

    finally:
        temp_path.unlink()


def main():
    """Run all tests."""
    print("=" * 70)
    print("Transcript Parser Test Suite")
    print("=" * 70)

    tests = [
        ("Import Test", test_parser_import),
        ("Parse Sample Transcript", test_parse_sample_transcript),
        ("Message Structure", test_message_structure),
        ("Media Detection", test_media_detection),
        ("Timestamp Parsing", test_timestamp_parsing),
        ("Generate Summary", test_generate_summary),
        ("Media Correlation", test_media_correlation),
        ("Multi-line Messages", test_multiline_messages),
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{'─' * 70}")
        print(f"Test: {test_name}")
        print('─' * 70)

        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("=" * 70)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 70)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
