"""Tests for the PreflightPanel widget."""

from datetime import datetime

import pytest
from textual.app import App, ComposeResult

from whatsapp_chat_autoexport.preflight.report import (
    CheckResult,
    PreflightReport,
    Status,
)
from whatsapp_chat_autoexport.tui.textual_widgets.preflight_panel import (
    PreflightPanel,
)


class _PanelHost(App):
    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _report(*specs):
    results = [
        CheckResult(
            provider=p,
            display_name=name,
            status=s,
            summary=summary,
        )
        for p, name, s, summary in specs
    ]
    return PreflightReport(
        results=results,
        started_at=datetime.now(),
        duration_ms=42,
    )


@pytest.mark.asyncio
async def test_initial_render_shows_pending():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        text = panel.render_text()
        assert "Preflight" in text


@pytest.mark.asyncio
async def test_set_report_renders_three_rows():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "Key valid"),
                ("elevenlabs", "ElevenLabs", Status.WARN, "8,420 chars left"),
                ("drive", "Google Drive", Status.HARD_FAIL, "Only 200 MB free"),
            )
        )
        await pilot.pause()
        text = panel.render_text()
        assert "OpenAI (Whisper)" in text
        assert "ElevenLabs" in text
        assert "Google Drive" in text


@pytest.mark.asyncio
async def test_has_hard_fail_property():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "x"),
                ("elevenlabs", "ElevenLabs", Status.HARD_FAIL, "y"),
            )
        )
        assert panel.has_hard_fail is True


@pytest.mark.asyncio
async def test_no_hard_fail_property_initial():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        assert panel.has_hard_fail is False


@pytest.mark.asyncio
async def test_clear_resets_to_pending():
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "Key valid"),
            )
        )
        await pilot.pause()
        # Verify the report row is visible first
        assert "OpenAI (Whisper)" in panel.render_text()

        panel.clear()
        await pilot.pause()
        text = panel.render_text()
        assert "OpenAI (Whisper)" not in text
        assert "Preflight" in text
        assert panel.has_hard_fail is False


@pytest.mark.asyncio
async def test_shrink_hides_surplus_rows():
    """Setting a smaller report after a larger one must hide the surplus rows."""
    panel = PreflightPanel()
    async with _PanelHost(panel).run_test() as pilot:
        await pilot.pause()
        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "x"),
                ("elevenlabs", "ElevenLabs", Status.OK, "y"),
                ("drive", "Google Drive", Status.OK, "z"),
            )
        )
        await pilot.pause()
        text_three = panel.render_text()
        assert "Google Drive" in text_three

        panel.set_report(
            _report(
                ("whisper", "OpenAI (Whisper)", Status.OK, "x"),
                ("elevenlabs", "ElevenLabs", Status.OK, "y"),
            )
        )
        await pilot.pause()
        text_two = panel.render_text()
        assert "Google Drive" not in text_two
        assert "OpenAI (Whisper)" in text_two
        assert "ElevenLabs" in text_two
