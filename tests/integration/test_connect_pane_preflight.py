"""
Integration tests for ConnectPane + PreflightPanel interaction.

These tests verify that:
1. PreflightPanel is present in the ConnectPane DOM.
2. When skip_preflight=True, run_preflight is never called.
3. set_report() renders the expected provider name in the panel.
4. A HARD_FAIL report blocks the dry-run binding from posting Connected.
5. An OK report allows the dry-run binding to post Connected.

All tests use a minimal host App (not the full WhatsAppExporterApp) so that
the test fixture is fast and isolated.  subprocess.run is patched to return
an empty device list so no real ADB is required.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from textual.app import App, ComposeResult

from whatsapp_chat_autoexport.tui.textual_panes.connect_pane import ConnectPane
from whatsapp_chat_autoexport.tui.textual_widgets.activity_log import ActivityLog
from whatsapp_chat_autoexport.tui.textual_widgets.preflight_panel import PreflightPanel
from whatsapp_chat_autoexport.preflight.report import CheckResult, PreflightReport, Status


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _ok_report() -> PreflightReport:
    return PreflightReport(
        results=[
            CheckResult(
                provider="whisper",
                display_name="OpenAI (Whisper)",
                status=Status.OK,
                summary="Key valid",
            )
        ],
        started_at=datetime.now(),
        duration_ms=50,
    )


def _hard_fail_report() -> PreflightReport:
    return PreflightReport(
        results=[
            CheckResult(
                provider="elevenlabs",
                display_name="ElevenLabs",
                status=Status.HARD_FAIL,
                summary="Quota exhausted",
                error="0 chars left",
            ),
        ],
        started_at=datetime.now(),
        duration_ms=50,
    )


# ---------------------------------------------------------------------------
# Minimal host app
# ---------------------------------------------------------------------------


def _make_empty_adb_result() -> MagicMock:
    mock_result = MagicMock()
    mock_result.stdout = "List of devices attached\n\n"
    mock_result.returncode = 0
    return mock_result


class _Host(App):
    """Minimal host that wires ConnectPane + ActivityLog into a screen."""

    def __init__(self, skip_preflight: bool = False) -> None:
        super().__init__()
        self.skip_preflight = skip_preflight
        self._received_connected: list = []

    def compose(self) -> ComposeResult:
        yield ActivityLog()
        yield ConnectPane()

    def on_connect_pane_connected(self, message: ConnectPane.Connected) -> None:
        self._received_connected.append(message)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preflight_panel_present():
    """#preflight-panel must exist in the DOM when ConnectPane is mounted."""
    app = _Host()
    with patch("subprocess.run", return_value=_make_empty_adb_result()), patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight",
        return_value=_ok_report(),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one("#preflight-panel", PreflightPanel)
            assert panel is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preflight_skipped_when_skip_preflight_true():
    """When app.skip_preflight=True, run_preflight must never be called."""
    app = _Host(skip_preflight=True)
    with patch("subprocess.run", return_value=_make_empty_adb_result()), patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight"
    ) as preflight_mock:
        async with app.run_test(size=(120, 40)) as pilot:
            # Give any workers a moment to complete
            await pilot.pause()
            await asyncio.sleep(0.3)
            await pilot.pause()

        preflight_mock.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preflight_panel_shows_report():
    """After set_report() with an OK result, render_text() contains the provider name."""
    app = _Host()
    with patch("subprocess.run", return_value=_make_empty_adb_result()), patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight",
        return_value=_ok_report(),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            panel = app.query_one("#preflight-panel", PreflightPanel)
            # Call set_report directly with a known report
            report = _ok_report()
            panel.set_report(report)
            await pilot.pause()

            text = panel.render_text()
            assert "OpenAI (Whisper)" in text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preflight_blocks_dry_run_on_hard_fail():
    """When the panel holds a HARD_FAIL report, action_use_dry_run must NOT post Connected."""
    app = _Host()
    with patch("subprocess.run", return_value=_make_empty_adb_result()), patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight",
        return_value=_hard_fail_report(),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Inject a HARD_FAIL report into the panel directly
            panel = app.query_one("#preflight-panel", PreflightPanel)
            panel.set_report(_hard_fail_report())
            await pilot.pause()

            # Trigger dry-run
            connect_pane = app.query_one(ConnectPane)
            connect_pane.action_use_dry_run()
            await pilot.pause()

            # Connected must NOT have been posted
            assert len(app._received_connected) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_preflight_allows_dry_run_on_ok():
    """When the panel holds an OK report, action_use_dry_run MUST post Connected."""
    app = _Host()
    with patch("subprocess.run", return_value=_make_empty_adb_result()), patch(
        "whatsapp_chat_autoexport.tui.textual_panes.connect_pane.run_preflight",
        return_value=_ok_report(),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Inject an OK report into the panel directly
            panel = app.query_one("#preflight-panel", PreflightPanel)
            panel.set_report(_ok_report())
            await pilot.pause()

            # Trigger dry-run
            connect_pane = app.query_one(ConnectPane)
            connect_pane.action_use_dry_run()
            await pilot.pause()

            # Connected MUST have been posted
            assert len(app._received_connected) == 1
            assert app._received_connected[0].driver is None
