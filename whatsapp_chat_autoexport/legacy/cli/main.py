"""
Main CLI entry point for WhatsApp Chat Auto-Export.

Provides a unified command interface with subcommands for:
- export: Export chats from WhatsApp to Google Drive
- process: Process exported files (download, extract, transcribe)
- wizard: Interactive step-by-step workflow
"""

from typing import Optional
from pathlib import Path

import typer
from rich.console import Console

from .commands import export, process, wizard

# Create main app
app = typer.Typer(
    name="whatsapp",
    help="WhatsApp Chat Auto-Export - Export and process WhatsApp chats",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Add subcommands
app.add_typer(export.app, name="export")
app.add_typer(process.app, name="process")
app.add_typer(wizard.app, name="wizard")

# Console for output
console = Console()


@app.callback()
def callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        is_eager=True,
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug output",
    ),
) -> None:
    """
    WhatsApp Chat Auto-Export CLI.

    Export WhatsApp chats from Android devices and process them
    with transcription and organization.
    """
    if version:
        from importlib.metadata import version as get_version

        try:
            v = get_version("whatsapp-chat-autoexport")
        except Exception:
            v = "2.0.0-dev"

        console.print(f"[bold cyan]WhatsApp Chat Auto-Export[/] version [green]{v}[/]")
        raise typer.Exit()


@app.command()
def status() -> None:
    """
    Show current export status.

    Displays information about:
    - Active exports
    - Checkpoint availability
    - Device connection status
    """
    from whatsapp_chat_autoexport.state import CheckpointManager

    console.print("\n[bold]WhatsApp Export Status[/]\n")

    # Check for checkpoints
    checkpoint = CheckpointManager()
    info = checkpoint.get_checkpoint_info()

    if info["count"] > 0:
        console.print(f"[green]✓[/] Found {info['count']} checkpoint(s)")
        console.print(f"  Latest: {info['latest']}")
        console.print(f"  Time: {info['latest_time']}")
    else:
        console.print("[dim]No checkpoints found[/]")

    console.print()


@app.command()
def resume(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for processed files",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without executing",
    ),
) -> None:
    """
    Resume from the last checkpoint.

    Continues an interrupted export from where it left off.
    """
    from whatsapp_chat_autoexport.state import CheckpointManager

    console.print("\n[bold]Resuming Export[/]\n")

    checkpoint = CheckpointManager()

    if not checkpoint.has_checkpoint():
        console.print("[red]✗[/] No checkpoint found to resume from")
        console.print("[dim]Start a new export with: whatsapp export[/]")
        raise typer.Exit(1)

    session = checkpoint.load_latest()

    if session is None:
        console.print("[red]✗[/] Failed to load checkpoint")
        raise typer.Exit(1)

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")
        console.print(f"Would resume session: {session.session_id}")
        console.print(f"Total chats: {session.total_chats}")
        console.print(f"Completed: {session.completed_chats}")
        console.print(f"Remaining: {session.pending_chats}")
        return

    # TODO: Implement actual resume logic
    console.print(f"Resuming session: {session.session_id}")
    console.print(f"Chats remaining: {session.pending_chats}")


@app.command()
def clean() -> None:
    """
    Clean up temporary files and checkpoints.

    Removes:
    - Old checkpoint files
    - Temporary extraction directories
    - Cache files
    """
    from whatsapp_chat_autoexport.state import CheckpointManager

    console.print("\n[bold]Cleaning Up[/]\n")

    # Clean checkpoints
    checkpoint = CheckpointManager()
    info = checkpoint.get_checkpoint_info()

    if info["count"] > 0:
        checkpoint.clear()
        console.print(f"[green]✓[/] Removed {info['count']} checkpoint(s)")
    else:
        console.print("[dim]No checkpoints to clean[/]")

    console.print("\n[green]Cleanup complete[/]\n")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
