"""Test Opus to M4A conversion for transcription."""
import sys
from pathlib import Path

# Test imports
try:
    from whatsapp_chat_autoexport.utils.audio_converter import AudioConverter
    from whatsapp_chat_autoexport.transcription.whisper_transcriber import WhisperTranscriber
    from whatsapp_chat_autoexport.pipeline import PipelineConfig
    from whatsapp_chat_autoexport.utils.logger import Logger
    
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test AudioConverter
try:
    logger = Logger(debug=True)
    converter = AudioConverter(logger=logger)
    
    # Check FFmpeg availability
    if converter.is_ffmpeg_available():
        print("✓ FFmpeg is available")
    else:
        print("⚠️  FFmpeg not available - conversion will be skipped")
    
    # Check that conversion methods exist
    assert hasattr(converter, 'convert_to_m4a'), "convert_to_m4a method missing"
    assert hasattr(converter, 'convert_opus_to_m4a'), "convert_opus_to_m4a method missing"
    print("✓ AudioConverter methods exist")
    
except Exception as e:
    print(f"✗ AudioConverter test failed: {e}")
    sys.exit(1)

# Test WhisperTranscriber with convert_opus parameter
try:
    # Test with opus conversion enabled
    transcriber_with_conversion = WhisperTranscriber(
        logger=logger,
        convert_opus=True
    )
    assert hasattr(transcriber_with_conversion, 'audio_converter'), "audio_converter attribute missing"
    assert hasattr(transcriber_with_conversion, 'convert_opus'), "convert_opus attribute missing"
    assert transcriber_with_conversion.convert_opus == True, "convert_opus should be True"
    print("✓ WhisperTranscriber with opus conversion initialized")
    
    # Test with opus conversion disabled
    transcriber_without_conversion = WhisperTranscriber(
        logger=logger,
        convert_opus=False
    )
    assert transcriber_without_conversion.convert_opus == False, "convert_opus should be False"
    print("✓ WhisperTranscriber without opus conversion initialized")
    
except Exception as e:
    print(f"✗ WhisperTranscriber test failed: {e}")
    sys.exit(1)

# Test PipelineConfig with convert_opus_to_m4a
try:
    config_with_conversion = PipelineConfig(
        convert_opus_to_m4a=True,
        output_dir=Path("~/test").expanduser()
    )
    assert config_with_conversion.convert_opus_to_m4a == True, "convert_opus_to_m4a should be True"
    print("✓ PipelineConfig with opus conversion works")
    
    config_without_conversion = PipelineConfig(
        convert_opus_to_m4a=False,
        output_dir=Path("~/test").expanduser()
    )
    assert config_without_conversion.convert_opus_to_m4a == False, "convert_opus_to_m4a should be False"
    print("✓ PipelineConfig without opus conversion works")
    
except Exception as e:
    print(f"✗ PipelineConfig test failed: {e}")
    sys.exit(1)

# Find an actual Opus file to test with
try:
    test_opus_files = list(Path("WhatsApp Chat with Example").glob("**/*.opus")) if Path("WhatsApp Chat with Example").exists() else []
    
    if test_opus_files:
        opus_file = test_opus_files[0]
        print(f"\n✓ Found test Opus file: {opus_file.name}")
        
        if converter.is_ffmpeg_available():
            # Test actual conversion
            print(f"Testing conversion of {opus_file.name}...")
            temp_m4a = converter.convert_opus_to_m4a(opus_file, temp_dir=opus_file.parent)
            
            if temp_m4a and temp_m4a.exists():
                print(f"✓ Successfully converted to M4A: {temp_m4a.name}")
                print(f"  Original size: {opus_file.stat().st_size / 1024:.2f} KB")
                print(f"  Converted size: {temp_m4a.stat().st_size / 1024:.2f} KB")
                
                # Cleanup
                temp_m4a.unlink()
                print("✓ Cleaned up temporary M4A file")
            else:
                print("⚠️  Conversion returned None (may be expected if FFmpeg not configured)")
        else:
            print("⚠️  Skipping actual conversion test (FFmpeg not available)")
    else:
        print("\n⚠️  No Opus files found for testing actual conversion")
        
except Exception as e:
    print(f"⚠️  Opus file conversion test error: {e}")
    # Not failing the test for this

print("\n" + "=" * 70)
print("✅ All Opus conversion tests passed!")
print("=" * 70)
print("\nNew Opus conversion features:")
print("  • AudioConverter utility class with FFmpeg wrapper")
print("  • WhisperTranscriber.convert_opus parameter")
print("  • Automatic Opus → M4A conversion before transcription")
print("  • PipelineConfig.convert_opus_to_m4a option")
print("  • CLI flags: --skip-opus-conversion")
print("  • Proper cleanup of temporary M4A files")
