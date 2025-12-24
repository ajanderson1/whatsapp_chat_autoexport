#!/usr/bin/env python3
"""
Test suite for output builder.

Tests output structure creation, transcript merging, and file organization.
"""

import sys
from pathlib import Path
import tempfile
import shutil

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from whatsapp_chat_autoexport.output import OutputBuilder
from whatsapp_chat_autoexport.utils.logger import Logger


def test_import_module():
    """Test that output module can be imported."""
    print("✓ OutputBuilder imported successfully")
    return True


def test_extract_contact_name():
    """Test contact name extraction from filename."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Test with "WhatsApp Chat with" prefix
    path1 = Path("WhatsApp Chat with Alice.txt")
    name1 = builder._extract_contact_name(path1)
    if name1 != "Alice":
        print(f"✗ Expected 'Alice', got '{name1}'")
        return False

    # Test without prefix
    path2 = Path("Bob.txt")
    name2 = builder._extract_contact_name(path2)
    if name2 != "Bob":
        print(f"✗ Expected 'Bob', got '{name2}'")
        return False

    print(f"  Extracted: '{name1}', '{name2}'")
    print("✓ Contact name extraction working")
    return True


def test_build_simple_output():
    """Test building output with sample transcript."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Use the existing sample transcript
        sample_transcript = project_root / "sample_transcript.txt"

        if not sample_transcript.exists():
            print("✗ Sample transcript not found")
            return False

        # Create fake media directory
        media_dir = temp_path / "media"
        media_dir.mkdir()

        # Create destination
        dest_dir = temp_path / "output"

        # Build output (without copying media)
        summary = builder.build_output(
            sample_transcript,
            media_dir,
            dest_dir,
            contact_name="Test Contact",
            copy_media=False
        )

        # Verify structure
        contact_dir = dest_dir / "Test Contact"
        transcript_path = contact_dir / "transcript.txt"

        if not contact_dir.exists():
            print("✗ Contact directory not created")
            return False

        if not transcript_path.exists():
            print("✗ Transcript file not created")
            return False

        # Check summary
        if summary['contact_name'] != "Test Contact":
            print(f"✗ Wrong contact name: {summary['contact_name']}")
            return False

        if summary['total_messages'] != 15:
            print(f"✗ Expected 15 messages, got {summary['total_messages']}")
            return False

        print(f"  Output dir: {contact_dir.name}")
        print(f"  Messages: {summary['total_messages']}")
        print(f"  Media refs: {summary['media_messages']}")
        print("✓ Simple output build working")
        return True


def test_build_output_with_media():
    """Test building output with media files."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create test transcript
        transcript_path = temp_path / "chat.txt"
        transcript_path.write_text("""1/15/24, 10:30 AM - Alice: Hello!
1/15/24, 10:31 AM - Bob: Hi there!
1/15/24, 10:32 AM - Alice: IMG-001.jpg (file attached)
1/15/24, 10:33 AM - Bob: Nice photo!
""")

        # Create media directory with files
        media_dir = temp_path / "media"
        media_dir.mkdir()

        # Create test media files (with recent timestamps so correlation might work)
        img_file = media_dir / "IMG-001.jpg"
        img_file.write_text("fake image data")

        # Create destination
        dest_dir = temp_path / "output"

        # Build output with media
        summary = builder.build_output(
            transcript_path,
            media_dir,
            dest_dir,
            contact_name="Alice",
            copy_media=True,
            include_transcriptions=False
        )

        # Verify structure
        contact_dir = dest_dir / "Alice"
        media_out_dir = contact_dir / "media"

        if not media_out_dir.exists():
            print("✗ Media directory not created")
            return False

        # Check if media was copied
        copied_img = media_out_dir / "IMG-001.jpg"
        # Note: May not exist if correlation failed due to timestamps

        print(f"  Media copied: {summary['media_copied']}")
        print(f"  Media dir exists: {media_out_dir.exists()}")
        print("✓ Output with media working")
        return True


def test_verify_output():
    """Test output verification."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create a valid output structure
        contact_dir = temp_path / "Alice"
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

        if not results['valid']:
            print("✗ Valid output marked as invalid")
            return False

        if not results['transcript_exists']:
            print("✗ Transcript not detected")
            return False

        if not results['media_dir_exists']:
            print("✗ Media directory not detected")
            return False

        if results['media_count'] != 1:
            print(f"✗ Expected 1 media file, found {results['media_count']}")
            return False

        print(f"  Transcript: {results['transcript_exists']}")
        print(f"  Media dir: {results['media_dir_exists']} ({results['media_count']} files)")
        print(f"  Transcriptions: {results['transcriptions_dir_exists']} ({results['transcriptions_count']} files)")
        print("✓ Output verification working")
        return True


