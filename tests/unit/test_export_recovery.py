"""
Tests for session recovery logic in ChatExporter.

Covers:
- SESSION_ERROR_KEYWORDS constant and _is_session_error() detection
- _attempt_session_recovery() success/failure paths
- _check_consecutive_recovery_limit() threshold behavior
- Recovery wiring in export_chats() and export_chats_with_new_workflow()
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from whatsapp_chat_autoexport.export.whatsapp_driver import SESSION_ERROR_KEYWORDS
from whatsapp_chat_autoexport.export.chat_exporter import ChatExporter


# --- Fixtures ---

@pytest.fixture
def mock_driver():
    """Create a mock WhatsAppDriver with common methods stubbed."""
    driver = MagicMock()
    driver.verify_whatsapp_is_open.return_value = True
    driver.is_session_active.return_value = True
    driver.reconnect.return_value = True
    driver.navigate_to_main.return_value = None
    driver.navigate_back_to_main.return_value = None
    driver.click_chat.return_value = True
    driver.device_id = "test-device"
    return driver


@pytest.fixture
def mock_logger():
    """Create a mock Logger."""
    logger = MagicMock()
    logger.debug = False
    return logger


@pytest.fixture
def exporter(mock_driver, mock_logger):
    """Create a ChatExporter with mocked dependencies."""
    return ChatExporter(driver=mock_driver, logger=mock_logger)


# --- SESSION_ERROR_KEYWORDS constant ---

class TestSessionErrorKeywords:
    def test_contains_all_expected_keywords(self):
        expected = [
            "session is either terminated",
            "nosuchdrivererror",
            "invalidsessionid",
            "instrumentation process is not running",
            "cannot be proxied",
            "socket hang up",
        ]
        for kw in expected:
            assert kw in SESSION_ERROR_KEYWORDS

    def test_does_not_contain_overly_broad_terms(self):
        """The old code had standalone 'session' and 'terminated' which false-matched."""
        for kw in SESSION_ERROR_KEYWORDS:
            assert kw != "session"
            assert kw != "terminated"
            assert kw != "not started"


# --- _is_session_error() ---

class TestIsSessionError:
    def test_detects_each_keyword(self, exporter):
        for kw in SESSION_ERROR_KEYWORDS:
            assert exporter._is_session_error(f"Error: {kw} happened") is True

    def test_case_insensitive(self, exporter):
        assert exporter._is_session_error("Session Is Either Terminated") is True

    def test_rejects_community_error(self, exporter):
        assert exporter._is_session_error("community chat not supported") is False

    def test_rejects_generic_error(self, exporter):
        assert exporter._is_session_error("Element not found: menuitem_search") is False

    def test_rejects_partial_keyword_match(self, exporter):
        """'Permission session denied' should NOT match — 'session' alone is not a keyword."""
        assert exporter._is_session_error("Permission session denied") is False


# --- _attempt_session_recovery() ---

class TestAttemptSessionRecovery:
    def test_success_reconnect_and_verify(self, exporter, mock_driver):
        mock_driver.reconnect.return_value = True
        mock_driver.verify_whatsapp_is_open.return_value = True

        result = exporter._attempt_session_recovery("test context")

        assert result is True
        assert exporter._consecutive_recovery_count == 1
        mock_driver.reconnect.assert_called_once()
        mock_driver.verify_whatsapp_is_open.assert_called()

    def test_reconnect_succeeds_verify_fails(self, exporter, mock_driver):
        mock_driver.reconnect.return_value = True
        mock_driver.verify_whatsapp_is_open.return_value = False

        result = exporter._attempt_session_recovery("test context")

        assert result is False
        assert exporter._consecutive_recovery_count == 0

    def test_reconnect_fails(self, exporter, mock_driver):
        mock_driver.reconnect.return_value = False

        result = exporter._attempt_session_recovery("test context")

        assert result is False
        assert exporter._consecutive_recovery_count == 0

    def test_reconnect_raises_exception(self, exporter, mock_driver):
        mock_driver.reconnect.side_effect = Exception("ADB gone")

        result = exporter._attempt_session_recovery("test context")

        assert result is False

    def test_increments_consecutive_count(self, exporter, mock_driver):
        mock_driver.reconnect.return_value = True
        mock_driver.verify_whatsapp_is_open.return_value = True

        exporter._attempt_session_recovery("first")
        exporter._attempt_session_recovery("second")

        assert exporter._consecutive_recovery_count == 2


# --- _check_consecutive_recovery_limit() ---

class TestCheckConsecutiveRecoveryLimit:
    def test_not_reached(self, exporter):
        exporter._consecutive_recovery_count = 0
        assert exporter._check_consecutive_recovery_limit() is False

    def test_at_limit(self, exporter):
        exporter._consecutive_recovery_count = 3
        assert exporter._check_consecutive_recovery_limit() is True

    def test_above_limit(self, exporter):
        exporter._consecutive_recovery_count = 5
        assert exporter._check_consecutive_recovery_limit() is True

    def test_exactly_at_boundary(self, exporter):
        exporter._consecutive_recovery_count = 2
        assert exporter._check_consecutive_recovery_limit() is False
        exporter._consecutive_recovery_count = 3
        assert exporter._check_consecutive_recovery_limit() is True


# --- Recovery in export_chats() ---

class TestExportChatsRecovery:
    def test_pre_verify_fails_recovery_succeeds_continues(self, exporter, mock_driver):
        """When verify fails but recovery succeeds, batch continues to next chat."""
        # First call: verify fails. Recovery succeeds. Second call: verify passes.
        mock_driver.verify_whatsapp_is_open.side_effect = [False, True, True]
        mock_driver.reconnect.return_value = True

        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B"], include_media=True
        )

        # Chat A should be marked failed (skipped due to recovery), Chat B should succeed
        assert results["Chat A"] is False
        assert results["Chat B"] is True

    def test_pre_verify_fails_recovery_fails_breaks(self, exporter, mock_driver):
        """When verify fails and recovery also fails, batch stops."""
        mock_driver.verify_whatsapp_is_open.side_effect = [False, False]
        mock_driver.reconnect.return_value = False

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B", "Chat C"], include_media=True
        )

        # Only Chat A should be in results (batch broke)
        assert results["Chat A"] is False
        assert "Chat B" not in results

    def test_session_error_exception_recovery_succeeds(self, exporter, mock_driver):
        """Session error in exception handler triggers recovery and continues."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.reconnect.return_value = True

        call_count = [0]
        def export_side_effect(name, include_media=True):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("instrumentation process is not running")
            return True

        exporter.export_chat_to_google_drive = MagicMock(side_effect=export_side_effect)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B"], include_media=True
        )

        assert results["Chat A"] is False
        assert results["Chat B"] is True

    def test_community_exception_no_recovery(self, exporter, mock_driver):
        """Community chat errors should NOT trigger session recovery."""
        mock_driver.verify_whatsapp_is_open.return_value = True

        exporter.export_chat_to_google_drive = MagicMock(
            side_effect=Exception("community chat not supported")
        )

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A"], include_media=True
        )

        # Should not attempt reconnect for community error
        mock_driver.reconnect.assert_not_called()

    def test_post_export_health_check_session_inactive_recovery_succeeds(self, exporter, mock_driver):
        """Post-export health check detects dead session, recovery succeeds."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.is_session_active.side_effect = [False, True]  # First inactive, then active
        mock_driver.reconnect.return_value = True

        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B"], include_media=True
        )

        assert results["Chat A"] is True
        assert results["Chat B"] is True

    def test_post_export_health_check_recovery_fails_breaks(self, exporter, mock_driver):
        """Post-export health check detects dead session, recovery fails, batch stops."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.is_session_active.return_value = False
        mock_driver.reconnect.return_value = False

        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B"], include_media=True
        )

        # Chat A exported but batch stopped after health check failed
        assert results["Chat A"] is True
        assert "Chat B" not in results

    def test_successful_export_resets_consecutive_counter(self, exporter, mock_driver):
        """A fully successful export resets the consecutive recovery counter."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.is_session_active.return_value = True

        exporter._consecutive_recovery_count = 2
        exporter.export_chat_to_google_drive = MagicMock(return_value=True)

        exporter.export_chats(["Chat A"], include_media=True)

        assert exporter._consecutive_recovery_count == 0

    def test_consecutive_recovery_limit_breaks_batch(self, exporter, mock_driver):
        """Reaching MAX_CONSECUTIVE_RECOVERIES stops the batch."""
        exporter._consecutive_recovery_count = 0
        mock_driver.reconnect.return_value = True

        # All verifications fail, each recovery increments counter
        mock_driver.verify_whatsapp_is_open.return_value = False

        results, timings, total_time, skipped = exporter.export_chats(
            ["Chat A", "Chat B", "Chat C", "Chat D", "Chat E"],
            include_media=True,
        )

        # Should have stopped after MAX_CONSECUTIVE_RECOVERIES (3) + 1 for the limit check
        assert exporter._consecutive_recovery_count <= ChatExporter.MAX_CONSECUTIVE_RECOVERIES


# --- Recovery in export_chats_with_new_workflow() ---

class TestExportChatsNewWorkflowRecovery:
    @pytest.fixture(autouse=True)
    def _patch_state_manager(self, exporter):
        """Patch state manager for new workflow tests."""
        mock_sm = MagicMock()
        mock_sm.has_session = True
        exporter._state_manager = mock_sm

    def test_pre_verify_fails_recovery_succeeds_continues(self, exporter, mock_driver):
        """When verify fails but recovery succeeds, batch continues."""
        mock_driver.verify_whatsapp_is_open.side_effect = [False, True, True]
        mock_driver.reconnect.return_value = True

        exporter.export_with_new_workflow = MagicMock(return_value=(True, "ok"))

        results, timings, total_time, skipped = exporter.export_chats_with_new_workflow(
            ["Chat A", "Chat B"], include_media=True
        )

        assert results["Chat A"] is False
        assert results["Chat B"] is True

    def test_pre_verify_fails_recovery_fails_breaks(self, exporter, mock_driver):
        """When verify fails and recovery fails, batch stops with state manager update."""
        mock_driver.verify_whatsapp_is_open.side_effect = [False, False]
        mock_driver.reconnect.return_value = False

        results, timings, total_time, skipped = exporter.export_chats_with_new_workflow(
            ["Chat A", "Chat B"], include_media=True
        )

        assert results["Chat A"] is False
        assert "Chat B" not in results
        # State manager should have been notified
        exporter._state_manager.fail_chat.assert_called()

    def test_session_error_exception_with_state_manager(self, exporter, mock_driver):
        """Session error updates state manager and attempts recovery."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.reconnect.return_value = True

        call_count = [0]
        def workflow_side_effect(chat_name, chat_index, include_media, use_state_tracking):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("instrumentation process is not running")
            return True, "ok"

        exporter.export_with_new_workflow = MagicMock(side_effect=workflow_side_effect)

        results, timings, total_time, skipped = exporter.export_chats_with_new_workflow(
            ["Chat A", "Chat B"], include_media=True
        )

        # State manager should record the crash
        exporter._state_manager.fail_chat.assert_called()
        assert results["Chat B"] is True

    def test_post_export_health_check(self, exporter, mock_driver):
        """Post-export health check works in new workflow too."""
        mock_driver.verify_whatsapp_is_open.return_value = True
        mock_driver.is_session_active.side_effect = [False, True]
        mock_driver.reconnect.return_value = True

        exporter.export_with_new_workflow = MagicMock(return_value=(True, "ok"))

        results, timings, total_time, skipped = exporter.export_chats_with_new_workflow(
            ["Chat A", "Chat B"], include_media=True
        )

        assert results["Chat A"] is True
        assert results["Chat B"] is True
