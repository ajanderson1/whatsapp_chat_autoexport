"""
Tests for adaptive Drive polling with progressive backoff (Unit 3).

Covers:
- Progressive backoff schedule (2s, 2s, 4s, 4s, 8s, 8s, ...)
- chat_name filter in Drive API query
- include_media timeout defaults
- Error handling during polling
- Concurrent polling with different chat_name filters
"""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
from typing import Optional, Dict, Any, List

import pytest

from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient
from whatsapp_chat_autoexport.google_drive.drive_manager import GoogleDriveManager
from whatsapp_chat_autoexport.pipeline import PipelineConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file_metadata(
    name: str = "WhatsApp Chat with Alice.zip",
    created_minutes_ago: float = 1.0,
    size: int = 1024,
) -> Dict[str, Any]:
    """Create a fake Drive file metadata dict."""
    created = datetime.now(timezone.utc) - timedelta(minutes=created_minutes_ago)
    return {
        "id": f"file_{name.replace(' ', '_')}",
        "name": name,
        "mimeType": "application/zip",
        "size": str(size),
        "createdTime": created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "modifiedTime": created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "parents": ["root"],
    }


def _build_client(service_mock: Optional[MagicMock] = None) -> GoogleDriveClient:
    """Build a GoogleDriveClient with a mocked auth and optionally injected service."""
    auth = MagicMock()
    logger = MagicMock()
    client = GoogleDriveClient(auth=auth, logger=logger)
    if service_mock is not None:
        client.service = service_mock
    else:
        client.service = MagicMock()
    return client


class _ListResultSequence:
    """
    Helper that returns different list() results on successive calls.

    Each entry in `responses` is either a list of file dicts (wrapped into
    {'files': ...}) or an Exception to be raised.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._call_idx = 0

    def __call__(self, *args, **kwargs):
        """Return next response when .execute() is called."""
        idx = self._call_idx
        self._call_idx += 1
        if idx < len(self._responses):
            resp = self._responses[idx]
        else:
            # After exhausting responses, return empty
            resp = []

        if isinstance(resp, Exception):
            raise resp
        # Return a mock whose .execute() returns the files dict
        m = MagicMock()
        m.execute.return_value = {"files": resp}
        return m


# ---------------------------------------------------------------------------
# Tests: Backoff schedule
# ---------------------------------------------------------------------------

class TestAdaptiveBackoff:
    """Verify progressive backoff intervals."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_file_found_on_first_poll(self, mock_time, mock_sleep):
        """File found on first poll -- no sleep at all."""
        mock_time.return_value = 0.0  # elapsed always 0

        client = _build_client()
        file_meta = _make_file_metadata()

        client.service.files().list.return_value.execute.return_value = {
            "files": [file_meta]
        }

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=60,
        )

        assert result is not None
        assert result["name"] == file_meta["name"]
        mock_sleep.assert_not_called()

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_file_found_on_fifth_poll_backoff_schedule(self, mock_time, mock_sleep):
        """File found on 5th poll -- intervals should be 2, 2, 4, 4."""
        # Simulate time progressing but never hitting timeout
        elapsed_values = [0.0] * 20  # Always return 0 so we never timeout
        mock_time.side_effect = elapsed_values

        client = _build_client()
        file_meta = _make_file_metadata()

        # First 4 polls: empty results. 5th poll: file found.
        seq = _ListResultSequence([[], [], [], [], [file_meta]])
        client.service.files().list = seq

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=300,
        )

        assert result is not None
        assert result["name"] == file_meta["name"]

        # Verify sleep calls: polls 1-4 sleep, poll 5 finds file
        # Poll 1: interval=2 (poll_count=1, no doubling yet)
        # Poll 2: interval=2 (poll_count=2, doubles after sleep -> 4)
        # Poll 3: interval=4 (poll_count=3, no doubling)
        # Poll 4: interval=4 (poll_count=4, doubles after sleep -> 8)
        assert mock_sleep.call_count == 4
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args == [2, 2, 4, 4]

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_intervals_cap_at_max(self, mock_time, mock_sleep):
        """After enough polls, interval caps at max_interval and stays there."""
        # Return increasing elapsed times, timeout at "100s"
        call_count = [0]

        def time_fn():
            call_count[0] += 1
            # Timeout after poll 8
            if call_count[0] > 16:
                return 200.0  # trigger timeout
            return 0.0

        mock_time.side_effect = time_fn

        client = _build_client()
        file_meta = _make_file_metadata()

        # 7 empty polls, then file on poll 8
        seq = _ListResultSequence([[], [], [], [], [], [], [], [file_meta]])
        client.service.files().list = seq

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=300,
        )

        assert result is not None
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        # Expected: 2, 2, 4, 4, 8, 8, 8
        assert sleep_args == [2, 2, 4, 4, 8, 8, 8]


