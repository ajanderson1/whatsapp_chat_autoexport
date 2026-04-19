"""Integration test: full pipeline with --format spec produces correct output."""

import zipfile
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig


def _make_chat_zip(source_dir: Path, dest_dir: Path) -> Path:
    """
    Create a WhatsApp-style ZIP archive (no .zip extension) from *source_dir*.

    WhatsApp exports files to Google Drive without the .zip extension.  The
    pipeline's ``find_whatsapp_chat_files`` helper validates the magic bytes, so
    the file must be a valid ZIP even though it lacks the extension.

    The archive is written to *dest_dir* with the name
    ``WhatsApp Chat with Example`` (matching the sample fixture directory name).
    """
    zip_path = dest_dir / "WhatsApp Chat with Example"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.iterdir():
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.name)
    return zip_path


@pytest.mark.integration
@pytest.mark.slow
def test_pipeline_spec_format_produces_companion_notes(sample_export_dir, temp_output_dir):
    """Pipeline with output_format='spec' creates index.md + transcript.md."""
    # Create a working directory for the pipeline source (needs a ZIP file)
    source_dir = temp_output_dir / "source"
    source_dir.mkdir()
    _make_chat_zip(sample_export_dir, source_dir)

    output_dir = temp_output_dir / "output"
    output_dir.mkdir()

    config = PipelineConfig(
        skip_download=True,
        download_dir=source_dir,
        output_dir=output_dir,
        output_format="spec",
        include_media=False,
        include_transcriptions=True,
        transcribe_audio_video=False,
        cleanup_temp=False,
    )

    pipeline = WhatsAppPipeline(config)
    results = pipeline.run(source_dir=source_dir)

    assert results["success"], f"Pipeline failed with errors: {results.get('errors')}"

    # Find output directories (should be at least one contact folder)
    output_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
    assert len(output_dirs) > 0, f"No output directories created in {output_dir}"

    # Check the first output has the spec structure
    contact_dir = output_dirs[0]
    index_md = contact_dir / "index.md"
    transcript_md = contact_dir / "transcript.md"

    assert index_md.exists(), f"index.md missing in {contact_dir}"
    assert transcript_md.exists(), f"transcript.md missing in {contact_dir}"

    # Verify index.md has expected frontmatter fields
    index_content = index_md.read_text(encoding="utf-8")
    assert "type: note" in index_content, "index.md must contain 'type: note'"
    assert "whatsapp" in index_content, "index.md must reference 'whatsapp'"

    # Verify transcript.md uses spec format (frontmatter + day headers)
    transcript_content = transcript_md.read_text(encoding="utf-8")
    assert "cssclasses:" in transcript_content, "transcript.md must have cssclasses frontmatter"
    assert "whatsapp-transcript" in transcript_content, (
        "transcript.md must declare whatsapp-transcript cssclass"
    )
    assert "## 20" in transcript_content, (
        "transcript.md must contain day headers like '## 2017-07-26'"
    )

    # Verify legacy .txt transcript is NOT present
    assert not (contact_dir / "transcript.txt").exists(), (
        "spec format must not produce transcript.txt"
    )


@pytest.mark.integration
@pytest.mark.slow
def test_pipeline_legacy_format_unchanged(sample_export_dir, temp_output_dir):
    """Pipeline with default format still produces transcript.txt, not transcript.md."""
    # Create a working directory for the pipeline source (needs a ZIP file)
    source_dir = temp_output_dir / "source"
    source_dir.mkdir()
    _make_chat_zip(sample_export_dir, source_dir)

    output_dir = temp_output_dir / "output"
    output_dir.mkdir()

    config = PipelineConfig(
        skip_download=True,
        download_dir=source_dir,
        output_dir=output_dir,
        output_format="legacy",
        include_media=False,
        include_transcriptions=False,
        transcribe_audio_video=False,
        cleanup_temp=False,
    )

    pipeline = WhatsAppPipeline(config)
    results = pipeline.run(source_dir=source_dir)

    assert results["success"], f"Pipeline failed with errors: {results.get('errors')}"

    output_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
    assert len(output_dirs) > 0, f"No output directories created in {output_dir}"

    contact_dir = output_dirs[0]

    # Legacy format must produce transcript.txt
    assert (contact_dir / "transcript.txt").exists(), (
        f"Legacy format must produce transcript.txt in {contact_dir}"
    )

    # Legacy format must NOT produce spec companion files
    assert not (contact_dir / "transcript.md").exists(), (
        "Legacy format must not produce transcript.md"
    )
    assert not (contact_dir / "index.md").exists(), (
        "Legacy format must not produce index.md"
    )
