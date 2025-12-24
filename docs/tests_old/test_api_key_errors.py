#!/usr/bin/env python3
"""
Test script to verify improved API key error messages.
Run this without setting API keys to see the helpful error messages.
"""

import os
import sys
from pathlib import Path

# Add the package to the path
sys.path.insert(0, str(Path(__file__).parent))

from whatsapp_chat_autoexport.transcription.whisper_transcriber import WhisperTranscriber
from whatsapp_chat_autoexport.transcription.elevenlabs_transcriber import ElevenLabsTranscriber


class SimpleLogger:
    """Simple logger that prints to stdout."""

    def info(self, msg):
        print(f"INFO: {msg}")

    def error(self, msg):
        print(f"ERROR: {msg}")

    def warning(self, msg):
        print(f"WARNING: {msg}")

    def success(self, msg):
        print(f"SUCCESS: {msg}")

    def debug(self, msg):
        print(f"DEBUG: {msg}")


def test_whisper_missing_key():
    """Test Whisper transcriber without API key."""
    print("=" * 70)
    print("Testing Whisper Transcriber (no API key)")
    print("=" * 70)

    # Temporarily remove the API key if it exists
    old_key = os.environ.pop('OPENAI_API_KEY', None)

    try:
        logger = SimpleLogger()
        transcriber = WhisperTranscriber(logger=logger)

        if transcriber.is_available():
            print("❌ FAIL: Transcriber should NOT be available without API key")
        else:
            print("\n✅ PASS: Transcriber correctly reports as unavailable")

    finally:
        # Restore the key if it was set
        if old_key:
            os.environ['OPENAI_API_KEY'] = old_key

    print()


def test_elevenlabs_missing_key():
    """Test ElevenLabs transcriber without API key."""
    print("=" * 70)
    print("Testing ElevenLabs Transcriber (no API key)")
    print("=" * 70)

    # Temporarily remove the API key if it exists
    old_key = os.environ.pop('ELEVENLABS_API_KEY', None)

    try:
        logger = SimpleLogger()
        transcriber = ElevenLabsTranscriber(logger=logger)

        if transcriber.is_available():
            print("❌ FAIL: Transcriber should NOT be available without API key")
        else:
            print("\n✅ PASS: Transcriber correctly reports as unavailable")

    finally:
        # Restore the key if it was set
        if old_key:
            os.environ['ELEVENLABS_API_KEY'] = old_key

    print()


def main():
    """Run all tests."""
    print("\n")
    print("=" * 70)
    print("Testing API Key Error Messages")
    print("=" * 70)
    print("\nYou should see helpful error messages below about missing API keys.\n")

    test_whisper_missing_key()
    test_elevenlabs_missing_key()

    print("=" * 70)
    print("Test Complete!")
    print("=" * 70)
    print("\nIf you saw clear error messages with instructions on how to")
    print("set the API keys, then the improvements are working correctly!")
    print()


if __name__ == "__main__":
    main()
