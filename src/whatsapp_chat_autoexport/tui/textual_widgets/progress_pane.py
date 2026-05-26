"""
Unified progress pane widget for export and processing display.

Shows real-time progress for both export and post-processing phases
in a compact bottom pane format with activity log.
"""

from datetime import datetime
from typing import List, Literal, Optional
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static, ProgressBar, RichLog
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive


class ProgressPane(Widget):
    """
    Unified progress pane for export and processing modes.

    Features:
    - Two modes: "export" and "processing"
    - Export mode: shows current chat, step, overall progress
    - Processing mode: shows phase list, current phase, overall progress
    - Compact activity log (3-5 lines)
    - Progress bar with percentage

    Layout (export mode):
    ┌─ Progress ─────────────────────────────────────────────┐
    │ Current: Tim Cocking                                   │
    │ Step: Select Drive (5/7)                               │
    │ Overall: 1/5 complete (20%)                            │
    │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  20%         │
    ├─ Activity ─────────────────────────────────────────────┤
    │ 12:34:15 ✓ Jason Cormack exported successfully         │
    │ 12:34:45 → Starting export: Tim Cocking                │
    │ 12:34:46 → Opening chat menu...                        │
    └────────────────────────────────────────────────────────┘

    Layout (processing mode):
    ┌─ Progress ─────────────────────────────────────────────┐
    │ Phase: Transcribe audio/video (3/5)                    │
    │ [✓] Download  [✓] Extract  [●] Transcribe  [ ] Build   │
    │ ██████████████████████████░░░░░░░░░░░░░░░░░  60%      │
    ├─ Activity ─────────────────────────────────────────────┤
    │ 12:40:12 ✓ Downloaded 4 files from Google Drive        │
    │ 12:40:45 ✓ Extracted archives to temp directory        │
    │ 12:41:00 → Transcribing: Jason Cormack/PTT-001.opus    │
    └────────────────────────────────────────────────────────┘
    """

    DEFAULT_CSS = """
    ProgressPane {
        height: 30%;
        min-height: 12;
        border: solid $primary;
        padding: 0;
    }

    ProgressPane .progress-section {
        height: auto;
        max-height: 6;
        padding: 0 1;
    }

    ProgressPane .progress-title {
        text-style: bold;
        padding: 0;
        background: $primary-background;
    }

    ProgressPane .progress-current {
        color: $primary;
    }

    ProgressPane .progress-step {
        color: $text;
    }

    ProgressPane .progress-overall {
        color: $text-muted;
    }

    ProgressPane .phase-list {
        height: auto;
    }

    ProgressPane ProgressBar {
        padding: 0;
        margin: 0;
    }

    ProgressPane .activity-section {
        height: 1fr;
        min-height: 4;
        border-top: solid $primary;
        padding: 0;
    }

    ProgressPane .activity-title {
        text-style: bold;
        padding: 0;
        background: $primary-background;
    }

    ProgressPane RichLog {
        height: 1fr;
        min-height: 2;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    ProgressPane .summary-section {
        padding: 1;
    }

    ProgressPane .summary-success {
        color: $success;
    }

    ProgressPane .summary-error {
        color: $error;
    }
    """

    # Mode: "export", "processing", "complete", or "error"
    mode: reactive[str] = reactive("export")

    # Export mode properties
    current_chat: reactive[str] = reactive("")
    current_step: reactive[str] = reactive("")
    step_number: reactive[int] = reactive(0)
    total_steps: reactive[int] = reactive(7)
    completed_chats: reactive[int] = reactive(0)
    total_chats: reactive[int] = reactive(0)

    # Processing mode properties
    current_phase: reactive[str] = reactive("")
    phase_number: reactive[int] = reactive(0)
    total_phases: reactive[int] = reactive(5)

    # Shared state
    is_paused: reactive[bool] = reactive(False)
    has_error: reactive[bool] = reactive(False)
    error_message: reactive[str] = reactive("")

    # Internal state
    _is_mounted: bool = False

    # Processing phases
    PROCESSING_PHASES = [
        "Download",
        "Extract",
        "Transcribe",
        "Build",
        "Cleanup",
    ]

    # Map from pipeline phase strings to display names
    PHASE_DISPLAY_MAP = {
        "download": "Download",
        "extract": "Extract",
        "transcribe": "Transcribe",
        "build_output": "Build",
        "organize": "Build",
        "cleanup": "Cleanup",
    }

    # Processing item-level progress
    pipeline_item: reactive[str] = reactive("")
    pipeline_item_current: reactive[int] = reactive(0)
    pipeline_item_total: reactive[int] = reactive(0)

    # Export steps
    EXPORT_STEPS = [
        "Open chat",
        "Open menu",
        "Click More",
        "Export chat",
        "Select media",
        "Select Drive",
        "Upload",
    ]

    def __init__(
        self,
        mode: str = "export",
        total_chats: int = 0,
        **kwargs,
    ) -> None:
        """
        Initialize the progress pane.

        Args:
            mode: Initial mode ("export" or "processing")
            total_chats: Total number of chats to export
        """
        super().__init__(**kwargs)
        self.mode = mode
        self.total_chats = total_chats
        self._activity_messages: List[str] = []

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        with Vertical(classes="progress-section"):
            yield Static(" PROGRESS ", classes="progress-title")
            yield Static("", id="progress-current", classes="progress-current")
            yield Static("", id="progress-step", classes="progress-step")
            yield Static("", id="progress-overall", classes="progress-overall")
            yield Static("", id="phase-list", classes="phase-list")
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        with Vertical(classes="activity-section"):
            yield Static(" Activity ", classes="activity-title")
            yield RichLog(
                highlight=True,
                markup=True,
                wrap=True,
                auto_scroll=True,
                max_lines=50,
                id="activity-log",
            )
        with Vertical(classes="summary-section", id="summary-section"):
            yield Static("", id="summary-text")

    def on_mount(self) -> None:
        """Initialize display on mount."""
        self._is_mounted = True
        self._update_display()
        # Hide summary section initially
        summary = self.query_one("#summary-section")
        summary.display = False

    def _update_display(self) -> None:
        """Update the display based on current mode and state."""
        # Guard against calling before widget is mounted
        if not self._is_mounted:
            return

        if self.mode == "export":
            self._update_export_display()
        elif self.mode == "processing":
            self._update_processing_display()
        elif self.mode == "complete":
            self._update_complete_display()
        elif self.mode == "error":
            self._update_error_display()

    def _update_export_display(self) -> None:
        """Update display for export mode."""
        current = self.query_one("#progress-current", Static)
        step = self.query_one("#progress-step", Static)
        overall = self.query_one("#progress-overall", Static)
        phase_list = self.query_one("#phase-list", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)

        # Hide phase list in export mode
        phase_list.display = False

        # Update current chat
        if self.current_chat:
            paused_text = " [yellow](PAUSED)[/yellow]" if self.is_paused else ""
            current.update(f"Exporting: [cyan]{self.current_chat}[/cyan]{paused_text}")
        else:
            current.update("[dim]Waiting to start...[/dim]")

        # Update step
        if self.current_step:
            step.update(f"Step: {self.current_step} ({self.step_number}/{self.total_steps})")
        else:
            step.update("")

        # Update overall progress
        if self.total_chats > 0:
            percent = (self.completed_chats / self.total_chats) * 100
            overall.update(f"Overall: {self.completed_chats}/{self.total_chats} chats ({percent:.0f}%)")
            progress_bar.update(progress=percent)
        else:
            overall.update("")
            progress_bar.update(progress=0)

    def _update_processing_display(self) -> None:
        """Update display for processing mode."""
        current = self.query_one("#progress-current", Static)
        step = self.query_one("#progress-step", Static)
        overall = self.query_one("#progress-overall", Static)
        phase_list = self.query_one("#phase-list", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)

        # Show per-item progress in step line
        if self.pipeline_item and self.pipeline_item_total > 0:
            step.display = True
            step.update(
                f"[cyan]{self.pipeline_item}[/cyan]"
                f" ({self.pipeline_item_current}/{self.pipeline_item_total})"
            )
        else:
            step.display = False

        # Update current phase
        if self.current_phase:
            current.update(f"Phase: [cyan]{self.current_phase}[/cyan] ({self.phase_number}/{self.total_phases})")
        else:
            current.update("[dim]Starting processing...[/dim]")

        # Show phase list with checkmarks
        phase_list.display = True
        phase_parts = []
        for i, phase_name in enumerate(self.PROCESSING_PHASES):
            if i < self.phase_number - 1:
                phase_parts.append(f"[green]✓[/green] {phase_name}")
            elif i == self.phase_number - 1:
                phase_parts.append(f"[yellow bold]●[/yellow bold] [yellow]{phase_name}[/yellow]")
            else:
                phase_parts.append(f"[dim]○ {phase_name}[/dim]")
        phase_list.update("  ".join(phase_parts))

        # Update overall progress — show item-level progress within the current phase
        if self.pipeline_item_total > 0:
            overall.display = True
            item_percent = (self.pipeline_item_current / self.pipeline_item_total) * 100
            overall.update(
                f"Items: {self.pipeline_item_current}/{self.pipeline_item_total} ({item_percent:.0f}%)"
            )
        else:
            overall.display = False

        # Update progress bar — combine phase-level and item-level progress
        if self.total_phases > 0:
            phase_base = ((self.phase_number - 1) / self.total_phases) * 100
            phase_span = (1 / self.total_phases) * 100
            if self.pipeline_item_total > 0:
                item_fraction = self.pipeline_item_current / self.pipeline_item_total
            else:
                item_fraction = 0.1  # small nudge so bar isn't empty at phase start
            percent = phase_base + (phase_span * item_fraction)
            progress_bar.update(progress=min(percent, 100))
        else:
            progress_bar.update(progress=0)

    def _update_complete_display(self) -> None:
        """Update display for complete mode."""
        current = self.query_one("#progress-current", Static)
        step = self.query_one("#progress-step", Static)
        overall = self.query_one("#progress-overall", Static)
        phase_list = self.query_one("#phase-list", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)

        current.update("[green bold]Complete![/green bold]")
        step.display = False
        overall.display = False
        phase_list.display = False
        progress_bar.update(progress=100)

        # Show summary section
        summary_section = self.query_one("#summary-section")
        summary_section.display = True

    def _update_error_display(self) -> None:
        """Update display for error mode."""
        current = self.query_one("#progress-current", Static)
        step = self.query_one("#progress-step", Static)

        current.update(f"[red bold]Error:[/red bold] {self.error_message}")
        step.display = False

    # =========================================================================
    # Watch methods for reactive updates
    # =========================================================================

    def watch_mode(self, new_mode: str) -> None:
        """React to mode changes."""
        self._update_display()

    def watch_current_chat(self, new_value: str) -> None:
        """React to current chat changes."""
        if self.mode == "export":
            self._update_display()

    def watch_current_step(self, new_value: str) -> None:
        """React to step changes."""
        if self.mode == "export":
            self._update_display()

    def watch_completed_chats(self, new_value: int) -> None:
        """React to completed chat count changes."""
        if self.mode == "export":
            self._update_display()

    def watch_current_phase(self, new_value: str) -> None:
        """React to phase changes."""
        if self.mode == "processing":
            self._update_display()

    def watch_phase_number(self, new_value: int) -> None:
        """React to phase number changes."""
        if self.mode == "processing":
            self._update_display()

    def watch_pipeline_item(self, new_value: str) -> None:
        """React to pipeline item changes."""
        if self.mode == "processing":
            self._update_display()

    def watch_pipeline_item_current(self, new_value: int) -> None:
        """React to pipeline item progress changes."""
        if self.mode == "processing":
            self._update_display()

    def watch_pipeline_item_total(self, new_value: int) -> None:
        """React to pipeline item total changes."""
        if self.mode == "processing":
            self._update_display()

    def watch_is_paused(self, new_value: bool) -> None:
        """React to pause state changes."""
        self._update_display()

    # =========================================================================
    # Public API
    # =========================================================================

    def start_export(self, total_chats: int) -> None:
        """
        Start export mode with specified total chats.

        Args:
            total_chats: Total number of chats to export
        """
        self.mode = "export"
        self.total_chats = total_chats
        self.completed_chats = 0
        self.current_chat = ""
        self.current_step = ""
        self.step_number = 0
        self.log_activity("Starting export...", "info")

    def update_export_progress(
        self,
        chat: Optional[str] = None,
        step: Optional[str] = None,
        step_num: Optional[int] = None,
        completed: Optional[int] = None,
    ) -> None:
        """
        Update export progress.

        Args:
            chat: Current chat being exported
            step: Current step name
            step_num: Current step number (1-indexed)
            completed: Number of completed chats
        """
        if chat is not None:
            self.current_chat = chat
        if step is not None:
            self.current_step = step
        if step_num is not None:
            self.step_number = step_num
        if completed is not None:
            self.completed_chats = completed

    def update_export_step(
        self,
        step_message: str,
        step_num: int,
        total_steps: int,
    ) -> None:
        """
        Update the current export step from the on_progress callback.

        This is called from the worker thread via call_from_thread()
        to show real-time step-level progress during a single chat export.

        Args:
            step_message: Description of the current step (e.g., "Menu opened")
            step_num: Current step number (1-indexed)
            total_steps: Total number of steps in the export
        """
        self.current_step = step_message
        self.step_number = step_num
        self.total_steps = total_steps

    def complete_chat(self, chat_name: str) -> None:
        """
        Mark a chat as completed.

        Args:
            chat_name: Name of completed chat
        """
        self.completed_chats += 1
        self.current_chat = ""
        self.current_step = ""
        self.step_number = 0
        self.log_activity(f"[green]✓[/green] {chat_name} exported", "success")

    def fail_chat(self, chat_name: str, error: str) -> None:
        """
        Mark a chat as failed.

        Args:
            chat_name: Name of failed chat
            error: Error message
        """
        self.current_chat = ""
        self.current_step = ""
        self.step_number = 0
        self.log_activity(f"[red]✗[/red] {chat_name}: {error}", "error")

    def start_processing(self) -> None:
        """Start processing mode."""
        self.mode = "processing"
        self.phase_number = 0
        self.current_phase = ""
        self.log_activity("Starting post-processing...", "info")

    def update_processing_progress(
        self,
        phase: Optional[str] = None,
        phase_num: Optional[int] = None,
    ) -> None:
        """
        Update processing progress.

        Args:
            phase: Current phase name
            phase_num: Current phase number (1-indexed)
        """
        if phase is not None:
            self.current_phase = phase
        if phase_num is not None:
            self.phase_number = phase_num

    def update_pipeline_phase(self, phase: str) -> None:
        """
        Update the active pipeline phase from a phase key.

        Translates pipeline phase strings (e.g. "download", "build_output")
        to display names and updates the phase number.

        Args:
            phase: Pipeline phase key (e.g. "download", "extract", "transcribe",
                   "build_output", "organize", "cleanup")
        """
        display_name = self.PHASE_DISPLAY_MAP.get(phase, phase.title())
        try:
            phase_idx = self.PROCESSING_PHASES.index(display_name)
        except ValueError:
            phase_idx = self.phase_number - 1  # keep current if unknown
        self.current_phase = display_name
        self.phase_number = phase_idx + 1
        # Reset item-level progress when entering a new phase
        self.pipeline_item = ""
        self.pipeline_item_current = 0
        self.pipeline_item_total = 0

    def update_pipeline_item(
        self,
        item_name: str,
        current: int,
        total: int,
    ) -> None:
        """
        Update per-item progress within the current pipeline phase.

        Args:
            item_name: Name of the item being processed (filename, archive, etc.)
            current: Current item number (1-indexed)
            total: Total number of items in this phase
        """
        self.pipeline_item = item_name
        self.pipeline_item_current = current
        self.pipeline_item_total = total

    def complete_phase(self, phase_name: str) -> None:
        """
        Mark a phase as completed.

        Args:
            phase_name: Name of completed phase
        """
        # Clear item-level progress
        self.pipeline_item = ""
        self.pipeline_item_current = 0
        self.pipeline_item_total = 0
        self.log_activity(f"[green]✓[/green] {phase_name} complete", "success")

    def set_complete(self, summary: dict) -> None:
        """
        Set completion state with summary.

        Args:
            summary: Dictionary with completion summary
        """
        self.mode = "complete"

        # Build summary text
        summary_text = self.query_one("#summary-text", Static)
        lines = []

        exported = summary.get("exported", 0)
        failed = summary.get("failed", 0)
        transcribed = summary.get("transcribed", 0)
        output_path = summary.get("output_path", "")

        if exported > 0:
            lines.append(f"[green]✓[/green] Exported: {exported} chats")
        if failed > 0:
            lines.append(f"[red]✗[/red] Failed: {failed} chats")
        if transcribed > 0:
            lines.append(f"[green]✓[/green] Transcribed: {transcribed} files")
        if output_path:
            lines.append(f"\nOutput: [cyan]{output_path}[/cyan]")

        summary_text.update("\n".join(lines) if lines else "Complete!")
        self.log_activity("All operations complete!", "success")

    def set_error(self, error: str) -> None:
        """
        Set error state.

        Args:
            error: Error message
        """
        self.mode = "error"
        self.error_message = error
        self.has_error = True
        self.log_activity(f"Error: {error}", "error")

    def pause(self) -> None:
        """Pause progress."""
        self.is_paused = True
        self.log_activity("Paused", "warning")

    def resume(self) -> None:
        """Resume progress."""
        self.is_paused = False
        self.log_activity("Resumed", "info")

    def log_activity(
        self,
        message: str,
        level: str = "info",
    ) -> None:
        """
        Add a message to the activity log.

        Args:
            message: Message text
            level: Log level (info, success, warning, error)
        """
        try:
            richlog = self.query_one("#activity-log", RichLog)
            timestamp = datetime.now().strftime("%H:%M:%S")

            if level == "success":
                prefix = "[green]OK[/green]"
            elif level == "warning":
                prefix = "[yellow]![/yellow]"
            elif level == "error":
                prefix = "[red]X[/red]"
            else:
                prefix = "[cyan]→[/cyan]"

            formatted = f"[dim]{timestamp}[/dim] {prefix} {message}"
            richlog.write(formatted)

            # Store message
            self._activity_messages.append(formatted)
            if len(self._activity_messages) > 100:
                self._activity_messages = self._activity_messages[-100:]
        except Exception:
            pass  # Widget may not be mounted

    def clear_activity(self) -> None:
        """Clear the activity log."""
        try:
            richlog = self.query_one("#activity-log", RichLog)
            richlog.clear()
            self._activity_messages = []
        except Exception:
            pass
