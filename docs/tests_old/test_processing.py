#!/usr/bin/env python3
"""
Test the processing module with a mock directory structure.
"""

import sys
import tempfile
import shutil
from pathlib import Path

print("=" * 70)
print("Testing Processing Module")
print("=" * 70)

# Create a temporary directory structure
temp_dir = Path(tempfile.mkdtemp(prefix="whatsapp_test_"))
print(f"\nCreated test directory: {temp_dir}")

try:
    # Test 1: Test with empty directory
    print("\n1. Testing with empty directory...")
    from whatsapp_chat_autoexport.processing.archive_extractor import (
        validate_directory,
        find_whatsapp_chat_files
    )
    from whatsapp_chat_autoexport.utils.logger import Logger
    
    logger = Logger(debug=False)
    
    # Validate directory
    validated = validate_directory(str(temp_dir), logger)
    if validated and validated.exists():
        print(f"   ✓ Empty directory validates correctly: {validated}")
    else:
        print("   ✗ Directory validation failed")
        sys.exit(1)
    
    # Find files (should be empty)
    files = find_whatsapp_chat_files(validated, logger)
    if len(files) == 0:
        print("   ✓ Correctly finds no files in empty directory")
    else:
        print(f"   ✗ Expected 0 files, found {len(files)}")
        sys.exit(1)
    
    # Test 2: Test with a mock WhatsApp chat file
    print("\n2. Testing with mock WhatsApp chat file...")
    
    # Create a mock file (not a real zip, just for filename testing)
    mock_file = validated / "WhatsApp Chat with Test Contact"
    mock_file.write_text("Mock content")
    
    # Try to find it
    files = find_whatsapp_chat_files(validated, logger)
    
    # This should find 0 files because is_zip_file will reject it (not a real ZIP)
    if len(files) == 0:
        print("   ✓ Correctly rejects non-ZIP file")
    else:
        print(f"   ✗ Should reject non-ZIP file, found {len(files)}")
        sys.exit(1)
    
    # Test 3: Test is_zip_file function
    print("\n3. Testing is_zip_file function...")
    from whatsapp_chat_autoexport.processing.archive_extractor import is_zip_file
    
    # Test with non-ZIP file
    if not is_zip_file(mock_file):
        print("   ✓ is_zip_file correctly identifies non-ZIP file")
    else:
        print("   ✗ is_zip_file should return False for non-ZIP")
        sys.exit(1)
    
    # Test 4: Test with tilde expansion
    print("\n4. Testing directory validation with ~ expansion...")
    home_validated = validate_directory("~", logger)
    if home_validated and home_validated.exists():
        print(f"   ✓ Correctly expands ~ to {home_validated}")
    else:
        print("   ✗ Failed to expand ~")
        sys.exit(1)
    
    # Test 5: Test validate_directory with quotes
    print("\n5. Testing directory validation with quoted path...")
    quoted_path = f'"{str(temp_dir)}"'
    quoted_validated = validate_directory(quoted_path, logger)
    if quoted_validated and quoted_validated.exists():
        print(f"   ✓ Correctly handles quoted paths")
    else:
        print("   ✗ Failed to handle quoted path")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("✅ All processing module tests passed!")
    print("=" * 70)
    
finally:
    # Cleanup
    print(f"\nCleaning up test directory: {temp_dir}")
    shutil.rmtree(temp_dir)
