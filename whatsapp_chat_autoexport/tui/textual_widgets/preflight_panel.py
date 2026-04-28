"""PreflightPanel — read-only Textual widget showing the preflight report.

Lives inside ConnectPane (above the device list). When `set_report()` is
called, renders three labelled rows with status icons. Exposes
`has_hard_fail` so the parent pane can gate the Connected message.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ...preflight.report import PreflightReport, Status

_STATUS_ICON = {
    Status.OK: "[green]✓[/green]",
    Status.WARN: "[yellow]⚠[/yellow]",
    Status.HARD_FAIL: "[red]✗[/red]",
    Status.SKIPPED: "[dim]—[/dim]",
}

_PENDING_TEXT = "Preflight: not yet run"


class PreflightPanel(Vertical):
    """Read-only view of the preflight report.

    State machine:
        - mounted with no report → "Preflight: not yet run"
        - set_report(report)     → render rows
        - clear()                → back to pending

    Implementation note: rather than destroy and re-create children (which
    causes duplicate-ID errors in Textual when the remove is not awaited),
    the panel accumulates row Statics on first ``set_report`` call and reuses
    them on subsequent calls, growing or shrinking the list as needed.
    The summary Static is always the last child and is updated in place.
    """

    DEFAULT_CSS = """
    PreflightPanel {
        height: auto;
        border: solid $accent;
        padding: 0 1;
        margin-bottom: 1;
    }
    PreflightPanel > Static.preflight-row {
        height: 1;
    }
    PreflightPanel > Static#preflight-summary {
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._report: Optional[PreflightReport] = None
        # Cached row widgets created after first set_report call.
        self._row_widgets: list[Static] = []

    def compose(self) -> ComposeResult:
        yield Static(_PENDING_TEXT, id="preflight-summary")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def has_hard_fail(self) -> bool:
        return bool(self._report and self._report.has_hard_fail)

    def set_report(self, report: PreflightReport) -> None:
        """Replace contents with rendered rows for the given report."""
        self._report = report

        # Build the row text strings.
        row_texts = [
            f"{_STATUS_ICON[r.status]} {r.display_name}: {r.summary}"
            for r in report.results
        ]

        # Grow row widget list if needed (mount new ones before summary).
        summary_widget = self.query_one("#preflight-summary", Static)
        while len(self._row_widgets) < len(row_texts):
            new_row = Static("", classes="preflight-row")
            self.mount(new_row, before=summary_widget)
            self._row_widgets.append(new_row)

        # Hide surplus row widgets by clearing their text.
        for i, row_widget in enumerate(self._row_widgets):
            if i < len(row_texts):
                row_widget.update(row_texts[i])
                row_widget.display = True
            else:
                row_widget.update("")
                row_widget.display = False

        # Update summary line.
        n_warn = sum(1 for x in report.results if x.status == Status.WARN)
        n_fail = sum(1 for x in report.results if x.status == Status.HARD_FAIL)
        if n_fail:
            tail = (
                f"[red]{n_fail} hard "
                f"{'failure' if n_fail == 1 else 'failures'}[/red] — fix above to continue."
            )
        else:
            warn_word = "warning" if n_warn == 1 else "warnings"
            tail = f"{n_warn} {warn_word}, ready to continue ({report.duration_ms} ms)"
        summary_widget.update(tail)

    def clear(self) -> None:
        """Reset the panel to its pre-run state."""
        self._report = None
        for row_widget in self._row_widgets:
            row_widget.update("")
            row_widget.display = False
        try:
            summary_widget = self.query_one("#preflight-summary", Static)
            summary_widget.update(_PENDING_TEXT)
        except Exception:
            pass

    def render_text(self) -> str:
        """Return the panel's combined text content (for tests).

        Uses the ``content`` attribute of each visible Static child, which
        contains the raw markup string passed at construction or via
        ``update()``.
        """
        parts = []
        for child in self.children:
            if isinstance(child, Static) and child.display:
                raw = str(child.content)
                if raw:
                    parts.append(raw)
        return "\n".join(parts)