# ---------------------------------------------------------------------------
# Tests: Timeout behavior
# ---------------------------------------------------------------------------

class TestTimeoutBehavior:
    """Verify timeout handling and include_media defaults."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_timeout_returns_none(self, mock_time, mock_sleep):
        """When timeout is reached, returns None."""
        # First call = start_time, second call = already past timeout
        mock_time.side_effect = [0.0, 200.0]

        client = _build_client()
        client.service.files().list.return_value.execute.return_value = {"files": []}

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=60,
        )

        assert result is None

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_include_media_false_uses_120s_timeout(self, mock_time, mock_sleep):
        """include_media=False with default timeout should use 120s."""
        # start_time = 0, elapsed check = 125 (> 120)
        mock_time.side_effect = [0.0, 125.0]

        client = _build_client()
        client.service.files().list.return_value.execute.return_value = {"files": []}

        result = client.poll_for_new_export(
            include_media=False,
            timeout=300,  # default, but should be overridden to 120
        )

        assert result is None
        # Logger should mention 120s timeout
        client.logger.error.assert_called()
        error_msg = client.logger.error.call_args[0][0]
        assert "120" in error_msg

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_include_media_true_uses_300s_timeout(self, mock_time, mock_sleep):
        """include_media=True keeps the full 300s timeout."""
        # At 125s we should still be polling (not timed out)
        mock_time.side_effect = [0.0, 125.0, 125.0, 305.0]

        client = _build_client()
        file_meta = _make_file_metadata()

        # First poll: nothing. Second poll would happen but we timeout.
        seq = _ListResultSequence([[], []])
        client.service.files().list = seq

        result = client.poll_for_new_export(
            include_media=True,
            timeout=300,
        )

        # Should have polled at 125s (not timed out), then timed out at 305s
        assert result is None
        assert mock_sleep.call_count >= 1  # At least one poll happened before timeout

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_explicit_timeout_not_overridden_by_include_media(self, mock_time, mock_sleep):
        """When caller passes explicit non-default timeout, include_media=False does not override."""
        mock_time.side_effect = [0.0, 65.0]

        client = _build_client()
        client.service.files().list.return_value.execute.return_value = {"files": []}

        result = client.poll_for_new_export(
            include_media=False,
            timeout=60,  # Explicit non-default
        )

        assert result is None
        error_msg = client.logger.error.call_args[0][0]
        assert "60" in error_msg


# ---------------------------------------------------------------------------
# Tests: chat_name filter
# ---------------------------------------------------------------------------

class TestChatNameFilter:
    """Verify chat_name parameter scopes the Drive query."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_chat_name_appended_to_query(self, mock_time, mock_sleep):
        """When chat_name is provided, query includes name filter."""
        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata(name="WhatsApp Chat with Alice.zip")

        client.service.files().list.return_value.execute.return_value = {
            "files": [file_meta]
        }

        result = client.poll_for_new_export(chat_name="Alice", timeout=60)

        assert result is not None
        # Verify the query passed to list() contained 'Alice'
        list_call_kwargs = client.service.files().list.call_args
        query = list_call_kwargs.kwargs.get("q", "") or list_call_kwargs[1].get("q", "")
        assert "Alice" in query

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_chat_name_with_apostrophe_escaped(self, mock_time, mock_sleep):
        """Chat names with apostrophes should be escaped in query."""
        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata(name="WhatsApp Chat with O'Brien.zip")

        client.service.files().list.return_value.execute.return_value = {
            "files": [file_meta]
        }

        result = client.poll_for_new_export(chat_name="O'Brien", timeout=60)

        assert result is not None
        list_call_kwargs = client.service.files().list.call_args
        query = list_call_kwargs.kwargs.get("q", "") or list_call_kwargs[1].get("q", "")
        assert "O\\'Brien" in query

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_no_chat_name_uses_broad_query(self, mock_time, mock_sleep):
        """Without chat_name, query is the original broad pattern."""
        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata()

        client.service.files().list.return_value.execute.return_value = {
            "files": [file_meta]
        }

        result = client.poll_for_new_export(timeout=60)

        list_call_kwargs = client.service.files().list.call_args
        query = list_call_kwargs.kwargs.get("q", "") or list_call_kwargs[1].get("q", "")
        assert "WhatsApp Chat with" in query
        # Should NOT have an additional name filter
        assert query.count("name contains") == 1


