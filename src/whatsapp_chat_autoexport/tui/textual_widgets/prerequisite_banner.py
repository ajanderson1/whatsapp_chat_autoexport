"""
Prerequisite banner widget — single-line status row for the Select tab.

Shows the state of one prerequisite (Drive auth, API key, WhatsApp version)
with a coloured indicator and a "where to fix" hint. Banners are read-only;
the user changes settings on the Settings tab, not here.
"""

from enum import Enum

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class BannerStatus(Enum):
    """Visual states for a prerequisite banner."""

    OK = "ok"
    WARNING = "warning"
    UNMET = "unmet"


class PrerequisiteBanner(Widget):
    """Single-line prerequisite status banner.

    Args:
        key: Unique key for this banner (used as widget ID suffix).
        label: Short description, e.g. "Google Drive".
        status: One of BannerStatus.OK / WARNING / UNMET.
        detail: Right-side detail text, e.g. "signed in as foo@gmail.com".
        hint: Action hint, e.g. "open Settings tab to configure".
    """

    DEFAULT_CSS = """
    PrerequisiteBanner {
        height: auto;
        padding: 0 1;
        margin: 0 0 0 0;
    }

    PrerequisiteBanner .banner-row {
        height: auto;
    }

    PrerequisiteBanner .banner-icon {
        width: 3;
    }

    PrerequisiteBanner .banner-label {
        width: auto;
    }

    PrerequisiteBanner .banner-detail {
        width: 1fr;
        color: $text-muted;
    }

    PrerequisiteBanner.banner-ok .banner-icon {
        color: $success;
    }

    PrerequisiteBanner.banner-warning .banner-icon {
        color: $warning;
    }

    PrerequisiteBanner.banner-unmet .banner-icon {
        color: $error;
    }

    PrerequisiteBanner.banner-ok {
        display: none;
    }
    """

    def __init__(
        self,
        key: str,
        label: str = "",
        status: BannerStatus = BannerStatus.OK,
        detail: str = "",
        hint: str = "",
        **kwargs,
    ) -> None:
        super().__init__(id=f"banner-{key}", **kwargs)
        self._key = key
        self._label = label
        self._status = status
        self._detail = detail
        self._hint = hint

    def compose(self) -> ComposeResult:
        icon = self._icon_for_status(self._status)
        text = self._build_text()
        yield Static(icon, classes="banner-icon")
        yield Static(text, classes="banner-detail", id=f"banner-text-{self._key}")

    def _icon_for_status(self, status: BannerStatus) -> str:
        if status == BannerStatus.OK:
            return "[green]\u2713[/green]"
        elif status == BannerStatus.WARNING:
            return "[yellow]\u26a0[/yellow]"
        else:
            return "[red]\u2717[/red]"

    def _build_text(self) -> str:
        parts = [f"[bold]{self._label}[/bold]"]
        if self._detail:
            parts.append(f" \u2014 {self._detail}")
        if self._hint and self._status != BannerStatus.OK:
            parts.append(f" [dim]({self._hint})[/dim]")
        return "".join(parts)

    def update_status(
        self,
        status: BannerStatus,
        detail: str = "",
        hint: str = "",
    ) -> None:
        """Update the banner's visual state."""
        self._status = status
        self._detail = detail
        self._hint = hint

        # Update CSS class
        self.remove_class("banner-ok", "banner-warning", "banner-unmet")
        self.add_class(f"banner-{status.value}")

        # Update content
        try:
            icon_widget = self.query_one(".banner-icon", Static)
            icon_widget.update(self._icon_for_status(status))
            text_widget = self.query_one(f"#banner-text-{self._key}", Static)
            text_widget.update(self._build_text())
        except Exception:
            pass

    @property
    def status(self) -> BannerStatus:
        return self._status

    @property
    def is_blocking(self) -> bool:
        """True if this prerequisite is unmet (blocks export)."""
        return self._status == BannerStatus.UNMET
