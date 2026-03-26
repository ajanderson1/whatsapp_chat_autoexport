"""
Wizard command for WhatsApp Chat Auto-Export.

Provides an interactive step-by-step workflow for the complete
export and processing pipeline.
"""

import sys
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="wizard",
    help="Interactive export wizard",
    no_args_is_help=False,
)

console = Console()


def _scan_adb_devices() -> List[Tuple[str, str]]:
    """
    Scan for connected ADB devices.

    Returns:
        List of (device_id, model/status) tuples
    """
    import subprocess

    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
            close_fds=True  # Prevent fd inheritance issues in threaded contexts
        )

        if result.returncode != 0:
            return []

        devices = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]

                # Get device model if available
                model = "Unknown"
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.replace("model:", "")
                        break

                if status == "device":
                    devices.append((device_id, model))
                elif status == "unauthorized":
                    devices.append((device_id, "UNAUTHORIZED - Accept USB debugging on device"))
                elif status == "offline":
                    devices.append((device_id, "OFFLINE"))

        return devices

    except Exception as e:
        console.print(f"[yellow]⚠[/] Could not scan devices: {e}")
        return []


def _select_device_wizard() -> Tuple[Optional[str], Optional[str]]:
    """
    Scan for devices and let user select one in the wizard flow.

    Returns:
        Tuple of (device_id, wireless_address)
        - If USB device selected: (device_id, None)
        - If wireless selected: (None, wireless_address)
        - If cancelled: (None, None)
    """
    console.print("\n[bold]Scanning for connected devices...[/]")

    devices = _scan_adb_devices()

    if not devices:
        console.print("[yellow]No USB devices found[/]")
        console.print("\n[bold]Options:[/]")
        console.print("  1. Connect via wireless ADB")
        console.print("  2. Retry scan")
        console.print("  3. Cancel")

        choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")

        if choice == "1":
            console.print("\n[bold]Wireless ADB Connection[/]")
            console.print("  On your phone: Settings → Developer Options → Wireless Debugging")
            console.print("  Tap 'Pair device with pairing code' for new connection")
            console.print()
            wireless_address = Prompt.ask("Enter device IP:PORT (e.g., 192.168.1.100:5555)")
            return None, wireless_address
        elif choice == "2":
            return _select_device_wizard()  # Retry
        else:
            return None, None

    # Show available devices
    table = Table(title="Available Devices", show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Device ID")
    table.add_column("Model/Status")

    for i, (device_id, model) in enumerate(devices, 1):
        if "UNAUTHORIZED" in model or "OFFLINE" in model:
            table.add_row(str(i), device_id, f"[red]{model}[/]")
        else:
            table.add_row(str(i), device_id, f"[green]{model}[/]")

    console.print(table)

    # Add options
    console.print(f"\n  {len(devices) + 1}. Connect new wireless device")
    console.print(f"  {len(devices) + 2}. Rescan")

    choice = Prompt.ask(
        "Select device",
        choices=[str(i) for i in range(1, len(devices) + 3)],
        default="1"
    )

    choice_num = int(choice)

    if choice_num <= len(devices):
        device_id, model = devices[choice_num - 1]
        if "UNAUTHORIZED" in model:
            console.print("[yellow]⚠[/] Please accept USB debugging authorization on your device")
            console.print("   Then run the wizard again.")
            return None, None
        if "OFFLINE" in model:
            console.print("[yellow]⚠[/] Device is offline. Try reconnecting the USB cable.")
            return None, None
        console.print(f"[green]✓[/] Selected: {device_id}")
        return device_id, None
    elif choice_num == len(devices) + 1:
        console.print("\n[bold]Wireless ADB Connection[/]")
        console.print("  On your phone: Settings → Developer Options → Wireless Debugging")
        wireless_address = Prompt.ask("Enter device IP:PORT (e.g., 192.168.1.100:5555)")
        return None, wireless_address
    else:
        return _select_device_wizard()  # Rescan


def _run_wizard_flow(
    output: Optional[Path],
    debug: bool = False,
) -> None:
    """
    Run the full wizard flow with TUI integration.

    Steps:
    1. Welcome - Show options
    2. Device - Connect to device
    3. Chats - Select chats to export
    4. Export - Run export with progress
    5. Summary - Show results
    """
    from whatsapp_chat_autoexport.utils.logger import Logger
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver
    from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter
    from whatsapp_chat_autoexport.legacy.tui.screens.device_connect import DeviceInfo

    driver = None
    appium_manager = None
    logger = Logger(debug=debug)

    try:
        # =====================================================
        # STEP 1: WELCOME
        # =====================================================
        console.print(Panel.fit(
            "[bold cyan]WhatsApp Export Wizard[/]\n\n"
            "This wizard will guide you through:\n"
            "  1. Connecting to your Android device\n"
            "  2. Selecting chats to export\n"
            "  3. Exporting to Google Drive\n"
            "  4. (Optional) Processing exports",
            title="Welcome",
        ))

        console.print("\n[bold]Options:[/]")
        console.print("  1. Full Export - Export all chats with guidance")
        console.print("  2. Quick Export - Export with default settings")
        console.print("  3. Exit")
        console.print()

        choice = Prompt.ask(
            "Select an option",
            choices=["1", "2", "3"],
            default="1"
        )

        if choice == "3":
            console.print("[yellow]Exiting wizard[/]")
            return

        quick_mode = (choice == "2")

        # =====================================================
        # STEP 2: DEVICE CONNECTION
        # =====================================================
        console.print("\n" + "=" * 60)
        console.print(Panel.fit(
            "Connect to your Android device.\n\n"
            "Make sure:\n"
            "  • USB debugging is enabled\n"
            "  • Device is connected via USB\n"
            "  • WhatsApp is open on the device",
            title="Step 2: Device Connection",
        ))

        # Scan for devices and let user select
        selected_device_id, wireless_address = _select_device_wizard()

        if selected_device_id is None and wireless_address is None:
            console.print("[yellow]No device selected. Exiting wizard.[/]")
            return

        # Start Appium
        try:
            from whatsapp_chat_autoexport.export.appium_manager import AppiumManager
            appium_manager = AppiumManager(logger=logger)

            with console.status("[bold cyan]Starting Appium server..."):
                if not appium_manager.start_appium():
                    console.print("[red]✗[/] Failed to start Appium")
                    raise typer.Exit(1)
                console.print("[green]✓[/] Appium server started")

        except ImportError:
            console.print("[yellow]⚠[/] AppiumManager not available")

        # Create and connect driver
        if wireless_address:
            driver = WhatsAppDriver(logger=logger, wireless_adb=wireless_address)
        elif selected_device_id:
            driver = WhatsAppDriver(logger=logger, device_id=selected_device_id)
        else:
            driver = WhatsAppDriver(logger=logger)

        with console.status("[bold cyan]Connecting to device..."):
            if not driver.connect():
                console.print("[red]✗[/] Failed to connect to device")
                console.print("\n[yellow]Troubleshooting:[/]")
                console.print("  • Check USB cable connection")
                console.print("  • Ensure USB debugging is enabled")
                console.print("  • Accept USB debugging prompt on device")
                raise typer.Exit(1)
            console.print("[green]✓[/] Connected to device")

        # Verify WhatsApp
        with console.status("[bold cyan]Verifying WhatsApp..."):
            if not driver.verify_whatsapp_is_open():
                console.print("[red]✗[/] WhatsApp is not accessible")
                console.print("\n[yellow]Please ensure:[/]")
                console.print("  • WhatsApp is open on the device")
                console.print("  • Phone is unlocked")
                console.print("  • You are on the main chat list")
                raise typer.Exit(1)
            console.print("[green]✓[/] WhatsApp is accessible")

        # =====================================================
        # STEP 3: CHAT SELECTION
        # =====================================================
        console.print("\n" + "=" * 60)
        console.print(Panel.fit(
            "Select which chats to export.\n\n"
            "The wizard will scan your chat list\n"
            "and let you choose which ones to export.",
            title="Step 3: Chat Selection",
        ))

        # Collect chats
        chats = []
        with console.status("[bold cyan]Scanning chat list..."):
            chats = driver.collect_all_chats()

        if not chats:
            console.print("[yellow]No chats found[/]")
            raise typer.Exit(0)

        console.print(f"[green]✓[/] Found {len(chats)} chats\n")

        # Show chat list
        table = Table(title="Available Chats", show_header=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Chat Name")

        for i, chat in enumerate(chats[:20], 1):
            table.add_row(str(i), chat)

        if len(chats) > 20:
            table.add_row("...", f"... and {len(chats) - 20} more")

        console.print(table)

        # Selection
        if quick_mode:
            selected_chats = chats
            console.print(f"\n[cyan]Quick mode: All {len(chats)} chats selected[/]")
        else:
            console.print("\n[bold]Selection Options:[/]")
            console.print("  1. Export all chats")
            console.print("  2. Export first N chats")
            console.print("  3. Enter specific chat numbers")

            sel_choice = Prompt.ask(
                "Select option",
                choices=["1", "2", "3"],
                default="1"
            )

            if sel_choice == "1":
                selected_chats = chats
            elif sel_choice == "2":
                n = int(Prompt.ask("How many chats?", default="5"))
                selected_chats = chats[:n]
            else:
                nums = Prompt.ask("Enter chat numbers (comma-separated)")
                indices = [int(x.strip()) - 1 for x in nums.split(",")]
                selected_chats = [chats[i] for i in indices if 0 <= i < len(chats)]

        console.print(f"\n[green]✓[/] Selected {len(selected_chats)} chats for export")

        # Media option
        include_media = True
        if not quick_mode:
            include_media = Confirm.ask("Include media files?", default=True)

        # =====================================================
        # STEP 4: EXPORT
        # =====================================================
        console.print("\n" + "=" * 60)
        console.print(Panel.fit(
            f"Ready to export {len(selected_chats)} chats.\n\n"
            f"Media: {'Included' if include_media else 'Excluded'}",
            title="Step 4: Export",
        ))

        if not Confirm.ask("Start export?", default=True):
            console.print("[yellow]Export cancelled[/]")
            raise typer.Exit(0)

        # Create exporter and run
        exporter = ChatExporter(driver=driver, logger=logger)

        console.print("\n[bold]Exporting...[/]\n")

        # Run export
        results, timings, total_time, skipped = exporter.export_chats(
            chat_names=selected_chats,
            include_media=include_media,
            resume_folder=None,
        )

        # =====================================================
        # STEP 5: SUMMARY
        # =====================================================
        console.print("\n" + "=" * 60)

        # Count results
        successful = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)

        summary_table = Table(title="Export Summary", show_header=True)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total chats", str(len(results)))
        summary_table.add_row("Successful", f"[green]{successful}[/]")
        summary_table.add_row("Failed", f"[red]{failed}[/]" if failed > 0 else "0")
        summary_table.add_row("Total time", f"{total_time:.1f}s")

        console.print(summary_table)

        if failed > 0:
            console.print("\n[red]Failed chats:[/]")
            for name, success in results.items():
                if not success:
                    console.print(f"  - {name}")

        # Pipeline option
        if output and successful > 0:
            console.print(f"\n[bold]Processing Pipeline[/]")
            if Confirm.ask("Run processing pipeline?", default=True):
                console.print("\n[bold]Running pipeline...[/]")
                try:
                    from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline
                    import tempfile

                    with tempfile.TemporaryDirectory() as temp_dir:
                        pipeline = WhatsAppPipeline(
                            downloads_dir=Path(temp_dir),
                            output_dir=output,
                            transcribe=True,
                            copy_media=True,
                        )

                        with console.status("[bold cyan]Downloading from Drive..."):
                            pipeline.download_from_drive()
                            console.print("[green]✓[/] Downloaded")

                        with console.status("[bold cyan]Extracting..."):
                            pipeline.extract_archives()
                            console.print("[green]✓[/] Extracted")

                        with console.status("[bold cyan]Building output..."):
                            pipeline.build_output()
                            console.print("[green]✓[/] Output built")

                        console.print(f"\n[green]✓[/] Output saved to: {output}")

                except Exception as e:
                    console.print(f"[red]✗[/] Pipeline error: {e}")

        console.print("\n[green bold]✓ Wizard complete![/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Wizard interrupted[/]")

    except typer.Exit:
        raise

    except Exception as e:
        console.print(f"\n[red]✗[/] Error: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        if appium_manager:
            try:
                appium_manager.stop_appium()
            except:
                pass


def _run_textual_tui(
    output: Optional[Path],
    include_media: bool = True,
    transcribe_audio: bool = True,
    delete_from_drive: bool = False,
    limit: Optional[int] = None,
    debug: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Run the Textual-based interactive TUI.

    Args:
        output: Output directory for processed files
        include_media: Whether to include media in exports
        transcribe_audio: Whether to transcribe audio files
        delete_from_drive: Whether to delete from Drive after processing
        limit: Maximum number of chats to export
        debug: Enable debug mode
        dry_run: Run in dry-run mode
    """
    import sys
    from whatsapp_chat_autoexport.tui.textual_app import WhatsAppExporterApp
    from whatsapp_chat_autoexport.utils.logger import Logger

    app = WhatsAppExporterApp(
        output_dir=output,
        include_media=include_media,
        transcribe_audio=transcribe_audio,
        delete_from_drive=delete_from_drive,
        limit=limit,
        debug=debug,
        dry_run=dry_run,
    )

    try:
        app.run(mouse=False)
    finally:
        # Ensure shutdown flag is set in case cleanup didn't run
        Logger.set_shutdown(True)

        # Clear any partial output and print clean exit message
        # Use ANSI escape codes to clear line and move cursor
        sys.stdout.write("\033[2K\r")  # Clear current line
        sys.stdout.flush()

        # Reset shutdown flag for any subsequent operations
        Logger.set_shutdown(False)

        # Print clean exit message
        console.print("\n[dim]WhatsApp Exporter closed.[/dim]")


@app.callback(invoke_without_command=True)
def wizard_main(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Pre-set output directory",
    ),
    textual: bool = typer.Option(
        False,
        "--textual",
        "--tui",
        help="Use new Textual-based interactive TUI",
    ),
    include_media: bool = typer.Option(
        True,
        "--with-media/--without-media",
        help="Include media in export",
    ),
    transcribe: bool = typer.Option(
        True,
        "--transcribe/--no-transcribe",
        help="Transcribe audio/video files",
    ),
    delete_from_drive: bool = typer.Option(
        False,
        "--delete-from-drive",
        help="Delete files from Drive after processing",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of chats to export",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show wizard flow without executing",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
) -> None:
    """
    Start the interactive export wizard.

    Guides you through:
    1. Device connection (USB or wireless)
    2. Chat selection
    3. Export options
    4. Processing options
    5. Export execution with progress

    The wizard provides a rich TUI with:
    - Visual progress indicators
    - Pause/resume controls
    - Error handling with retry options

    Use --textual for the new interactive TUI experience.
    """
    if ctx.invoked_subcommand is not None:
        return

    # Use Textual TUI if requested
    if textual:
        console.print("\n[bold cyan]Starting Textual TUI...[/]\n")
        _run_textual_tui(
            output=output,
            include_media=include_media,
            transcribe_audio=transcribe,
            delete_from_drive=delete_from_drive,
            limit=limit,
            debug=debug,
            dry_run=dry_run,
        )
        return

    console.print("\n[bold cyan]WhatsApp Export Wizard[/]\n")

    if dry_run:
        console.print("[yellow]DRY RUN - Showing wizard flow[/]\n")
        _show_wizard_flow()
        return

    # Run the full wizard flow
    _run_wizard_flow(output=output, debug=debug)


def _show_wizard_flow() -> None:
    """Show the wizard flow in dry-run mode."""
    # Step 1: Welcome
    console.print("[bold]Step 1: Welcome[/]")
    console.print("  Options:")
    console.print("  • Export Wizard - Full guided workflow")
    console.print("  • Quick Export - Export all with defaults")
    console.print("  • Settings - Configure options")
    console.print()

    # Step 2: Device
    console.print("[bold]Step 2: Device Connection[/]")
    console.print("  • USB: Auto-detect connected devices")
    console.print("  • Wireless: Enter IP and pairing code")
    console.print("  • Verify WhatsApp is open and accessible")
    console.print()

    # Step 3: Chat Selection
    console.print("[bold]Step 3: Chat Selection[/]")
    console.print("  • View all available chats")
    console.print("  • Filter and search")
    console.print("  • Select individual or all")
    console.print("  • Skip already-exported chats")
    console.print()

    # Step 4: Export Progress
    console.print("[bold]Step 4: Export Progress[/]")
    console.print("  • Real-time progress bars")
    console.print("  • Current chat and step display")
    console.print("  • Queue view with status")
    console.print("  • Pause/Resume controls")
    console.print("  • Automatic retry on failures")
    console.print()

    # Step 5: Summary
    console.print("[bold]Step 5: Summary[/]")
    console.print("  • Completed/Failed/Skipped counts")
    console.print("  • Duration statistics")
    console.print("  • Option to retry failed exports")
    console.print("  • Output location")
    console.print()


@app.command()
def quick(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for processed files",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of chats",
    ),
    include_media: bool = typer.Option(
        True,
        "--with-media/--without-media",
        help="Include media in export",
    ),
    use_new_workflow: bool = typer.Option(
        False,
        "--use-new-workflow",
        help="Use new modular workflow",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
) -> None:
    """
    Quick export with default settings.

    Exports all chats without interactive prompts.
    Good for automated/scripted usage.
    """
    console.print("\n[bold cyan]Quick Export[/]\n")

    if dry_run:
        console.print("[yellow]DRY RUN[/]\n")
        console.print("[bold]Settings:[/]")
        console.print(f"  Output: {output}")
        if limit:
            console.print(f"  Limit: {limit} chats")
        console.print(f"  Media: {'included' if include_media else 'excluded'}")
        console.print(f"  Workflow: {'new' if use_new_workflow else 'legacy'}")
        console.print("\n[dim]Would proceed with export...[/]")
        return

    # Run quick export using export command
    from .export import export_main

    # Create a mock context
    class MockContext:
        invoked_subcommand = None

    ctx = MockContext()

    # Call export with quick settings
    export_main(
        ctx=ctx,
        output=output,
        limit=limit,
        include_media=include_media,
        no_output_media=False,
        no_transcribe=False,
        force_transcribe=False,
        connection="usb",
        wireless_address=None,
        resume_path=None,
        delete_from_drive=False,
        dry_run=False,
        debug=debug,
        use_new_workflow=use_new_workflow,
        skip_appium=False,
    )
