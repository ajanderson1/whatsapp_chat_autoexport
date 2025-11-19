#!/usr/bin/env python3
"""
Test CLI argument parsing for both export and processing commands.
"""

import sys
import subprocess

print("=" * 70)
print("Testing CLI Argument Parsing")
print("=" * 70)

tests_passed = 0
tests_total = 0

def run_test(description, command, expected_in_output=None, should_fail=False):
    """Run a CLI test and check output."""
    global tests_passed, tests_total
    tests_total += 1
    
    print(f"\n{tests_total}. {description}")
    print(f"   Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = result.stdout + result.stderr
        
        # Check if it should fail
        if should_fail:
            if result.returncode != 0:
                print(f"   ✓ Correctly failed as expected")
                tests_passed += 1
                return True
            else:
                print(f"   ✗ Should have failed but didn't")
                return False
        
        # Check for expected output
        if expected_in_output:
            if expected_in_output in output:
                print(f"   ✓ Found expected output: '{expected_in_output}'")
                tests_passed += 1
                return True
            else:
                print(f"   ✗ Expected output not found: '{expected_in_output}'")
                print(f"   Output: {output[:200]}")
                return False
        else:
            # Just check it didn't crash
            print(f"   ✓ Command executed (exit code: {result.returncode})")
            tests_passed += 1
            return True
            
    except subprocess.TimeoutExpired:
        print(f"   ✗ Command timed out")
        return False
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False

# Test whatsapp-export command
print("\n" + "=" * 70)
print("Testing whatsapp-export Command")
print("=" * 70)

run_test(
    "Help flag shows usage",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="WhatsApp Chat Auto-Export"
)

run_test(
    "Debug flag is recognized",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="--debug"
)

run_test(
    "Limit flag is recognized",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="--limit"
)

run_test(
    "Media flags are recognized",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="--with-media"
)

run_test(
    "Resume flag is recognized",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="--resume"
)

run_test(
    "Wireless ADB flag is recognized",
    ["poetry", "run", "whatsapp-export", "--help"],
    expected_in_output="--wireless-adb"
)

# Test whatsapp-process command
print("\n" + "=" * 70)
print("Testing whatsapp-process Command")
print("=" * 70)

run_test(
    "Help flag shows usage",
    ["poetry", "run", "whatsapp-process", "--help"],
    expected_in_output="WhatsApp Chat Processor"
)

run_test(
    "Debug flag is recognized",
    ["poetry", "run", "whatsapp-process", "--help"],
    expected_in_output="--debug"
)

run_test(
    "Transcripts directory flag is recognized",
    ["poetry", "run", "whatsapp-process", "--help"],
    expected_in_output="--transcripts-dir"
)

run_test(
    "Missing directory argument is caught",
    ["poetry", "run", "whatsapp-process"],
    expected_in_output="required",
    should_fail=True
)

# Summary
print("\n" + "=" * 70)
print("Test Summary")
print("=" * 70)
print(f"Passed: {tests_passed}/{tests_total} tests")
print("=" * 70)

if tests_passed == tests_total:
    print("\n🎉 All CLI argument tests passed!")
    sys.exit(0)
else:
    print(f"\n⚠️  {tests_total - tests_passed} test(s) failed")
    sys.exit(1)
