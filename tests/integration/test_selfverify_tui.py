"""T1 self-verification: drive the real app object via Textual's pilot.

Proves the agent can launch the TUI in-process, navigate, and assert on
screen state deterministically, and capture a rendered snapshot as evidence.
Mirrors tests/integration/test_textual_tui.py.
"""

import pytest

from whatsapp_chat_autoexport.tui.textual_screens.main_screen import MainScreen


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selfverify_tui_launches_and_navigates(tui_app):
    """The loop can launch the TUI and confirm it reaches MainScreen."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(tui_app.screen, MainScreen)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selfverify_tui_snapshot_captures_screen(tui_app, tmp_path):
    """The loop can capture a rendered snapshot as evidence."""
    async with tui_app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        snapshot = tui_app.export_screenshot()  # Textual returns an SVG string
        out = tmp_path / "t1-snapshot.svg"
        out.write_text(snapshot)
        assert out.stat().st_size > 0
