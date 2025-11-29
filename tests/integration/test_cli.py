"""
Test suite for CLI argument parsing.

Tests CLI commands using subprocess to verify argument handling.
"""

import subprocess

import pytest


@pytest.mark.integration
def test_export_help_shows_usage():
    """Test that export help flag shows usage information."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "WhatsApp Chat Auto-Export" in output or "usage" in output.lower()


@pytest.mark.integration
def test_export_debug_flag_recognized():
    """Test that export debug flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "--debug" in output, "Debug flag should be documented in help"


@pytest.mark.integration
def test_export_limit_flag_recognized():
    """Test that export limit flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "--limit" in output, "Limit flag should be documented in help"


@pytest.mark.integration
def test_export_media_flags_recognized():
    """Test that export media flags are recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert (
        "--with-media" in output or "--without-media" in output
    ), "Media flags should be documented in help"


@pytest.mark.integration
def test_export_resume_flag_recognized():
    """Test that export resume flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "--resume" in output, "Resume flag should be documented in help"


@pytest.mark.integration
def test_export_wireless_adb_flag_recognized():
    """Test that export wireless ADB flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "--wireless-adb" in output, "Wireless ADB flag should be documented in help"


@pytest.mark.integration
def test_process_help_shows_usage():
    """Test that process help flag shows usage information."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-process", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert (
        "WhatsApp Chat Processor" in output or "usage" in output.lower()
    ), "Help should show usage information"


@pytest.mark.integration
def test_process_debug_flag_recognized():
    """Test that process debug flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-process", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "--debug" in output, "Debug flag should be documented in help"


@pytest.mark.integration
def test_process_transcripts_dir_flag_recognized():
    """Test that process transcripts directory flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-process", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert (
        "--transcripts-dir" in output or "transcripts" in output.lower()
    ), "Transcripts directory flag should be documented"


@pytest.mark.integration
def test_process_missing_directory_argument():
    """Test that process command catches missing directory argument."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-process"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr

    # Should fail with non-zero exit code
    assert result.returncode != 0, "Should fail when directory argument is missing"

    # Should mention required argument
    assert (
        "required" in output.lower() or "error" in output.lower()
    ), "Error message should mention missing required argument"


@pytest.mark.integration
def test_pipeline_help_shows_usage():
    """Test that pipeline help flag shows usage information."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-pipeline", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert "usage" in output.lower() or "pipeline" in output.lower()


@pytest.mark.integration
def test_pipeline_transcription_provider_flag():
    """Test that pipeline transcription provider flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-pipeline", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert (
        "--transcription-provider" in output or "transcription" in output.lower()
    ), "Transcription provider flag should be documented"


@pytest.mark.integration
def test_pipeline_no_transcribe_flag():
    """Test that pipeline no-transcribe flag is recognized."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-pipeline", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = result.stdout + result.stderr
    assert (
        "--no-transcribe" in output or "transcribe" in output.lower()
    ), "No-transcribe flag should be documented"


@pytest.mark.integration
@pytest.mark.slow
def test_export_version_info():
    """Test that export command provides version or package information."""
    result = subprocess.run(
        ["poetry", "run", "whatsapp-export", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Should not crash and should return help text
    assert result.returncode == 0, "Help command should succeed"
    assert len(result.stdout) > 0, "Should output help text"
