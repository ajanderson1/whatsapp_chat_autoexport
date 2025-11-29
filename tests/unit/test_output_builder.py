"""
Test suite for output builder.

Tests output structure creation, transcript merging, and file organization.
"""

from pathlib import Path

import pytest

from whatsapp_chat_autoexport.output import OutputBuilder
from whatsapp_chat_autoexport.utils.logger import Logger


@pytest.mark.unit
def test_import_module():
    """Test that output module can be imported."""
    assert OutputBuilder is not None


@pytest.mark.unit
def test_extract_contact_name():
    """Test contact name extraction from filename."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Test with "WhatsApp Chat with" prefix
    path1 = Path("WhatsApp Chat with Alice.txt")
    name1 = builder._extract_contact_name(path1)
    assert name1 == "Alice"

    # Test without prefix
    path2 = Path("Bob.txt")
    name2 = builder._extract_contact_name(path2)
    assert name2 == "Bob"

    # Test with path components
    path3 = Path("/some/path/WhatsApp Chat with Charlie.txt")
    name3 = builder._extract_contact_name(path3)
    assert name3 == "Charlie"


@pytest.mark.unit
def test_build_simple_output(sample_transcript_file, temp_output_dir):
    """Test building output with sample transcript."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create fake media directory
    media_dir = temp_output_dir / "media"
    media_dir.mkdir()

    # Create destination
    dest_dir = temp_output_dir / "output"

    # Build output (without copying media)
    summary = builder.build_output(
        sample_transcript_file,
        media_dir,
        dest_dir,
        contact_name="Test Contact",
        copy_media=False,
    )

    # Verify structure
    contact_dir = dest_dir / "Test Contact"
    transcript_path = contact_dir / "transcript.txt"

    assert contact_dir.exists(), "Contact directory not created"
    assert transcript_path.exists(), "Transcript file not created"

    # Check summary
    assert summary["contact_name"] == "Test Contact"
    assert summary["total_messages"] > 0, "Should have some messages"


@pytest.mark.unit
def test_build_output_with_media(temp_working_dir, temp_output_dir):
    """Test building output with media files."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create test transcript
    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        """1/15/24, 10:30 AM - Alice: Hello!
1/15/24, 10:31 AM - Bob: Hi there!
1/15/24, 10:32 AM - Alice: IMG-001.jpg (file attached)
1/15/24, 10:33 AM - Bob: Nice photo!
"""
    )

    # Create media directory with files
    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Create test media files
    img_file = media_dir / "IMG-001.jpg"
    img_file.write_text("fake image data")

    # Build output with media
    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=True,
        include_transcriptions=False,
    )

    # Verify structure
    contact_dir = temp_output_dir / "Alice"
    media_out_dir = contact_dir / "media"

    assert media_out_dir.exists(), "Media directory not created"


@pytest.mark.unit
def test_verify_output(temp_working_dir):
    """Test output verification."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create a valid output structure
    contact_dir = temp_working_dir / "Alice"
    contact_dir.mkdir()

    transcript = contact_dir / "transcript.txt"
    transcript.write_text("Test transcript")

    media_dir = contact_dir / "media"
    media_dir.mkdir()
    (media_dir / "test.jpg").write_text("test")

    transcriptions_dir = contact_dir / "transcriptions"
    transcriptions_dir.mkdir()
    (transcriptions_dir / "test_transcription.txt").write_text("test")

    # Verify
    results = builder.verify_output(contact_dir)

    assert results["valid"] is True, "Valid output marked as invalid"
    assert results["transcript_exists"] is True, "Transcript not detected"
    assert results["media_dir_exists"] is True, "Media directory not detected"
    assert results["media_count"] == 1, f"Expected 1 media file, found {results['media_count']}"
    assert results["transcriptions_dir_exists"] is True, "Transcriptions directory not detected"
    assert (
        results["transcriptions_count"] == 1
    ), f"Expected 1 transcription, found {results['transcriptions_count']}"


