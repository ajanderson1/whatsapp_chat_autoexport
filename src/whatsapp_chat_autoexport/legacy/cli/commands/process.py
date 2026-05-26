"""
Process command for WhatsApp Chat Auto-Export.

Processes exported WhatsApp files through the pipeline:
download, extract, transcribe, and build output.
"""

from typing import Optional
from pathlib import Path
from enum import Enum

import typer
from rich.console import Console

app = typer.Typer(
    name="process",
    help="Process exported WhatsApp files",
    no_args_is_help=True,
)

console = Console()


class TranscriptionProvider(str, Enum):
    """Transcription service provider."""

    whisper = "whisper"
    elevenlabs = "elevenlabs"


@app.callback(invoke_without_command=True)
def process_main(
    ctx: typer.Context,
    input_dir: Path = typer.Argument(
        ...,
        help="Input directory with exported files",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    output_dir: Path = typer.Argument(
        ...,
        help="Output directory for processed files",
    ),
    no_media: bool = typer.Option(
        False,
        "--no-media",
        help="Exclude media from final output (still used for transcription)",
    ),
    no_transcribe: bool = typer.Option(
        False,
        "--no-transcribe",
        help="Skip audio/video transcription",
    ),
    force_transcribe: bool = typer.Option(
        False,
        "--force-transcribe",
        help="Re-transcribe even if transcriptions exist",
    ),
    provider: TranscriptionProvider = typer.Option(
        TranscriptionProvider.whisper,
        "--transcription-provider",
        "-p",
        help="Transcription service provider",
    ),
    skip_drive_download: bool = typer.Option(
        False,
        "--skip-drive-download",
        help="Skip Google Drive download (process local files only)",
    ),
    delete_from_drive: bool = typer.Option(
        False,
        "--delete-from-drive",
        help="Delete from Google Drive after processing",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without executing",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
) -> None:
    """
    Process exported WhatsApp files.

    Runs the processing pipeline:
    1. Download from Google Drive (unless --skip-drive-download)
    2. Extract and organize archives
    3. Transcribe audio/video files (unless --no-transcribe)
    4. Build final output structure
    5. Cleanup temporary files
    """
    if ctx.invoked_subcommand is not None:
        return

    console.print("\n[bold cyan]WhatsApp Processing Pipeline[/]\n")

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")
        _show_process_plan(
            input_dir=input_dir,
            output_dir=output_dir,
            no_media=no_media,
            no_transcribe=no_transcribe,
            force_transcribe=force_transcribe,
            provider=provider,
            skip_drive_download=skip_drive_download,
        )
        return

    # Show configuration
    console.print("[bold]Configuration:[/]")
    console.print(f"  Input: {input_dir}")
    console.print(f"  Output: {output_dir}")
    console.print(f"  Download from Drive: {not skip_drive_download}")
    console.print(f"  Transcription: {not no_transcribe}")
    if not no_transcribe:
        console.print(f"  Provider: {provider.value}")
        console.print(f"  Force re-transcribe: {force_transcribe}")
    console.print(f"  Output media: {not no_media}")
    if delete_from_drive:
        console.print(f"  Delete from Drive: yes")
    console.print()

    # TODO: Connect to actual pipeline
    console.print("[yellow]Pipeline will be connected in Task 8[/]")
    console.print("[dim]Use 'poetry run whatsapp-pipeline' for now[/]")


def _show_process_plan(
    input_dir: Path,
    output_dir: Path,
    no_media: bool,
    no_transcribe: bool,
    force_transcribe: bool,
    provider: TranscriptionProvider,
    skip_drive_download: bool,
) -> None:
    """Show what the process would do."""
    console.print("[bold]Processing Plan:[/]\n")

    phase = 1

    # Download
    if not skip_drive_download:
        console.print(f"{phase}. [cyan]Download from Google Drive[/]")
        console.print(f"   → To: {input_dir}")
        phase += 1
    else:
        console.print(f"[dim]{phase}. Download skipped[/]")
        phase += 1

    # Extract
    console.print(f"\n{phase}. [cyan]Extract and organize[/]")
    console.print(f"   → From: {input_dir}")
    phase += 1

    # Transcribe
    if not no_transcribe:
        console.print(f"\n{phase}. [cyan]Transcribe audio/video[/]")
        console.print(f"   → Provider: {provider.value}")
        if force_transcribe:
            console.print("   → Force re-transcribe: yes")
    else:
        console.print(f"\n[dim]{phase}. Transcription skipped[/]")
    phase += 1

    # Build output
    console.print(f"\n{phase}. [cyan]Build final output[/]")
    console.print(f"   → Output: {output_dir}")
    console.print(f"   → Media: {'excluded' if no_media else 'included'}")
    phase += 1

    # Cleanup
    console.print(f"\n{phase}. [cyan]Cleanup temporary files[/]")

    console.print()


@app.command()
def download(
    output_dir: Path = typer.Argument(
        ...,
        help="Directory to download files to",
    ),
    pattern: str = typer.Option(
        "WhatsApp Chat with *",
        "--pattern",
        help="File name pattern to match",
    ),
    delete_after: bool = typer.Option(
        False,
        "--delete-after",
        help="Delete from Drive after download",
    ),
) -> None:
    """
    Download exported files from Google Drive.

    Downloads WhatsApp export files matching the pattern.
    """
    console.print("\n[bold]Downloading from Google Drive...[/]\n")

    console.print(f"Pattern: {pattern}")
    console.print(f"Output: {output_dir}")

    # TODO: Implement download
    console.print("\n[yellow]Download will be connected in Task 8[/]")


@app.command()
def extract(
    input_dir: Path = typer.Argument(
        ...,
        help="Directory with exported zip files",
        exists=True,
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (defaults to input_dir/extracted)",
    ),
) -> None:
    """
    Extract exported zip files.

    Extracts and organizes WhatsApp export archives.
    """
    console.print("\n[bold]Extracting archives...[/]\n")

    output = output_dir or input_dir / "extracted"
    console.print(f"Input: {input_dir}")
    console.print(f"Output: {output}")

    # TODO: Implement extraction
    console.print("\n[yellow]Extraction will be connected in Task 8[/]")


@app.command()
def transcribe(
    input_dir: Path = typer.Argument(
        ...,
        help="Directory with media files to transcribe",
        exists=True,
    ),
    provider: TranscriptionProvider = typer.Option(
        TranscriptionProvider.whisper,
        "--provider",
        "-p",
        help="Transcription service provider",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Re-transcribe even if transcriptions exist",
    ),
) -> None:
    """
    Transcribe audio and video files.

    Creates transcription text files alongside media files.
    """
    console.print("\n[bold]Transcribing media files...[/]\n")

    console.print(f"Input: {input_dir}")
    console.print(f"Provider: {provider.value}")
    console.print(f"Force: {force}")

    # TODO: Implement transcription
    console.print("\n[yellow]Transcription will be connected in Task 8[/]")
