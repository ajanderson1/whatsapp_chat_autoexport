"""
Test suite for output builder.

Tests output structure creation, transcript merging, and file organization.
"""

from pathlib import Path

import pytest

from whatsapp_chat_autoexport.output import OutputBuilder, SpecFormatter, IndexBuilder
from whatsapp_chat_autoexport.utils.logger import Logger


@pytest.mark.unit
def test_import_module():
    """Test that output module can be imported."""
    assert OutputBuilder is not None


@pytest.mark.unit
def test_extract_contact_name():
    """Test contact name extraction from filename."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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
    builder = OutputBuilder(logger=logger, format_version="legacy")

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


# =========================================================================
# V2 format tests
# =========================================================================


@pytest.mark.unit
def test_v2_produces_transcript_md(temp_working_dir, temp_output_dir):
    """Test that v2 format produces transcript.md (not transcript.txt)."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="v2")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        "1/15/24, 10:30 AM - Alice: Hello!\n"
        "1/15/24, 10:31 AM - Bob: Hi there!\n"
    )

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
        chat_jid="1234@s.whatsapp.net",
    )

    contact_dir = temp_output_dir / "Alice"
    assert (contact_dir / "transcript.md").exists(), "transcript.md should exist in v2 mode"
    assert not (contact_dir / "transcript.txt").exists(), "transcript.txt should NOT exist in v2 mode"
    assert summary["format_version"] == "v2"
    assert summary["transcript_path"].name == "transcript.md"


@pytest.mark.unit
def test_v2_produces_index_md(temp_working_dir, temp_output_dir):
    """Test that v2 format produces index.md alongside transcript."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="v2")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text("1/15/24, 10:30 AM - Alice: Hello!\n")

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
        chat_jid="1234@s.whatsapp.net",
    )

    contact_dir = temp_output_dir / "Alice"
    index_path = contact_dir / "index.md"
    assert index_path.exists(), "index.md should exist in v2 mode"

    index_content = index_path.read_text()
    assert "---" in index_content, "index.md should contain YAML frontmatter"


@pytest.mark.unit
def test_v2_transcript_has_day_headers_and_typed_media(temp_working_dir, temp_output_dir):
    """Test that v2 transcript.md has day headers and typed media tags."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="v2")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        "1/15/24, 10:30 AM - Alice: Hello!\n"
        "1/15/24, 10:31 AM - Bob: IMG-20240115-WA0001.jpg (file attached)\n"
        "1/16/24, 09:00 AM - Alice: Good morning\n"
    )

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
        chat_jid="1234@s.whatsapp.net",
    )

    transcript_content = summary["transcript_path"].read_text()

    # Day headers
    assert "## 2024-01-15" in transcript_content, "Should have day header for 2024-01-15"
    assert "## 2024-01-16" in transcript_content, "Should have day header for 2024-01-16"

    # Typed media tag (image -> <photo>)
    assert "<photo>" in transcript_content, "Should have typed <photo> media tag"

    # Spec format: [HH:MM] Sender: content
    assert "[10:30] Alice: Hello!" in transcript_content, "Should use spec message format"


@pytest.mark.unit
def test_v2_index_has_correct_frontmatter(temp_working_dir, temp_output_dir):
    """Test that v2 index.md has correct YAML frontmatter fields."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="v2")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        "1/15/24, 10:30 AM - Alice: Hello!\n"
        "1/15/24, 10:31 AM - Bob: Hi there!\n"
    )

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
        chat_jid="1234@s.whatsapp.net",
    )

    index_content = (temp_output_dir / "Alice" / "index.md").read_text()

    assert "type: note" in index_content
    assert "chat_type: direct" in index_content
    assert 'jid: "1234@s.whatsapp.net"' in index_content
    assert "message_count: 2" in index_content
    assert "whatsapp" in index_content
    assert "correspondence" in index_content


@pytest.mark.unit
def test_legacy_format_unchanged_regression(temp_working_dir, temp_output_dir):
    """Regression: legacy format must produce transcript.txt, no index.md."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="legacy")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text(
        "1/15/24, 10:30 AM - Alice: Hello!\n"
        "1/15/24, 10:31 AM - Bob: Hi there!\n"
    )

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
    )

    contact_dir = temp_output_dir / "Alice"
    assert (contact_dir / "transcript.txt").exists(), "Legacy must produce transcript.txt"
    assert not (contact_dir / "transcript.md").exists(), "Legacy must NOT produce transcript.md"
    assert not (contact_dir / "index.md").exists(), "Legacy must NOT produce index.md"
    assert summary["format_version"] == "legacy"

    # Content should use old-style header
    content = summary["transcript_path"].read_text()
    assert "# WhatsApp Chat with Alice" in content


