"""
Manual smoke-tests for the preflight probes.

These tests exercise all three probes against real API keys and a real Drive
token file.  They are skipped automatically in CI because the required
environment variables are not set there.

Run with real credentials:

    poetry run pytest tests/manual/ -v -s -m requires_api

Individual probes can be run in isolation:

    OPENAI_API_KEY=sk-... poetry run pytest tests/manual/test_preflight_live.py::test_whisper_probe_live -v -s
    ELEVENLABS_API_KEY=... poetry run pytest tests/manual/test_preflight_live.py::test_elevenlabs_probe_live -v -s
    poetry run pytest tests/manual/test_preflight_live.py::test_drive_probe_live -v -s
    poetry run pytest tests/manual/test_preflight_live.py::test_run_preflight_live -v -s
"""

import os

import pytest

# All tests in this module require real credentials and must be run manually.
pytestmark = [pytest.mark.requires_api, pytest.mark.manual]


def test_whisper_probe_live():
    """Hit GET /v1/models with a real OPENAI_API_KEY and print the result."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    from whatsapp_chat_autoexport.preflight.probes.whisper import check_whisper

    result = check_whisper(api_key)
    print(f"\nWhisper probe result: {result}")
    print(f"  provider     : {result.provider}")
    print(f"  display_name : {result.display_name}")
    print(f"  status       : {result.status}")
    print(f"  summary      : {result.summary}")
    if result.details:
        print(f"  details      : {result.details}")
    if result.error:
        print(f"  error        : {result.error}")

    assert result.provider == "whisper"
    assert result.status is not None


def test_elevenlabs_probe_live():
    """Hit GET /v1/user/subscription with a real ELEVENLABS_API_KEY and print the result."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        pytest.skip("ELEVENLABS_API_KEY not set")

    from whatsapp_chat_autoexport.preflight.probes.elevenlabs import check_elevenlabs

    result = check_elevenlabs(api_key)
    print(f"\nElevenLabs probe result: {result}")
    print(f"  provider     : {result.provider}")
    print(f"  display_name : {result.display_name}")
    print(f"  status       : {result.status}")
    print(f"  summary      : {result.summary}")
    if result.details:
        print(f"  details      : {result.details}")
    if result.error:
        print(f"  error        : {result.error}")

    assert result.provider == "elevenlabs"
    assert result.status is not None


def test_drive_probe_live():
    """Probe Drive auth + storage quota using whatever token file is present."""
    from whatsapp_chat_autoexport.google_drive.auth import GoogleDriveAuth

    auth = GoogleDriveAuth()
    if not auth.has_credentials():
        pytest.skip("No Drive token file found — run the OAuth flow first")

    from whatsapp_chat_autoexport.preflight.probes.drive import check_drive

    result = check_drive(auth)
    print(f"\nDrive probe result: {result}")
    print(f"  provider     : {result.provider}")
    print(f"  display_name : {result.display_name}")
    print(f"  status       : {result.status}")
    print(f"  summary      : {result.summary}")
    if result.details:
        for key, value in result.details.items():
            print(f"  {key:<30}: {value}")
    if result.error:
        print(f"  error        : {result.error}")

    assert result.provider == "drive"
    assert result.status is not None


def test_run_preflight_live():
    """Run the full run_preflight() aggregator and print the formatted report.

    Skips if neither OPENAI_API_KEY nor ELEVENLABS_API_KEY is set and no Drive
    token exists — otherwise there would be nothing useful to test.
    """
    from whatsapp_chat_autoexport.google_drive.auth import GoogleDriveAuth

    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_elevenlabs = bool(os.getenv("ELEVENLABS_API_KEY"))
    has_drive = GoogleDriveAuth().has_credentials()

    if not any([has_openai, has_elevenlabs, has_drive]):
        pytest.skip(
            "No credentials available — set OPENAI_API_KEY, ELEVENLABS_API_KEY, "
            "or provide a Drive token file"
        )

    from whatsapp_chat_autoexport.preflight.runner import (
        format_report_for_stderr,
        run_preflight,
    )

    report = run_preflight(skip_drive=not has_drive)

    formatted = format_report_for_stderr(report)
    print(f"\n{formatted}")
    print(f"\nRaw report:")
    print(f"  started_at   : {report.started_at}")
    print(f"  duration_ms  : {report.duration_ms}")
    print(f"  has_hard_fail: {report.has_hard_fail}")
    print(f"  has_warning  : {report.has_warning}")
    for r in report.results:
        print(f"  [{r.provider}] status={r.status} summary={r.summary!r}")

    assert len(report.results) >= 1
    assert report.duration_ms >= 0