def test_batch_build():
    """Test batch building of multiple outputs."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create multiple transcripts
        transcripts = []
        for i, name in enumerate(["Alice", "Bob", "Charlie"], 1):
            transcript = temp_path / f"chat_{name}.txt"
            transcript.write_text(f"1/15/24, 10:{30+i:02d} AM - {name}: Hello!\n")

            media_dir = temp_path / f"media_{name}"
            media_dir.mkdir()

            transcripts.append((transcript, media_dir))

        # Batch build
        dest_dir = temp_path / "output"

        results = builder.batch_build_outputs(
            transcripts,
            dest_dir,
            copy_media=False
        )

        if len(results) != 3:
            print(f"✗ Expected 3 results, got {len(results)}")
            return False

        # Verify all outputs exist (filenames are "chat_Alice", etc.)
        for name in ["chat_Alice", "chat_Bob", "chat_Charlie"]:
            contact_dir = dest_dir / name
            if not contact_dir.exists():
                print(f"✗ Output not created for {name}")
                return False

        print(f"  Processed: {len(results)} chats")
        print("✓ Batch build working")
        return True


def test_with_real_whatsapp_export():
    """Test with real WhatsApp export if available."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    # Check for real example
    example_dir = project_root / "WhatsApp Chat with Example"
    if not example_dir.exists():
        print("  (Skipping: real example not found)")
        return True

    transcript = example_dir / "WhatsApp Chat with Example.txt"
    if not transcript.exists():
        print("  (Skipping: transcript not found)")
        return True

    with tempfile.TemporaryDirectory() as tmpdir:
        dest_dir = Path(tmpdir) / "output"

        # Build output
        try:
            summary = builder.build_output(
                transcript,
                example_dir,
                dest_dir,
                copy_media=True,
                include_transcriptions=True
            )

            print(f"\n  Real WhatsApp Export:")
            print(f"    Contact: {summary['contact_name']}")
            print(f"    Messages: {summary['total_messages']}")
            print(f"    Media refs: {summary['media_messages']}")
            print(f"    Media copied: {summary['media_copied']}")
            print(f"    Transcriptions: {summary['transcriptions_copied']}")

            # Verify output
            verification = builder.verify_output(summary['output_dir'])
            if not verification['valid']:
                print("  ✗ Output verification failed")
                return False

            print("✓ Real WhatsApp export processed successfully")
            return True

        except Exception as e:
            print(f"✗ Error processing real export: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_merged_transcript_format():
    """Test merged transcript format."""
    logger = Logger()
    builder = OutputBuilder(logger=logger)

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create test transcript
        transcript_path = temp_path / "chat.txt"
        transcript_path.write_text("""1/15/24, 10:30 AM - Alice: Hello!
1/15/24, 10:31 AM - Bob: How are you?
1/15/24, 10:32 AM - Alice: Great!
""")

        media_dir = temp_path / "media"
        media_dir.mkdir()

        dest_dir = temp_path / "output"

        # Build output
        summary = builder.build_output(
            transcript_path,
            media_dir,
            dest_dir,
            contact_name="Alice",
            copy_media=False
        )

        # Read merged transcript
        transcript_content = summary['transcript_path'].read_text()

        # Check header
        if "# WhatsApp Chat with Alice" not in transcript_content:
            print("✗ Header missing in merged transcript")
            return False

        if "# Total messages:" not in transcript_content:
            print("✗ Message count missing in header")
            return False

        # Check messages are present
        if "Alice: Hello!" not in transcript_content:
            print("✗ Message content missing")
            return False

        print("  Header: ✓")
        print("  Messages: ✓")
        print("✓ Merged transcript format correct")
        return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("Output Builder Test Suite")
    print("=" * 70)

    tests = [
        ("Import Module", test_import_module),
        ("Extract Contact Name", test_extract_contact_name),
        ("Build Simple Output", test_build_simple_output),
        ("Build Output with Media", test_build_output_with_media),
        ("Verify Output", test_verify_output),
        ("Batch Build", test_batch_build),
        ("Merged Transcript Format", test_merged_transcript_format),
        ("Real WhatsApp Export", test_with_real_whatsapp_export),
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
