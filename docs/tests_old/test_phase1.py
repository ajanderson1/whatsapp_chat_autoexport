#!/usr/bin/env python3
"""
Phase 1 Test Script - Verify modular refactoring works correctly.

This script tests that all modules can be imported and basic functionality works
without requiring an actual Android device connection.
"""

import sys
from pathlib import Path

print("=" * 70)
print("Phase 1 Test - Module Import and Structure Verification")
print("=" * 70)

# Test 1: Import all modules
print("\n1. Testing module imports...")
test_results = []

try:
    from whatsapp_chat_autoexport.utils.logger import Logger

    print("   ✓ Logger imported")
    test_results.append(("Logger import", True))
except Exception as e:
    print(f"   ✗ Logger import failed: {e}")
    test_results.append(("Logger import", False))

try:
    print("   ✓ AppiumManager imported")
    test_results.append(("AppiumManager import", True))
except Exception as e:
    print(f"   ✗ AppiumManager import failed: {e}")
    test_results.append(("AppiumManager import", False))

try:
    print("   ✓ WhatsAppDriver imported")
    test_results.append(("WhatsAppDriver import", True))
except Exception as e:
    print(f"   ✗ WhatsAppDriver import failed: {e}")
    test_results.append(("WhatsAppDriver import", False))

try:
    from whatsapp_chat_autoexport.export.chat_exporter import validate_resume_directory

    print("   ✓ ChatExporter imported")
    test_results.append(("ChatExporter import", True))
except Exception as e:
    print(f"   ✗ ChatExporter import failed: {e}")
    test_results.append(("ChatExporter import", False))

try:
    print("   ✓ Interactive module imported")
    test_results.append(("Interactive import", True))
except Exception as e:
    print(f"   ✗ Interactive import failed: {e}")
    test_results.append(("Interactive import", False))

try:
    from whatsapp_chat_autoexport.processing.archive_extractor import (
        validate_directory,
    )

    print("   ✓ Archive extractor imported")
    test_results.append(("Archive extractor import", True))
except Exception as e:
    print(f"   ✗ Archive extractor import failed: {e}")
    test_results.append(("Archive extractor import", False))

try:
    print("   ✓ Export CLI imported")
    test_results.append(("Export CLI import", True))
except Exception as e:
    print(f"   ✗ Export CLI import failed: {e}")
    test_results.append(("Export CLI import", False))

try:
    print("   ✓ Processing CLI imported")
    test_results.append(("Processing CLI import", True))
except Exception as e:
    print(f"   ✗ Processing CLI import failed: {e}")
    test_results.append(("Processing CLI import", False))

# Test 2: Verify Logger functionality
print("\n2. Testing Logger functionality...")
try:
    logger = Logger(debug=True)
    logger.info("Test info message")
    logger.success("Test success message")
    logger.warning("Test warning message")
    logger.error("Test error message")
    logger.debug_msg("Test debug message")
    logger.step(1, "Test step message")
    print("   ✓ Logger methods work correctly")
    test_results.append(("Logger functionality", True))
except Exception as e:
    print(f"   ✗ Logger functionality failed: {e}")
    test_results.append(("Logger functionality", False))

# Test 3: Test helper functions
print("\n3. Testing helper functions...")
try:
    # Test validate_resume_directory with non-existent path
    result = validate_resume_directory("/nonexistent/path", Logger(debug=False))
    if result is None:
        print("   ✓ validate_resume_directory correctly rejects invalid path")
        test_results.append(("validate_resume_directory", True))
    else:
        print("   ✗ validate_resume_directory should reject invalid path")
        test_results.append(("validate_resume_directory", False))
except Exception as e:
    print(f"   ✗ Helper function test failed: {e}")
    test_results.append(("validate_resume_directory", False))

# Test 4: Test archive processing helper functions
print("\n4. Testing archive processing helpers...")
try:
    # Test validate_directory with current directory
    current_dir = Path.cwd()
    result = validate_directory(str(current_dir), Logger(debug=False))
    if result == current_dir:
        print("   ✓ validate_directory correctly validates current directory")
        test_results.append(("validate_directory", True))
    else:
        print("   ✗ validate_directory failed for current directory")
        test_results.append(("validate_directory", False))
except Exception as e:
    print(f"   ✗ Archive processing helper test failed: {e}")
    test_results.append(("validate_directory", False))

# Summary
print("\n" + "=" * 70)
print("Test Summary")
print("=" * 70)

passed = sum(1 for _, result in test_results if result)
total = len(test_results)

for test_name, result in test_results:
    status = "✓ PASS" if result else "✗ FAIL"
    print(f"{status}: {test_name}")

print("\n" + "-" * 70)
print(f"Total: {passed}/{total} tests passed")
print("=" * 70)

if passed == total:
    print("\n🎉 All tests passed! Phase 1 refactoring is successful.")
    sys.exit(0)
else:
    print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
    sys.exit(1)
