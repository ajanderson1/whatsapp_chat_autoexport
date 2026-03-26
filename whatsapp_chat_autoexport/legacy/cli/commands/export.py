"""
Export command for WhatsApp Chat Auto-Export.

Exports chats from WhatsApp on an Android device to Google Drive.
"""

import sys
import time
from typing import Optional, List, Tuple
from pathlib import Path
from enum import Enum

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

app = typer.Typer(
    name="export",
    help="Export chats from WhatsApp to Google Drive",
    no_args_is_help=False,
)

console = Console()


class ConnectionType(str, Enum):
    """Device connection type."""

    usb = "usb"
    wireless = "wireless"


def _scan_adb_devices(console: Console) -> List[Tuple[str, str]]:
    """
    Scan for connected ADB devices.

    Returns:
        List of (device_id, status) tuples
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


def _select_device(console: Console) -> Tuple[Optional[str], bool]:
    """
    Scan for devices and let user select one.

    Returns:
        Tuple of (device_id or None, is_wireless)
        - device_id: Selected device ID, or None if connecting new wireless
        - is_wireless: True if user wants to connect new wireless device
    """
    console.print("\n[bold]Scanning for connected devices...[/]")

    devices = _scan_adb_devices(console)

    if not devices:
        console.print("[yellow]No devices found[/]")
        console.print("\n[bold]Options:[/]")
        console.print("  1. Connect via wireless ADB")
        console.print("  2. Retry scan")
        console.print("  3. Cancel")

        from rich.prompt import Prompt
        choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")

        if choice == "1":
            return None, True
        elif choice == "2":
            return _select_device(console)  # Retry
        else:
            return None, False

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

    from rich.prompt import Prompt
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
            console.print("   Then run the command again.")
            return None, False
        if "OFFLINE" in model:
            console.print("[yellow]⚠[/] Device is offline. Try reconnecting the USB cable.")
            return None, False
        console.print(f"[green]✓[/] Selected: {device_id}")
        return device_id, False
    elif choice_num == len(devices) + 1:
        return None, True  # Wireless
    else:
        return _select_device(console)  # Rescan


def _create_driver_and_exporter(
    connection: ConnectionType,
    wireless_address: Optional[str],
    debug: bool,
) -> Tuple["WhatsAppDriver", "ChatExporter", "Logger"]:
    """
    Create WhatsAppDriver and ChatExporter instances.

    Returns:
        Tuple of (WhatsAppDriver, ChatExporter, Logger)
    """
    from whatsapp_chat_autoexport.utils.logger import Logger
    from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver
    from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter

    logger = Logger(debug=debug)

    # Create driver with appropriate connection settings
    if connection == ConnectionType.wireless and wireless_address:
        driver = WhatsAppDriver(
            logger=logger,
            wireless_adb=wireless_address,
        )
    else:
        driver = WhatsAppDriver(logger=logger)

    exporter = ChatExporter(driver=driver, logger=logger)

    return driver, exporter, logger


def _connect_device(
    driver: "WhatsAppDriver",
    connection: ConnectionType,
    wireless_address: Optional[str],
    console: Console,
) -> bool:
    """
    Connect to the Android device.

    Returns:
        True if connection successful
    """
    with console.status("[bold cyan]Connecting to device..."):
        try:
            if connection == ConnectionType.wireless and wireless_address:
                console.print(f"  Connecting via wireless ADB to {wireless_address}...")
            else:
                console.print("  Connecting via USB...")

            if not driver.connect():
                console.print("[red]✗[/] Failed to connect to device")
                return False

            console.print("[green]✓[/] Connected to device")
            return True

        except Exception as e:
            console.print(f"[red]✗[/] Connection error: {e}")
            return False


def _verify_whatsapp(driver: "WhatsAppDriver", console: Console) -> bool:
    """
    Verify WhatsApp is open and accessible.

    Returns:
        True if WhatsApp is accessible
    """
    with console.status("[bold cyan]Verifying WhatsApp..."):
        try:
            if not driver.verify_whatsapp_is_open():
                console.print("[red]✗[/] WhatsApp is not accessible")
                console.print("  Please ensure:")
                console.print("  - WhatsApp is open on the device")
                console.print("  - Phone is unlocked")
                console.print("  - You are on the main chat list screen")
                return False

            console.print("[green]✓[/] WhatsApp is accessible")
            return True

        except Exception as e:
            console.print(f"[red]✗[/] WhatsApp verification error: {e}")
            return False


def _collect_chats(
    driver: "WhatsAppDriver",
    limit: Optional[int],
    console: Console,
) -> List[str]:
    """
    Collect list of chats from WhatsApp.

    Returns:
        List of chat names
    """
    console.print("\n[bold]Collecting chats...[/]")

    with console.status("[bold cyan]Scanning chat list..."):
        try:
            chats = driver.collect_all_chats()

            if not chats:
                console.print("[yellow]⚠[/] No chats found")
                return []

            # Apply limit if specified
            if limit and limit > 0:
                chats = chats[:limit]
                console.print(f"[green]✓[/] Found {len(chats)} chats (limited from total)")
            else:
                console.print(f"[green]✓[/] Found {len(chats)} chats")

            return chats

        except Exception as e:
            console.print(f"[red]✗[/] Error collecting chats: {e}")
            return []


def _export_chats(
    exporter: "ChatExporter",
    driver: "WhatsAppDriver",
    chats: List[str],
    include_media: bool,
    resume_path: Optional[Path],
    use_new_workflow: bool,
    console: Console,
) -> Tuple[dict, dict, float, dict]:
    """
    Export all chats to Google Drive.

    Returns:
        Tuple of (results, timings, total_time, skipped)
    """
    console.print(f"\n[bold]Exporting {len(chats)} chats...[/]\n")

    if use_new_workflow:
        console.print("[cyan]Using new modular workflow[/]\n")
        return exporter.export_chats_with_new_workflow(
            chat_names=chats,
            include_media=include_media,
            resume_folder=resume_path,
        )
    else:
        console.print("[dim]Using legacy workflow[/]\n")
        return exporter.export_chats(
            chat_names=chats,
            include_media=include_media,
            resume_folder=resume_path,
        )


def _show_export_summary(
    results: dict,
    timings: dict,
    total_time: float,
    skipped: dict,
    console: Console,
) -> None:
    """Display export summary."""
    # Count results
    successful = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    skipped_count = len(skipped)

    # Create summary table
    table = Table(title="Export Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total chats", str(len(results)))
    table.add_row("Successful", f"[green]{successful}[/]")
    table.add_row("Failed", f"[red]{failed}[/]" if failed > 0 else "0")
    table.add_row("Skipped (resume)", f"[yellow]{skipped_count}[/]" if skipped_count > 0 else "0")
    table.add_row("Total time", f"{total_time:.1f}s")

    if successful > 0:
        avg_time = sum(t for n, t in timings.items() if results.get(n)) / successful
        table.add_row("Avg time per chat", f"{avg_time:.1f}s")

    console.print()
    console.print(table)

    # Show failed chats if any
    if failed > 0:
        console.print("\n[red]Failed chats:[/]")
        for name, success in results.items():
            if not success and name not in skipped:
                console.print(f"  - {name}")


def _run_pipeline(
    output: Path,
    no_transcribe: bool,
    force_transcribe: bool,
    no_output_media: bool,
    delete_from_drive: bool,
    console: Console,
) -> bool:
    """
    Run the processing pipeline after export.

    Returns:
        True if pipeline completed successfully
    """
    console.print("\n[bold]Running processing pipeline...[/]\n")

    try:
        from whatsapp_chat_autoexport.pipeline import WhatsAppPipeline, PipelineConfig

        config = PipelineConfig(
            output_dir=Path(output),
            delete_from_drive=delete_from_drive,
            transcribe_audio_video=not no_transcribe,
            skip_existing_transcriptions=not force_transcribe,
            include_media=not no_output_media,
            skip_download=False,
        )

        pipeline = WhatsAppPipeline(config)
        result = pipeline.run()

        if result.get("success"):
            console.print(f"\n[green]✓[/] Pipeline complete! Output: {output}")
            return True
        else:
            for err in result.get("errors", []):
                console.print(f"[red]✗[/] {err}")
            return False

    except ImportError as e:
        console.print(f"[yellow]⚠[/] Pipeline not available: {e}")
        console.print("  Run 'poetry run whatsapp-pipeline' separately to process exports")
        return False
    except Exception as e:
        console.print(f"[red]✗[/] Pipeline error: {e}")
        return False


@app.callback(invoke_without_command=True)
def export_main(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for processed files (enables integrated pipeline)",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of chats to export",
    ),
    include_media: bool = typer.Option(
        True,
        "--with-media/--without-media",
        help="Include media files in export",
    ),
    no_output_media: bool = typer.Option(
        False,
        "--no-output-media",
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
    connection: ConnectionType = typer.Option(
        ConnectionType.usb,
        "--connection",
        "-c",
        help="Device connection type",
    ),
    wireless_address: Optional[str] = typer.Option(
        None,
        "--wireless-adb",
        help="Wireless ADB address (IP:PORT or just IP)",
    ),
    resume_path: Optional[Path] = typer.Option(
        None,
        "--resume",
        help="Resume mode: skip chats already in this Google Drive folder",
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
    use_new_workflow: bool = typer.Option(
        False,
        "--use-new-workflow",
        help="Use the new modular export workflow (experimental)",
    ),
    skip_appium: bool = typer.Option(
        False,
        "--skip-appium",
        help="Skip Appium server startup (use if already running)",
    ),
) -> None:
    """
    Export chats from WhatsApp to Google Drive.

    This command automates the WhatsApp export process:
    1. Connects to Android device via USB or wireless ADB
    2. Opens each chat in WhatsApp
    3. Triggers export to Google Drive

    With --output, also runs the processing pipeline:
    4. Downloads exports from Google Drive
    5. Extracts and organizes files
    6. Transcribes audio/video (unless --no-transcribe)
    7. Builds final output structure
    """
    if ctx.invoked_subcommand is not None:
        return

    console.print("\n[bold cyan]WhatsApp Chat Export[/]\n")

    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made[/]\n")
        _show_export_plan(
            output=output,
            limit=limit,
            include_media=include_media,
            no_output_media=no_output_media,
            no_transcribe=no_transcribe,
            connection=connection,
            wireless_address=wireless_address,
            resume_path=resume_path,
            use_new_workflow=use_new_workflow,
        )
        return

    # Validate options
    if connection == ConnectionType.wireless and not wireless_address:
        console.print("[red]✗[/] Wireless connection requires --wireless-adb address")
        raise typer.Exit(1)

    # Show configuration
    console.print("[bold]Configuration:[/]")
    console.print(f"  Connection: {connection.value}")
    if wireless_address:
        console.print(f"  Wireless address: {wireless_address}")
    if limit:
        console.print(f"  Limit: {limit} chats")
    console.print(f"  Include media: {include_media}")
    if use_new_workflow:
        console.print(f"  [cyan]Workflow: NEW MODULAR (experimental)[/]")
    else:
        console.print(f"  Workflow: legacy")
    if output:
        console.print(f"  Output: {output}")
        console.print(f"  Transcription: {not no_transcribe}")
        if not no_transcribe:
            console.print(f"  Force re-transcribe: {force_transcribe}")
        console.print(f"  Output media: {not no_output_media}")
    console.print()

    # ========================================
    # ACTUAL EXPORT IMPLEMENTATION
    # ========================================

    driver = None
    appium_manager = None

    try:
        # Import required modules
        from whatsapp_chat_autoexport.utils.logger import Logger
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver
        from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter

        logger = Logger(debug=debug)

        # ========================================
        # STEP 1: DEVICE SELECTION
        # ========================================
        # If no wireless address specified, scan for devices and let user choose
        selected_device_id = None
        use_wireless = (connection == ConnectionType.wireless)

        if not wireless_address:
            # Scan for devices and let user select
            selected_device_id, use_wireless = _select_device(console)

            if selected_device_id is None and not use_wireless:
                # User cancelled or device unavailable
                console.print("[yellow]No device selected. Exiting.[/]")
                raise typer.Exit(0)

            if use_wireless:
                # User wants to connect via wireless - prompt for address
                from rich.prompt import Prompt
                console.print("\n[bold]Wireless ADB Connection[/]")
                console.print("  On your phone: Settings → Developer Options → Wireless Debugging")
                console.print("  Tap 'Pair device with pairing code' for new connection")
                console.print()
                wireless_address = Prompt.ask("Enter device IP:PORT (e.g., 192.168.1.100:5555)")
                if not wireless_address:
                    console.print("[yellow]No address provided. Exiting.[/]")
                    raise typer.Exit(0)
                connection = ConnectionType.wireless

        # ========================================
        # STEP 2: START APPIUM
        # ========================================
        if not skip_appium:
            try:
                from whatsapp_chat_autoexport.export.appium_manager import AppiumManager
                appium_manager = AppiumManager(logger=logger)

                with console.status("[bold cyan]Starting Appium server..."):
                    if not appium_manager.start_appium():
                        console.print("[red]✗[/] Failed to start Appium server")
                        console.print("  Try running with --skip-appium if Appium is already running")
                        raise typer.Exit(1)
                    console.print("[green]✓[/] Appium server started")

            except ImportError:
                console.print("[yellow]⚠[/] AppiumManager not available, assuming Appium is running")

        # ========================================
        # STEP 3: CREATE DRIVER WITH SELECTED DEVICE
        # ========================================
        if use_wireless and wireless_address:
            driver = WhatsAppDriver(
                logger=logger,
                wireless_adb=wireless_address,
            )
        elif selected_device_id:
            # Pass specific device ID to the driver
            driver = WhatsAppDriver(
                logger=logger,
                device_id=selected_device_id,
            )
        else:
            driver = WhatsAppDriver(logger=logger)

        # Connect to device
        if not _connect_device(driver, connection, wireless_address, console):
            raise typer.Exit(1)

        # Verify WhatsApp
        if not _verify_whatsapp(driver, console):
            raise typer.Exit(1)

        # Collect chats
        chats = _collect_chats(driver, limit, console)
        if not chats:
            console.print("[yellow]No chats to export[/]")
            raise typer.Exit(0)

        # Show chat list
        console.print("\n[bold]Chats to export:[/]")
        for i, chat in enumerate(chats[:10], 1):
            console.print(f"  {i}. {chat}")
        if len(chats) > 10:
            console.print(f"  ... and {len(chats) - 10} more")

        # Confirm export
        console.print()
        if not typer.confirm(f"Export {len(chats)} chats?", default=True):
            console.print("[yellow]Export cancelled[/]")
            raise typer.Exit(0)

        # Create exporter and run
        exporter = ChatExporter(driver=driver, logger=logger)

        results, timings, total_time, skipped = _export_chats(
            exporter=exporter,
            driver=driver,
            chats=chats,
            include_media=include_media,
            resume_path=resume_path,
            use_new_workflow=use_new_workflow,
            console=console,
        )

        # Show summary
        _show_export_summary(results, timings, total_time, skipped, console)

        # Run pipeline if output specified
        if output:
            _run_pipeline(
                output=output,
                no_transcribe=no_transcribe,
                force_transcribe=force_transcribe,
                no_output_media=no_output_media,
                delete_from_drive=delete_from_drive,
                console=console,
            )

        console.print("\n[green]✓[/] Export complete!")

    except KeyboardInterrupt:
        console.print("\n[yellow]Export interrupted by user[/]")
        raise typer.Exit(130)

    except typer.Exit:
        raise

    except Exception as e:
        console.print(f"\n[red]✗[/] Unexpected error: {e}")
        if debug:
            import traceback
            console.print(traceback.format_exc())
        raise typer.Exit(1)

    finally:
        # Cleanup
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


def _show_export_plan(
    output: Optional[Path],
    limit: Optional[int],
    include_media: bool,
    no_output_media: bool,
    no_transcribe: bool,
    connection: ConnectionType,
    wireless_address: Optional[str],
    resume_path: Optional[Path],
    use_new_workflow: bool = False,
) -> None:
    """Show what the export would do."""
    console.print("[bold]Export Plan:[/]\n")

    # Workflow type
    if use_new_workflow:
        console.print("[cyan]Using NEW MODULAR workflow (experimental)[/]\n")
    else:
        console.print("[dim]Using legacy workflow[/]\n")

    # Connection
    console.print("1. [cyan]Connect to device[/]")
    if connection == ConnectionType.usb:
        console.print("   → USB connection")
    else:
        console.print(f"   → Wireless: {wireless_address}")

    # Collection
    console.print("\n2. [cyan]Collect chats[/]")
    if limit:
        console.print(f"   → Limited to {limit} chats")
    else:
        console.print("   → All chats")

    if resume_path:
        console.print(f"   → Resume mode: skip existing in {resume_path}")

    # Export
    console.print("\n3. [cyan]Export to Google Drive[/]")
    console.print(f"   → Media: {'included' if include_media else 'excluded'}")

    # Pipeline (if output specified)
    if output:
        console.print("\n4. [cyan]Download from Google Drive[/]")

        console.print("\n5. [cyan]Extract and organize[/]")

        if not no_transcribe:
            console.print("\n6. [cyan]Transcribe audio/video[/]")
        else:
            console.print("\n6. [dim]Transcription skipped[/]")

        console.print("\n7. [cyan]Build final output[/]")
        console.print(f"   → Output: {output}")
        console.print(f"   → Media: {'excluded' if no_output_media else 'included'}")

    console.print()


@app.command()
def list_chats(
    connection: ConnectionType = typer.Option(
        ConnectionType.usb,
        "--connection",
        "-c",
        help="Device connection type",
    ),
    wireless_address: Optional[str] = typer.Option(
        None,
        "--wireless-adb",
        help="Wireless ADB address",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
    skip_appium: bool = typer.Option(
        False,
        "--skip-appium",
        help="Skip Appium server startup",
    ),
) -> None:
    """
    List available chats from WhatsApp.

    Connects to the device and collects the list of chats
    without exporting any.
    """
    console.print("\n[bold]WhatsApp Chat List[/]\n")

    driver = None
    appium_manager = None

    try:
        from whatsapp_chat_autoexport.utils.logger import Logger
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

        logger = Logger(debug=debug)

        # Device selection if no wireless address specified
        selected_device_id = None
        use_wireless = (connection == ConnectionType.wireless)

        if not wireless_address:
            selected_device_id, use_wireless = _select_device(console)

            if selected_device_id is None and not use_wireless:
                console.print("[yellow]No device selected. Exiting.[/]")
                raise typer.Exit(0)

            if use_wireless:
                from rich.prompt import Prompt
                console.print("\n[bold]Wireless ADB Connection[/]")
                wireless_address = Prompt.ask("Enter device IP:PORT (e.g., 192.168.1.100:5555)")
                if not wireless_address:
                    console.print("[yellow]No address provided. Exiting.[/]")
                    raise typer.Exit(0)
                connection = ConnectionType.wireless

        # Start Appium if needed
        if not skip_appium:
            try:
                from whatsapp_chat_autoexport.export.appium_manager import AppiumManager
                appium_manager = AppiumManager(logger=logger)

                with console.status("[bold cyan]Starting Appium server..."):
                    if not appium_manager.start_appium():
                        console.print("[red]✗[/] Failed to start Appium server")
                        raise typer.Exit(1)
                    console.print("[green]✓[/] Appium server started")

            except ImportError:
                pass

        # Create and connect driver
        if use_wireless and wireless_address:
            driver = WhatsAppDriver(logger=logger, wireless_adb=wireless_address)
        elif selected_device_id:
            driver = WhatsAppDriver(logger=logger, device_id=selected_device_id)
        else:
            driver = WhatsAppDriver(logger=logger)

        if not _connect_device(driver, connection, wireless_address, console):
            raise typer.Exit(1)

        if not _verify_whatsapp(driver, console):
            raise typer.Exit(1)

        # Collect chats
        chats = _collect_chats(driver, None, console)

        if chats:
            console.print("\n[bold]Available chats:[/]")
            table = Table(show_header=True)
            table.add_column("#", style="dim")
            table.add_column("Chat Name")

            for i, chat in enumerate(chats, 1):
                table.add_row(str(i), chat)

            console.print(table)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]✗[/] Error: {e}")
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


@app.command()
def verify(
    connection: ConnectionType = typer.Option(
        ConnectionType.usb,
        "--connection",
        "-c",
        help="Device connection type",
    ),
    wireless_address: Optional[str] = typer.Option(
        None,
        "--wireless-adb",
        help="Wireless ADB address",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug output",
    ),
    skip_appium: bool = typer.Option(
        False,
        "--skip-appium",
        help="Skip Appium server startup",
    ),
) -> None:
    """
    Verify device connection and WhatsApp state.

    Checks:
    - Device is connected and accessible
    - WhatsApp is installed and open
    - Phone is unlocked
    - UI elements are accessible
    """
    console.print("\n[bold]Device and WhatsApp Verification[/]\n")

    driver = None
    appium_manager = None
    all_passed = True

    try:
        from whatsapp_chat_autoexport.utils.logger import Logger
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

        logger = Logger(debug=debug)

        # Device selection if no wireless address specified
        selected_device_id = None
        use_wireless = (connection == ConnectionType.wireless)

        if not wireless_address:
            selected_device_id, use_wireless = _select_device(console)

            if selected_device_id is None and not use_wireless:
                console.print("[yellow]No device selected. Exiting.[/]")
                raise typer.Exit(0)

            if use_wireless:
                from rich.prompt import Prompt
                console.print("\n[bold]Wireless ADB Connection[/]")
                wireless_address = Prompt.ask("Enter device IP:PORT (e.g., 192.168.1.100:5555)")
                if not wireless_address:
                    console.print("[yellow]No address provided. Exiting.[/]")
                    raise typer.Exit(0)
                connection = ConnectionType.wireless

        # Check 1: Appium
        console.print("[bold]1. Appium Server[/]")
        if not skip_appium:
            try:
                from whatsapp_chat_autoexport.export.appium_manager import AppiumManager
                appium_manager = AppiumManager(logger=logger)

                if appium_manager.start_appium():
                    console.print("   [green]✓[/] Appium server running")
                else:
                    console.print("   [red]✗[/] Failed to start Appium")
                    all_passed = False

            except ImportError:
                console.print("   [yellow]⚠[/] AppiumManager not available")
        else:
            console.print("   [dim]Skipped (--skip-appium)[/]")

        # Check 2: Device connection
        console.print("\n[bold]2. Device Connection[/]")
        if use_wireless and wireless_address:
            driver = WhatsAppDriver(logger=logger, wireless_adb=wireless_address)
        elif selected_device_id:
            driver = WhatsAppDriver(logger=logger, device_id=selected_device_id)
        else:
            driver = WhatsAppDriver(logger=logger)

        if driver.connect():
            console.print("   [green]✓[/] Device connected")

            # Get device info
            try:
                device_info = driver.get_device_info()
                if device_info:
                    console.print(f"   Device: {device_info.get('model', 'Unknown')}")
                    console.print(f"   Android: {device_info.get('version', 'Unknown')}")
            except:
                pass
        else:
            console.print("   [red]✗[/] Device not connected")
            all_passed = False

        # Check 3: Phone unlock status
        console.print("\n[bold]3. Phone Unlock Status[/]")
        if driver and driver.driver:
            try:
                if driver.check_if_phone_locked():
                    console.print("   [red]✗[/] Phone is locked")
                    all_passed = False
                else:
                    console.print("   [green]✓[/] Phone is unlocked")
            except Exception as e:
                console.print(f"   [yellow]⚠[/] Could not check: {e}")
        else:
            console.print("   [dim]Skipped (no connection)[/]")

        # Check 4: WhatsApp state
        console.print("\n[bold]4. WhatsApp State[/]")
        if driver and driver.driver:
            if driver.verify_whatsapp_is_open():
                console.print("   [green]✓[/] WhatsApp is open and accessible")

                # Check for main screen
                try:
                    current_activity = driver.driver.current_activity
                    console.print(f"   Activity: {current_activity}")
                except:
                    pass
            else:
                console.print("   [red]✗[/] WhatsApp is not accessible")
                all_passed = False
        else:
            console.print("   [dim]Skipped (no connection)[/]")

        # Summary
        console.print()
        if all_passed:
            console.print("[green]✓ All checks passed! Ready to export.[/]")
        else:
            console.print("[red]✗ Some checks failed. Please fix issues before exporting.[/]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]✗[/] Verification error: {e}")
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