@pytest.mark.unit
def test_batch_build(temp_working_dir, temp_output_dir):
    """Test batch building of multiple outputs."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create multiple transcripts
    transcripts = []
    for i, name in enumerate(["Alice", "Bob", "Charlie"], 1):
        transcript = temp_working_dir / f"chat_{name}.txt"
        transcript.write_text(f"1/15/24, 10:{30+i:02d} AM - {name}: Hello!\n")

        media_dir = temp_working_dir / f"media_{name}"
        media_dir.mkdir()

        transcripts.append((transcript, media_dir))

    # Batch build
    results = builder.batch_build_outputs(transcripts, temp_output_dir, copy_media=False)

    assert len(results) == 3, f"Expected 3 results, got {len(results)}"

    # Verify all outputs exist (filenames are "chat_Alice", etc.)
    for name in ["chat_Alice", "chat_Bob", "chat_Charlie"]:
        contact_dir = temp_output_dir / name
        assert contact_dir.exists(), f"Output not created for {name}"


@pytest.mark.integration
@pytest.mark.slow
def test_with_real_whatsapp_export(sample_export_dir, temp_output_dir):
    """Test with real WhatsApp export."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    transcript = sample_export_dir / "WhatsApp Chat with Example.txt"

    # Build output
    summary = builder.build_output(
        transcript,
        sample_export_dir,
        temp_output_dir,
        copy_media=True,
        include_transcriptions=True,
    )

    # Verify output
    assert summary["contact_name"] == "Example"
    assert summary["total_messages"] > 100, "Should have many messages"
    assert summary["media_messages"] > 10, "Should have media references"

    # Verify output structure
    verification = builder.verify_output(summary["output_dir"])
    assert verification["valid"] is True, "Output verification failed"


@pytest.mark.unit
def test_merged_transcript_format(temp_working_dir, temp_output_dir):
    """Test merged transcript format."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create test transcript
    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        """1/15/24, 10:30 AM - Alice: Hello!
1/15/24, 10:31 AM - Bob: How are you?
1/15/24, 10:32 AM - Alice: Great!
"""
    )

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Build output
    summary = builder.build_output(
        transcript_path, media_dir, temp_output_dir, contact_name="Alice", copy_media=False
    )

    # Read merged transcript
    transcript_content = summary["transcript_path"].read_text()

    # Check header
    assert (
        "# WhatsApp Chat with Alice" in transcript_content
    ), "Header missing in merged transcript"
    assert "# Total messages:" in transcript_content, "Message count missing in header"

    # Check messages are present
    assert "Alice: Hello!" in transcript_content, "Message content missing"


@pytest.mark.unit
def test_output_with_transcriptions(temp_working_dir, temp_output_dir):
    """Test output building with transcription files."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create test transcript
    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        """1/15/24, 10:30 AM - Alice: Hello!
1/15/24, 10:31 AM - Bob: PTT-001.opus (file attached)
"""
    )

    # Create media directory with audio file and transcription
    media_dir = temp_working_dir / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001.opus").write_text("fake audio")
    (media_dir / "PTT-001_transcription.txt").write_text("This is the transcription")

    # Build output
    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Bob",
        copy_media=False,
        include_transcriptions=True,
    )

    # Verify transcriptions directory exists
    contact_dir = temp_output_dir / "Bob"
    transcriptions_dir = contact_dir / "transcriptions"

    assert transcriptions_dir.exists(), "Transcriptions directory not created"
    assert summary["transcriptions_copied"] > 0, "Transcriptions should be copied"


@pytest.mark.unit
def test_output_without_transcriptions(temp_working_dir, temp_output_dir):
    """Test output building without transcription files."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create test transcript
    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text("""1/15/24, 10:30 AM - Alice: Hello!\n""")

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Build output without transcriptions
    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
    )

    # Verify transcriptions directory doesn't exist
    contact_dir = temp_output_dir / "Alice"
    transcriptions_dir = contact_dir / "transcriptions"

    assert not transcriptions_dir.exists(), "Transcriptions directory should not exist"
    assert summary["transcriptions_copied"] == 0, "No transcriptions should be copied"


@pytest.mark.unit
def test_empty_transcript(temp_working_dir, temp_output_dir):
    """Test handling of empty transcript."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Create empty transcript
    transcript_path = temp_working_dir / "empty.txt"
    transcript_path.write_text("")

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Build output
    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Empty",
        copy_media=False,
    )

    # Should still create output structure
    assert summary["total_messages"] == 0
    assert summary["output_dir"].exists()
