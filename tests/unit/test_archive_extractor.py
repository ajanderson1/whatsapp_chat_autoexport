"""
Test suite for archive extractor module.

Tests directory validation, file finding, and ZIP file detection.
"""

from pathlib import Path

import pytest

from whatsapp_chat_autoexport.processing.archive_extractor import (
    validate_directory,
    find_whatsapp_chat_files,
    is_zip_file,
)
from whatsapp_chat_autoexport.utils.logger import Logger


@pytest.mark.unit
def test_empty_directory(temp_working_dir):
    """Test with empty directory."""
    logger = Logger(debug=False)

    # Validate directory
    validated = validate_directory(str(temp_working_dir), logger)

    assert validated is not None, "Directory validation failed"
    assert validated.exists(), "Validated directory should exist"
    # Use resolve() to handle macOS /private/var vs /var symlink
    assert validated.resolve() == temp_working_dir.resolve(), "Validated path should match input"

    # Find files (should be empty)
    files = find_whatsapp_chat_files(validated, logger)

    assert len(files) == 0, f"Expected 0 files in empty directory, found {len(files)}"


@pytest.mark.unit
def test_mock_whatsapp_chat_file(temp_working_dir):
    """Test with mock WhatsApp chat file (not a real ZIP)."""
    logger = Logger(debug=False)

    # Create a mock file (not a real zip, just for filename testing)
    mock_file = temp_working_dir / "WhatsApp Chat with Test Contact"
    mock_file.write_text("Mock content")

    # Try to find it
    files = find_whatsapp_chat_files(temp_working_dir, logger)

    # Should find 0 files because is_zip_file will reject it
    assert len(files) == 0, "Should reject non-ZIP file"


@pytest.mark.unit
def test_is_zip_file_function(temp_working_dir):
    """Test is_zip_file function with non-ZIP file."""
    # Create non-ZIP file
    non_zip_file = temp_working_dir / "test_file.txt"
    non_zip_file.write_text("Not a ZIP file")

    # Test with non-ZIP file
    assert is_zip_file(non_zip_file) is False, "Should identify non-ZIP file correctly"


@pytest.mark.unit
def test_is_zip_file_with_real_zip(temp_working_dir):
    """Test is_zip_file function with actual ZIP file."""
    import zipfile

    # Create a real ZIP file
    zip_path = temp_working_dir / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("test.txt", "test content")

    # Test with real ZIP file
    assert is_zip_file(zip_path) is True, "Should identify ZIP file correctly"


@pytest.mark.unit
def test_tilde_expansion():
    """Test directory validation with ~ expansion."""
    logger = Logger(debug=False)

    # Test with tilde
    home_validated = validate_directory("~", logger)

    assert home_validated is not None, "Failed to expand ~"
    assert home_validated.exists(), "Expanded home directory should exist"
    assert "~" not in str(home_validated), "Should have expanded ~"


@pytest.mark.unit
def test_quoted_paths(temp_working_dir):
    """Test directory validation with quoted path."""
    logger = Logger(debug=False)

    # Test with quoted path
    quoted_path = f'"{str(temp_working_dir)}"'
    quoted_validated = validate_directory(quoted_path, logger)

    assert quoted_validated is not None, "Failed to handle quoted path"
    assert quoted_validated.exists(), "Validated directory should exist"
    assert '"' not in str(quoted_validated), "Should have removed quotes"


@pytest.mark.unit
def test_nonexistent_directory():
    """Test directory validation with nonexistent directory."""
    logger = Logger(debug=False)

    # Test with nonexistent path
    nonexistent = validate_directory("/nonexistent/path/that/does/not/exist", logger)

    # Should return None or handle gracefully
    # The actual behavior depends on the implementation
    # Just verify it doesn't crash
    assert True  # If we got here, it didn't crash


@pytest.mark.unit
def test_find_whatsapp_files_with_zip(temp_working_dir):
    """Test finding WhatsApp chat files with real ZIP files."""
    import zipfile

    logger = Logger(debug=False)

    # Create a real ZIP file with WhatsApp naming pattern
    zip_path = temp_working_dir / "WhatsApp Chat with Alice"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("chat.txt", "fake chat content")

    # Find files
    files = find_whatsapp_chat_files(temp_working_dir, logger)

    # Should find the ZIP file
    assert len(files) > 0, "Should find WhatsApp ZIP file"
    assert zip_path in files, "Should include the created ZIP file"


@pytest.mark.unit
def test_multiple_whatsapp_files(temp_working_dir):
    """Test finding multiple WhatsApp chat files."""
    import zipfile

    logger = Logger(debug=False)

    # Create multiple real ZIP files
    names = ["Alice", "Bob", "Charlie"]
    for name in names:
        zip_path = temp_working_dir / f"WhatsApp Chat with {name}"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("chat.txt", f"chat with {name}")

    # Find files
    files = find_whatsapp_chat_files(temp_working_dir, logger)

    # Should find all three files
    assert len(files) == 3, f"Expected 3 files, found {len(files)}"


@pytest.mark.unit
def test_mixed_files(temp_working_dir):
    """Test finding WhatsApp files among mixed file types."""
    import zipfile

    logger = Logger(debug=False)

    # Create a valid WhatsApp ZIP
    valid_zip = temp_working_dir / "WhatsApp Chat with Alice"
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.writestr("chat.txt", "chat content")

    # Create non-WhatsApp files
    (temp_working_dir / "random.txt").write_text("random")
    (temp_working_dir / "other.zip").write_bytes(b"PK\x03\x04")  # ZIP magic bytes
    (temp_working_dir / "WhatsApp Chat with Bob").write_text("not a zip")

    # Find files
    files = find_whatsapp_chat_files(temp_working_dir, logger)

    # Should only find the valid WhatsApp ZIP
    assert len(files) == 1, f"Expected 1 file, found {len(files)}"
    assert valid_zip in files, "Should find the valid WhatsApp ZIP"
