"""
Integration tests for the unified `whatsapp` CLI.

Tests the command-line surface of the unified entry point (cli_entry.py) via
subprocess. Also smoke-tests the deprecation wrappers so the legacy scripts
(whatsapp-export etc.) keep exiting cleanly with a migration notice.
"""

import subprocess

import pytest


def _run(args, timeout=15):
    """Run the `whatsapp` command (via poetry run) with the given args."""
    return subprocess.run(
        ["poetry", "run", "whatsapp", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# -----------------------------------------------------------------------------
# `whatsapp --help` surface
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_help_shows_usage():
    """`whatsapp --help` shows usage information and exits 0."""
    result = _run(["--help"])
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"--help should exit 0, got {result.returncode}"
    assert "usage" in output.lower() or "options" in output.lower() or "whatsapp" in output.lower()


@pytest.mark.integration
@pytest.mark.parametrize(
    "flag",
    [
        "--debug",
        "--limit",
        "--headless",
        "--pipeline-only",
        "--without-media",
        "--no-output-media",
        "--no-transcribe",
        "--force-transcribe",
        "--resume",
        "--wireless-adb",
        "--transcription-provider",
        "--skip-drive-download",
        "--auto-select",
        "--delete-from-drive",
        "--output",
    ],
)
def test_help_documents_flag(flag):
    """All unified-CLI flags documented in CLAUDE.md appear in `whatsapp --help`."""
    result = _run(["--help"])
    output = result.stdout + result.stderr
    assert flag in output, f"Expected {flag!r} in `whatsapp --help` output"


# -----------------------------------------------------------------------------
# Invalid invocations fail with a helpful message
# -----------------------------------------------------------------------------


@pytest.mark.integration
def test_headless_without_output_exits_with_error():
    """`whatsapp --headless` without `--output` should fail and mention the missing arg."""
    result = _run(["--headless"])
    output = (result.stdout + result.stderr).lower()
    assert result.returncode != 0, "Expected non-zero exit for --headless without --output"
    assert "output" in output or "required" in output or "error" in output


# -----------------------------------------------------------------------------
# Deprecated subprocess commands still exit cleanly with a migration notice
# -----------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "deprecated_cmd",
    ["whatsapp-export", "whatsapp-process", "whatsapp-pipeline", "whatsapp-drive", "whatsapp-logs"],
)
def test_deprecated_command_prints_migration_notice(deprecated_cmd):
    """Deprecated entry points exit cleanly with a migration hint pointing to `whatsapp`."""
    result = subprocess.run(
        ["poetry", "run", deprecated_cmd, "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = result.stdout + result.stderr
    # Must mention either 'deprecated' or the new unified command.
    assert "deprecated" in output.lower() or "whatsapp --" in output, (
        f"{deprecated_cmd} should print migration/deprecation notice; got: {output[:300]!r}"
    )
