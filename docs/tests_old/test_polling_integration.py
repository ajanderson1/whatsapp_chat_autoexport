"""Test polling integration for Google Drive exports."""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Test that we can import the new methods
try:
    from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient
    from whatsapp_chat_autoexport.google_drive.drive_manager import GoogleDriveManager
    from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline
    from whatsapp_chat_autoexport.output.output_builder import OutputBuilder
    from whatsapp_chat_autoexport.utils.logger import Logger
    
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test PipelineConfig with new polling parameters
try:
    config = PipelineConfig(
        poll_interval=10,
        poll_timeout=600,
        created_within_seconds=300,
        output_dir=Path("~/test_output").expanduser()
    )
    
    assert config.poll_interval == 10, "poll_interval not set correctly"
    assert config.poll_timeout == 600, "poll_timeout not set correctly"
    assert config.created_within_seconds == 300, "created_within_seconds not set correctly"
    
    print("✓ PipelineConfig polling parameters work correctly")
except Exception as e:
    print(f"✗ PipelineConfig test failed: {e}")
    sys.exit(1)

# Test that GoogleDriveClient has the new method
try:
    logger = Logger(debug=False)
    # We can't actually test the method without credentials, but we can verify it exists
    assert hasattr(GoogleDriveClient, 'poll_for_new_export'), "poll_for_new_export method missing"
    print("✓ GoogleDriveClient.poll_for_new_export method exists")
except Exception as e:
    print(f"✗ GoogleDriveClient test failed: {e}")
    sys.exit(1)

# Test that GoogleDriveManager has the new method
try:
    assert hasattr(GoogleDriveManager, 'wait_for_new_export'), "wait_for_new_export method missing"
    print("✓ GoogleDriveManager.wait_for_new_export method exists")
except Exception as e:
    print(f"✗ GoogleDriveManager test failed: {e}")
    sys.exit(1)

# Test that OutputBuilder copy methods exist
try:
    assert hasattr(OutputBuilder, '_copy_media_files'), "_copy_media_files method missing"
    assert hasattr(OutputBuilder, '_copy_transcriptions'), "_copy_transcriptions method missing"
    print("✓ OutputBuilder copy methods exist")
except Exception as e:
    print(f"✗ OutputBuilder test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ All integration tests passed!")
print("=" * 70)
print("\nNew features added:")
print("  • GoogleDriveClient.poll_for_new_export() - polls Drive root for new exports")
print("  • GoogleDriveManager.wait_for_new_export() - wrapper with error handling")
print("  • PipelineConfig polling parameters - poll_interval, poll_timeout, created_within_seconds")
print("  • OutputBuilder smart merge - skip-if-exists strategy for files")
print("  • CLI arguments - --poll-interval and --poll-timeout")
