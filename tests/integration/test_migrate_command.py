"""
Integration tests for the ``whatsapp-migrate`` command.

Each test creates old-format transcript.txt files in a temporary
directory structure and exercises the migration flow programmatically
via ``run_migrate``. No subprocesses are spawned.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.cli.commands.migrate import run_migrate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_US_FORMAT_MESSAGES = [
    ("3/25/26, 2:00 PM", "Alice Smith", "Hello!"),
    ("3/25/26, 2:01 PM", "Me", "Hi Alice!"),
    ("3/25/26, 2:05 PM", "Alice Smith", "How are you?"),
    ("3/26/26, 10:00 AM", "Alice Smith", "Good morning!"),
    ("3/26/26, 10:01 AM", "Me", "Morning!"),
]

_BOB_MESSAGES = [
    ("3/25/26, 3:00 PM", "Bob Jones", "Hey!"),
    ("3/25/26, 3:05 PM", "Me", "Hey Bob!"),
]


def _write_legacy_transcript(
    path: Path,
    messages: list[tuple[str, str, str]],
):
    """
    Write a legacy WhatsApp transcript.txt file.

    ``messages`` is a list of (timestamp_str, sender, content) tuples.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for ts, sender, content in messages:
        lines.append(f"{ts} - {sender}: {content}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def legacy_vault(tmp_path):
    """Create a vault directory with legacy transcript.txt files (nested layout)."""
    vault_dir = tmp_path / "vault_whatsapp"
    vault_dir.mkdir()

    # Alice: nested layout
    _write_legacy_transcript(
        vault_dir / "Alice Smith" / "transcript.txt",
        _US_FORMAT_MESSAGES,
    )

    # Bob: nested layout
    _write_legacy_transcript(
        vault_dir / "Bob Jones" / "transcript.txt",
        _BOB_MESSAGES,
    )

    return vault_dir


@pytest.fixture
def legacy_vault_flat(tmp_path):
    """Create a vault directory with legacy transcript.txt files (flat layout)."""
    vault_dir = tmp_path / "vault_whatsapp_flat"
    vault_dir.mkdir()

    # Write a flat .txt file
    _write_legacy_transcript(
        vault_dir / "Alice Smith.txt",
        _US_FORMAT_MESSAGES,
    )

    return vault_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMigrateBasic:
    """Test basic migration from legacy to v2 format."""

    def test_migration_creates_md_files(self, legacy_vault):
        """Migration should create transcript.md + index.md for each chat."""
        summary = run_migrate(input_dir=legacy_vault)

        assert summary["success"] is True
        assert summary["chats_migrated"] >= 2
        assert summary["chats_errored"] == 0

        # Check Alice
        alice_dir = legacy_vault / "Alice Smith"
        assert (alice_dir / "transcript.md").exists()
        assert (alice_dir / "index.md").exists()

        # Check Bob
        bob_dir = legacy_vault / "Bob Jones"
        assert (bob_dir / "transcript.md").exists()
        assert (bob_dir / "index.md").exists()

    def test_migration_transcript_format(self, legacy_vault):
        """Migrated transcript should be in v2 format."""
        run_migrate(input_dir=legacy_vault)

        content = (legacy_vault / "Alice Smith" / "transcript.md").read_text()
        assert content.startswith("---\n")
        assert "cssclasses:" in content
        assert "whatsapp-transcript" in content
        # Should have day headers
        assert "## 2026-03-25" in content
        assert "## 2026-03-26" in content

    def test_migration_index_format(self, legacy_vault):
        """Migrated index.md should have proper frontmatter."""
        run_migrate(input_dir=legacy_vault)

        content = (legacy_vault / "Alice Smith" / "index.md").read_text()
        assert content.startswith("---\n")
        assert "type: note" in content
        assert "whatsapp" in content
        assert "migration" in content


class TestMigrateBackup:
    """Test backup behaviour during migration."""

    def test_backup_created_by_default(self, legacy_vault):
        """Original transcript.txt should be backed up as .txt.bak."""
        run_migrate(input_dir=legacy_vault)

        alice_dir = legacy_vault / "Alice Smith"
        assert (alice_dir / "transcript.txt.bak").exists()
        # Original should still exist (we copy, not move)
        assert (alice_dir / "transcript.txt").exists()

    def test_no_backup_flag(self, legacy_vault):
        """--no-backup should skip creating .bak files."""
        run_migrate(input_dir=legacy_vault, no_backup=True)

        alice_dir = legacy_vault / "Alice Smith"
        assert not (alice_dir / "transcript.txt.bak").exists()
        # Original should still exist
        assert (alice_dir / "transcript.txt").exists()


class TestMigrateMessageCount:
    """Test that message counts match between old and new formats."""

    def test_message_count_matches(self, legacy_vault):
        """Old and new format should have the same message count."""
        summary = run_migrate(input_dir=legacy_vault)

        assert summary["success"] is True

        alice_result = next(
            r for r in summary["chat_results"] if r["name"] == "Alice Smith"
        )
        assert alice_result["old_message_count"] == len(_US_FORMAT_MESSAGES)
        assert alice_result["counts_match"] is True

    def test_total_messages_in_summary(self, legacy_vault):
        """Summary should report total migrated message count."""
        summary = run_migrate(input_dir=legacy_vault)

        assert summary["total_messages"] == (
            len(_US_FORMAT_MESSAGES) + len(_BOB_MESSAGES)
        )


class TestMigrateDryRun:
    """Test dry-run mode."""

    def test_dry_run_no_files_written(self, legacy_vault):
        """Dry-run should not create any new files."""
        summary = run_migrate(input_dir=legacy_vault, dry_run=True)

        assert summary["success"] is True
        assert summary["dry_run"] is True
        assert summary["chats_migrated"] >= 2

        # No .md files should have been created
        alice_dir = legacy_vault / "Alice Smith"
        assert not (alice_dir / "transcript.md").exists()
        assert not (alice_dir / "index.md").exists()
        # No backup should exist either
        assert not (alice_dir / "transcript.txt.bak").exists()


class TestMigrateErrors:
    """Test error handling."""

    def test_missing_input_dir(self, tmp_path):
        """Should report error for missing input directory."""
        summary = run_migrate(input_dir=tmp_path / "nonexistent")
        assert summary["success"] is False
        assert "not found" in summary["error"]

    def test_no_legacy_files(self, tmp_path):
        """Should report error when no legacy transcripts found."""
        empty_dir = tmp_path / "empty_vault"
        empty_dir.mkdir()

        summary = run_migrate(input_dir=empty_dir)
        assert summary["success"] is False
        assert "No legacy" in summary["error"]

    def test_empty_transcript(self, tmp_path):
        """Empty transcript.txt should be reported as empty."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        chat_dir = vault_dir / "Empty Chat"
        chat_dir.mkdir()
        (chat_dir / "transcript.txt").write_text("", encoding="utf-8")

        summary = run_migrate(input_dir=vault_dir)
        # Should succeed overall (empty is not an error)
        assert summary["chats_empty"] >= 1
