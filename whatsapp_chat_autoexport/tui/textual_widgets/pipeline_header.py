"""
Pipeline header widget showing the 4 stages of the export workflow.

Displays:
- CONNECT -> DISCOVER MESSAGES -> SELECT MESSAGES -> PROCESS MESSAGES
- Active stage highlighted in green
- Completed stages in primary color
- Inactive stages dimmed
"""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.reactive import reactive
from textual.containers import Horizontal

from ..textual_app import PipelineStage


class PipelineHeader(Widget):
    """
    Widget displaying the pipeline stages header.

    Shows 4 stages with visual indicators:
    - Active: Bright green, bold
    - Completed: Primary color
    - Inactive: Dimmed gray
    """

    DEFAULT_CSS = """
    PipelineHeader {
        height: 5;
        background: $primary-background;
        border: solid $primary;
        padding: 0 1;
    }
    """

    # Current active stage
    current_stage: reactive[PipelineStage] = reactive(PipelineStage.CONNECT)

    STAGES = [
        (PipelineStage.CONNECT, "1", "CONNECT"),
        (PipelineStage.DISCOVER, "2", "DISCOVER MESSAGES"),
        (PipelineStage.SELECT, "3", "SELECT MESSAGES"),
        (PipelineStage.PROCESS, "4", "PROCESS MESSAGES"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the header layout."""
        yield Static("WHATSAPP EXPORTER", classes="title")
        with Horizontal(classes="stages"):
            for stage, num, name in self.STAGES:
                yield Static(
                    self._format_stage(stage, num, name),
                    id=f"stage-{stage.name.lower()}",
                    classes="stage",
                )

    def on_mount(self) -> None:
        """Refresh stages after mounting to ensure correct display."""
        self._refresh_stages()

    def _format_stage(self, stage: PipelineStage, num: str, name: str) -> str:
        """
        Format a stage label with appropriate styling.

        Args:
            stage: The pipeline stage
            num: Stage number
            name: Stage display name

        Returns:
            Rich-formatted string
        """
        current_idx = self.current_stage.value
        stage_idx = stage.value

        if stage_idx == current_idx:
            # Active stage
            return f"[bold green]({num}) {name}[/bold green]  [green][ACTIVE][/green]"
        elif stage_idx < current_idx:
            # Completed stage
            return f"[cyan]({num}) {name}[/cyan]  [dim][DONE][/dim]"
        else:
            # Inactive stage
            return f"[dim]({num}) {name}[/dim]"

    def watch_current_stage(self, stage: PipelineStage) -> None:
        """React to stage changes by updating all stage labels."""
        self._refresh_stages()

    def _refresh_stages(self) -> None:
        """Refresh all stage labels based on current state."""
        if not self.is_mounted:
            return  # Skip refresh before widgets exist
        for stage, num, name in self.STAGES:
            widget = self.query_one(f"#stage-{stage.name.lower()}", Static)
            widget.update(self._format_stage(stage, num, name))

    def set_stage(self, stage: PipelineStage) -> None:
        """
        Set the current pipeline stage.

        Args:
            stage: The new active stage
        """
        self.current_stage = stage
        # Explicitly refresh to ensure UI updates even if watcher doesn't fire
        self._refresh_stages()
