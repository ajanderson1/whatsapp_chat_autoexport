"""
Integration tests for the ``whatsapp-ingest`` command.

Each test creates a mock Appium export directory structure and an output
directory, then exercises the ingest flow programmatically via
``run_ingest``. No subprocesses are spawned.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.cli.commands.ingest import run_ingest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 26, 14, 0, 0)
_YESTERDAY = _NOW - timedelta(days=1)


def _write_appium_transcript(chat_dir: Path, messages: list[tuple[str, str, str]]):
    """
    Create a mock Appium export transcript file.

    ``messages`` is a list of (timestamp_str, sender, content) tuples.
    The timestamp_str should be in WhatsApp US format: ``M/D/YY, H:MM AM/PM``.
    """
    chat_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for ts, sender, content in messages:
        lines.append(f"{ts} - {sender}: {content}")
    transcript = chat_dir / f"WhatsApp Chat with {chat_dir.name}.txt"
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_existing_vault_transcript(chat_dir: Path, messages: list[tuple[str, str, str]]):
    """
    Create an existing v2 transcript.md in the vault output directory.

    ``messages`` is a list of (date_str, time_str, content_line) tuples
    where content_line is a fully formatted ``[HH:MM] Sender: content``.
    """
    chat_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "cssclasses:",
        "  - whatsapp-transcript",
        "  - exclude-from-graph",
        "---",
        "",
        "<!-- TRANSCRIPT METADATA",
        f"chat_jid: {chat_dir.name}",
        f"contact: {chat_dir.name}",
        "generated: 2026-03-25T12:00:00Z",
        "generator: wa-sync/1.0.0",
        "message_count: 0",
        "media_count: 0",
        "date_range: none",
        "body_sha256: abc123",
        "-->",
        "",
    ]
    current_date = None
    for date_str, time_str, content in messages:
        if date_str != current_date:
            if current_date is not None:
                lines.append("")
            lines.append(f"## {date_str}")
            lines.append("")
            current_date = date_str
        lines.append(f"[{time_str}] {content}")

    transcript = chat_dir / "transcript.md"
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def appium_export(tmp_path):
    """Create a mock Appium export directory with two chats."""
    export_dir = tmp_path / "appium_export"
    export_dir.mkdir()

    _write_appium_transcript(export_dir / "Alice Smith", [
        ("3/25/26, 2:00 PM", "Alice Smith", "Hello!"),
        ("3/25/26, 2:01 PM", "Me", "Hi Alice!"),
        ("3/26/26, 2:00 PM", "Alice Smith", "How are you?"),
    ])

    _write_appium_transcript(export_dir / "Bob Jones", [
        ("3/25/26, 3:00 PM", "Bob Jones", "Hey!"),
        ("3/25/26, 3:05 PM", "Me", "Hey Bob!"),
    ])

    return export_dir


@pytest.fixture
def output_dir(tmp_path):
    """Create the vault output directory."""
    out = tmp_path / "vault_output"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIngestFresh:
    """Test ingesting into an empty output directory."""

    def test_fresh_ingest_creates_transcripts(self, appium_export, output_dir):
        """Fresh ingest should create transcript.md + index.md for each chat."""
        summary = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )

        assert summary["success"] is True
        assert summary["chats_processed"] >= 1
        assert summary["chats_errored"] == 0

        # Check Alice's chat was created
        alice_dir = output_dir / "Alice Smith"
        assert (alice_dir / "transcript.md").exists()
        assert (alice_dir / "index.md").exists()

        # Check Bob's chat was created
        bob_dir = output_dir / "Bob Jones"
        assert (bob_dir / "transcript.md").exists()
        assert (bob_dir / "index.md").exists()

    def test_fresh_ingest_message_counts(self, appium_export, output_dir):
        """Summary should report correct message counts."""
        summary = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )

        assert summary["success"] is True
        assert summary["total_new_messages"] > 0

        # Find Alice's result
        alice_result = next(
            r for r in summary["chat_results"] if r["name"] == "Alice Smith"
        )
        assert alice_result["appium_messages"] == 3
        assert alice_result["existing_messages"] == 0

    def test_fresh_ingest_transcript_format(self, appium_export, output_dir):
        """Transcript should be in v2 format with frontmatter and day headers."""
        run_ingest(export_dir=appium_export, output_dir=output_dir)

        content = (output_dir / "Alice Smith" / "transcript.md").read_text()
        assert content.startswith("---\n")
        assert "cssclasses:" in content
        assert "## 2026-03-25" in content
        assert "Alice Smith:" in content


class TestIngestGapFill:
    """Test ingesting with existing vault transcripts (gap fill)."""

    def test_gap_fill_merges_messages(self, appium_export, output_dir):
        """Ingest should merge new Appium messages with existing vault data."""
        # Pre-populate vault with an existing transcript for Alice
        _write_existing_vault_transcript(output_dir / "Alice Smith", [
            ("2026-03-25", "14:00", "Alice Smith: Hello!"),
        ])

        summary = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )

        assert summary["success"] is True

        alice_result = next(
            r for r in summary["chat_results"] if r["name"] == "Alice Smith"
        )
        assert alice_result["existing_messages"] >= 1
        # Merged count should be >= appium messages (dedup might reduce)
        assert alice_result["merged_messages"] >= alice_result["appium_messages"]

    def test_gap_fill_reports_correctly(self, appium_export, output_dir):
        """Gap-filled chats should be counted in the summary."""
        _write_existing_vault_transcript(output_dir / "Alice Smith", [
            ("2026-03-24", "10:00", "Alice Smith: Old message"),
        ])

        summary = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )

        assert summary["success"] is True
        assert summary["chats_gap_filled"] >= 1


class TestIngestIdempotent:
    """Test that running ingest twice produces consistent results."""

    def test_idempotent_second_run(self, appium_export, output_dir):
        """Second ingest produces valid output without duplicating messages."""
        # First run
        summary1 = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )
        assert summary1["success"] is True
        first_count = summary1["chats_processed"]
        assert first_count >= 1

        # Second run — should still succeed
        summary2 = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
        )
        assert summary2["success"] is True

        # Verify no text message content is duplicated in the transcript
        # (media format differences between sources may cause media-line
        # count to vary, but text messages must not duplicate)
        for chat_dir in output_dir.iterdir():
            transcript = chat_dir / "transcript.md"
            if not transcript.is_file():
                continue
            lines = transcript.read_text().splitlines()
            # Extract text message lines (have [HH:MM] prefix, contain sender, no media tag)
            text_msgs = [l for l in lines
                         if l.startswith("[") and ": " in l
                         and not any(tag in l for tag in ["<photo>", "<video>", "<voice>",
                                                          "<document>", "<sticker>", "<media>"])]
            # No text message should appear twice
            assert len(text_msgs) == len(set(text_msgs)), \
                f"Duplicate text messages found in {chat_dir.name}"


class TestIngestDryRun:
    """Test dry-run mode."""

    def test_dry_run_no_files_written(self, appium_export, output_dir):
        """Dry-run should not create any files."""
        summary = run_ingest(
            export_dir=appium_export,
            output_dir=output_dir,
            dry_run=True,
        )

        assert summary["success"] is True
        assert summary["dry_run"] is True
        assert summary["chats_processed"] >= 1

        # No files should have been created
        alice_dir = output_dir / "Alice Smith"
        assert not (alice_dir / "transcript.md").exists()


class TestIngestErrors:
    """Test error handling."""

    def test_missing_export_dir(self, tmp_path):
        """Should report error for missing export directory."""
        summary = run_ingest(
            export_dir=tmp_path / "nonexistent",
            output_dir=tmp_path / "output",
        )
        assert summary["success"] is False
        assert "not found" in summary["error"]

    def test_empty_export_dir(self, tmp_path):
        """Should report error for empty export directory."""
        export_dir = tmp_path / "empty_export"
        export_dir.mkdir()

        summary = run_ingest(
            export_dir=export_dir,
            output_dir=tmp_path / "output",
        )
        assert summary["success"] is False
        assert "No chats found" in summary["error"]