# ---------------------------------------------------------------------------
# Tests: Error handling during polling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify error handling preserves backoff schedule."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_http_error_retries_with_current_interval(self, mock_time, mock_sleep):
        """HTTP error during poll retries using current backoff interval."""
        from googleapiclient.errors import HttpError
        from unittest.mock import PropertyMock

        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata()

        http_error = HttpError(
            resp=MagicMock(status=500),
            content=b"Internal Server Error"
        )

        # Poll 1: HTTP error, Poll 2: success
        call_idx = [0]
        def list_side_effect(*args, **kwargs):
            call_idx[0] += 1
            m = MagicMock()
            if call_idx[0] == 1:
                m.execute.side_effect = http_error
            else:
                m.execute.return_value = {"files": [file_meta]}
            return m

        client.service.files().list = list_side_effect

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=60,
        )

        assert result is not None
        # Only one sleep (from the error), at the initial interval of 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 2

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_general_error_retries_with_current_interval(self, mock_time, mock_sleep):
        """General exception during poll retries at current interval."""
        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata()

        call_idx = [0]
        def list_side_effect(*args, **kwargs):
            call_idx[0] += 1
            m = MagicMock()
            if call_idx[0] == 1:
                m.execute.side_effect = RuntimeError("connection reset")
            else:
                m.execute.return_value = {"files": [file_meta]}
            return m

        client.service.files().list = list_side_effect

        result = client.poll_for_new_export(
            initial_interval=3,
            max_interval=10,
            timeout=60,
        )

        assert result is not None
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 3

    def test_not_connected_returns_none(self):
        """If service is None, returns None immediately."""
        auth = MagicMock()
        client = GoogleDriveClient(auth=auth, logger=MagicMock())
        client.service = None

        result = client.poll_for_new_export()
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Concurrent polling with different chat_name filters
# ---------------------------------------------------------------------------