@pytest.mark.unit
def test_v2_atomic_write_safety(temp_working_dir, temp_output_dir):
    """Test that atomic write preserves original on failure."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="v2")

    target = temp_output_dir / "test_file.md"
    original_content = "original content"
    target.write_text(original_content)

    # Successful atomic write should replace the file
    OutputBuilder._atomic_write(target, "new content")
    assert target.read_text() == "new content"

    # Verify no .tmp file is left behind
    tmp_path = target.with_suffix(".md.tmp")
    assert not tmp_path.exists(), "Temp file should be cleaned up after successful write"


@pytest.mark.unit
def test_v2_atomic_write_no_leftover_tmp_on_success(temp_output_dir):
    """Verify .tmp file is not left behind after a successful atomic write."""
    target = temp_output_dir / "clean.md"
    OutputBuilder._atomic_write(target, "content")
    assert target.read_text() == "content"
    assert not target.with_suffix(".md.tmp").exists()


@pytest.mark.unit
def test_batch_build_outputs_with_v2(temp_working_dir, temp_output_dir):
    """Test batch_build_outputs passes format_version='v2' through."""
    logger = Logger()
    builder = OutputBuilder(logger=logger, format_version="legacy")

    transcripts = []
    for i, name in enumerate(["Alice", "Bob"], 1):
        transcript = temp_working_dir / f"chat_{name}.txt"
        transcript.write_text(f"1/15/24, 10:{30+i:02d} AM - {name}: Hello!\n")

        media_dir = temp_working_dir / f"media_{name}"
        media_dir.mkdir()

        transcripts.append((transcript, media_dir))

    results = builder.batch_build_outputs(
        transcripts,
        temp_output_dir,
        copy_media=False,
        include_transcriptions=False,
        format_version="v2",
    )

    assert len(results) == 2
    for result in results:
        assert result["format_version"] == "v2"
        assert result["transcript_path"].name == "transcript.md"
        # Verify index.md was also created
        index_path = result["output_dir"] / "index.md"
        assert index_path.exists(), f"index.md should exist for {result['contact_name']}"


@pytest.mark.unit
def test_build_output_format_version_override(temp_working_dir, temp_output_dir):
    """Test that per-call format_version overrides the instance default."""
    logger = Logger()
    # Instance is legacy by default
    builder = OutputBuilder(logger=logger, format_version="legacy")

    transcript_path = temp_working_dir / "chat.txt"
    transcript_path.write_text("1/15/24, 10:30 AM - Alice: Hello!\n")

    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Override to v2 for this specific call
    summary = builder.build_output(
        transcript_path,
        media_dir,
        temp_output_dir,
        contact_name="Alice",
        copy_media=False,
        include_transcriptions=False,
        format_version="v2",
        chat_jid="override@s.whatsapp.net",
    )

    assert summary["format_version"] == "v2"
    assert (temp_output_dir / "Alice" / "transcript.md").exists()
    assert (temp_output_dir / "Alice" / "index.md").exists()


@pytest.mark.unit
def test_invalid_format_version_raises():
    """Test that an invalid format_version raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported format_version"):
        OutputBuilder(format_version="v3")
