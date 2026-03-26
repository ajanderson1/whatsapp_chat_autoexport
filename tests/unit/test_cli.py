"""
Tests for CLI package.

Tests cover:
- Main CLI entry point
- Export command
- Process command
- Wizard command
"""

import pytest
from typer.testing import CliRunner

from whatsapp_chat_autoexport.legacy.cli.main import app


runner = CliRunner()


# =============================================================================
# Main CLI Tests
# =============================================================================


class TestMainCLI:
    """Tests for main CLI entry point."""

    def test_help(self):
        """Test --help option."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "WhatsApp Chat Auto-Export" in result.output
        assert "export" in result.output
        assert "process" in result.output
        assert "wizard" in result.output

    def test_version_in_help(self):
        """Test that --version option is listed in help."""
        result = runner.invoke(app, ["--help"])

        # Version option should be listed
        assert result.exit_code == 0
        assert "--version" in result.output

    def test_status_command(self):
        """Test status command."""
        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Status" in result.output

    def test_clean_command(self):
        """Test clean command."""
        result = runner.invoke(app, ["clean"])

        assert result.exit_code == 0
        assert "Cleaning" in result.output or "Cleanup" in result.output


# =============================================================================
# Export Command Tests
# =============================================================================


class TestExportCommand:
    """Tests for export command."""

    def test_export_help(self):
        """Test export --help."""
        result = runner.invoke(app, ["export", "--help"])

        assert result.exit_code == 0
        assert "Export chats from WhatsApp" in result.output

    def test_export_dry_run(self):
        """Test export with --dry-run."""
        result = runner.invoke(app, ["export", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_export_list_chats_help(self):
        """Test export list-chats --help."""
        result = runner.invoke(app, ["export", "list-chats", "--help"])

        assert result.exit_code == 0
        assert "List available chats" in result.output

    def test_export_verify_help(self):
        """Test export verify --help."""
        result = runner.invoke(app, ["export", "verify", "--help"])

        assert result.exit_code == 0
        assert "Verify device connection" in result.output

    def test_export_with_output(self):
        """Test export with --output option."""
        result = runner.invoke(app, ["export", "--output", "/tmp/test", "--dry-run"])

        assert result.exit_code == 0
        assert "/tmp/test" in result.output

    def test_export_with_limit(self):
        """Test export with --limit option."""
        result = runner.invoke(app, ["export", "--limit", "5", "--dry-run"])

        assert result.exit_code == 0
        assert "5" in result.output


# =============================================================================
# Process Command Tests
# =============================================================================


class TestProcessCommand:
    """Tests for process command."""

    def test_process_help(self):
        """Test process --help."""
        result = runner.invoke(app, ["process", "--help"])

        assert result.exit_code == 0
        assert "Process exported WhatsApp files" in result.output

    def test_process_requires_args(self):
        """Test that process requires arguments."""
        result = runner.invoke(app, ["process"])

        # Should fail without required arguments
        assert result.exit_code != 0

    def test_process_download_requires_dir(self):
        """Test process download requires output directory."""
        result = runner.invoke(app, ["process", "download"])

        # Should fail without required argument
        assert result.exit_code != 0

    def test_process_extract_requires_dir(self):
        """Test process extract requires input directory."""
        result = runner.invoke(app, ["process", "extract"])

        # Should fail without required argument
        assert result.exit_code != 0

    def test_process_transcribe_requires_dir(self):
        """Test process transcribe requires input directory."""
        result = runner.invoke(app, ["process", "transcribe"])

        # Should fail without required argument
        assert result.exit_code != 0


# =============================================================================
# Wizard Command Tests
# =============================================================================


class TestWizardCommand:
    """Tests for wizard command."""

    def test_wizard_help(self):
        """Test wizard --help."""
        result = runner.invoke(app, ["wizard", "--help"])

        assert result.exit_code == 0
        assert "Interactive export wizard" in result.output

    def test_wizard_dry_run(self):
        """Test wizard with --dry-run."""
        result = runner.invoke(app, ["wizard", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Step 1" in result.output
        assert "Step 2" in result.output

    def test_wizard_quick_help(self):
        """Test wizard quick --help."""
        result = runner.invoke(app, ["wizard", "quick", "--help"])

        assert result.exit_code == 0
        assert "Quick export" in result.output


# =============================================================================
# Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Integration tests for CLI."""

    def test_export_dry_run_full_flow(self):
        """Test full export dry run."""
        result = runner.invoke(
            app,
            [
                "export",
                "--output", "/tmp/test",
                "--limit", "5",
                "--without-media",
                "--no-transcribe",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "5" in result.output
        assert "excluded" in result.output.lower()

    def test_wizard_dry_run_shows_steps(self):
        """Test wizard dry run shows all steps."""
        result = runner.invoke(app, ["wizard", "--dry-run"])

        assert result.exit_code == 0
        assert "Welcome" in result.output
        assert "Device Connection" in result.output
        assert "Chat Selection" in result.output
        assert "Export Progress" in result.output
        assert "Summary" in result.output