class TestConcurrentPolling:
    """Two concurrent polls with different chat_name filters find only their own export."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_two_concurrent_polls_scoped_by_chat_name(self, mock_time, mock_sleep):
        """Each poll with different chat_name finds only its own export."""
        mock_time.return_value = 0.0

        alice_file = _make_file_metadata(name="WhatsApp Chat with Alice.zip")
        bob_file = _make_file_metadata(name="WhatsApp Chat with Bob.zip")

        # Client for Alice
        client_alice = _build_client()

        def alice_list(*args, **kwargs):
            m = MagicMock()
            query = kwargs.get("q", "")
            if "Alice" in query:
                m.execute.return_value = {"files": [alice_file]}
            else:
                m.execute.return_value = {"files": [alice_file, bob_file]}
            return m

        client_alice.service.files().list = alice_list

        # Client for Bob
        client_bob = _build_client()

        def bob_list(*args, **kwargs):
            m = MagicMock()
            query = kwargs.get("q", "")
            if "Bob" in query:
                m.execute.return_value = {"files": [bob_file]}
            else:
                m.execute.return_value = {"files": [alice_file, bob_file]}
            return m

        client_bob.service.files().list = bob_list

        result_alice = client_alice.poll_for_new_export(chat_name="Alice", timeout=60)
        result_bob = client_bob.poll_for_new_export(chat_name="Bob", timeout=60)

        assert result_alice is not None
        assert "Alice" in result_alice["name"]

        assert result_bob is not None
        assert "Bob" in result_bob["name"]


# ---------------------------------------------------------------------------
# Tests: DriveManager.wait_for_new_export passthrough
# ---------------------------------------------------------------------------

class TestDriveManagerPassthrough:
    """Verify DriveManager.wait_for_new_export passes new params to client."""

    @patch.object(GoogleDriveClient, "poll_for_new_export")
    def test_passes_all_new_params(self, mock_poll):
        """All new parameters are forwarded to the client method."""
        file_meta = _make_file_metadata()
        mock_poll.return_value = file_meta

        manager = GoogleDriveManager(logger=MagicMock())
        manager.client = MagicMock()
        manager.client.poll_for_new_export = mock_poll

        result = manager.wait_for_new_export(
            initial_interval=3,
            max_interval=10,
            timeout=120,
            created_within_seconds=600,
            chat_name="Alice",
            include_media=True,
        )

        assert result is not None
        mock_poll.assert_called_once_with(
            initial_interval=3,
            max_interval=10,
            timeout=120,
            created_within_seconds=600,
            chat_name="Alice",
            include_media=True,
        )

    @patch.object(GoogleDriveClient, "poll_for_new_export")
    def test_raises_runtime_error_on_timeout(self, mock_poll):
        """When client returns None, raises RuntimeError."""
        mock_poll.return_value = None

        manager = GoogleDriveManager(logger=MagicMock())
        manager.client = MagicMock()
        manager.client.poll_for_new_export = mock_poll

        with pytest.raises(RuntimeError, match="Timeout"):
            manager.wait_for_new_export(timeout=60)

    @patch.object(GoogleDriveClient, "poll_for_new_export")
    def test_legacy_poll_interval_param_accepted(self, mock_poll):
        """Legacy poll_interval param is accepted but ignored."""
        file_meta = _make_file_metadata()
        mock_poll.return_value = file_meta

        manager = GoogleDriveManager(logger=MagicMock())
        manager.client = MagicMock()
        manager.client.poll_for_new_export = mock_poll

        # Should not raise TypeError
        result = manager.wait_for_new_export(poll_interval=8)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: PipelineConfig
# ---------------------------------------------------------------------------

class TestPipelineConfig:
    """Verify PipelineConfig changes."""

    def test_default_initial_interval(self):
        config = PipelineConfig()
        assert config.initial_interval == 2

    def test_default_max_interval(self):
        config = PipelineConfig()
        assert config.max_interval == 8

    def test_default_max_concurrent(self):
        config = PipelineConfig()
        assert config.max_concurrent == 2

    def test_legacy_poll_interval_accepted(self):
        """Legacy poll_interval kwarg is accepted for backward compat."""
        config = PipelineConfig(poll_interval=8)
        assert config.poll_interval == 8
        # But initial_interval is the real setting
        assert config.initial_interval == 2

    def test_custom_values(self):
        config = PipelineConfig(
            initial_interval=1,
            max_interval=16,
            max_concurrent=4,
        )
        assert config.initial_interval == 1
        assert config.max_interval == 16
        assert config.max_concurrent == 4


# ---------------------------------------------------------------------------
# Tests: Edge case — file appears during backoff
# ---------------------------------------------------------------------------

class TestFileAppearsDuringBackoff:
    """File that appears while sleeping is detected at next poll."""

    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.sleep")
    @patch("whatsapp_chat_autoexport.google_drive.drive_client.time.time")
    def test_file_detected_at_next_poll(self, mock_time, mock_sleep):
        """File that appears during a sleep is found on the very next poll."""
        mock_time.return_value = 0.0

        client = _build_client()
        file_meta = _make_file_metadata()

        # Poll 1: empty. Poll 2: empty. Poll 3: file appears.
        seq = _ListResultSequence([[], [], [file_meta]])
        client.service.files().list = seq

        result = client.poll_for_new_export(
            initial_interval=2,
            max_interval=8,
            timeout=300,
        )

        assert result is not None
        # Exactly 2 sleeps (polls 1 and 2), file found on poll 3
        assert mock_sleep.call_count == 2
