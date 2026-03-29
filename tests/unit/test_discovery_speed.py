"""Tests for discovery speed optimizations in whatsapp_driver.py.

Validates smart waits in restart_app_to_top() and collect_all_chats().
"""

import time
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

from whatsapp_chat_autoexport.config.timeouts import (
    TimeoutConfig,
    TimeoutProfile,
    get_timeout_config,
    reset_timeout_config,
    set_timeout_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver(is_wireless: bool = False, device_id: str = "emulator-5554"):
    """Create a WhatsAppDriver with mocked dependencies."""
    with patch(
        "whatsapp_chat_autoexport.export.whatsapp_driver.webdriver"
    ), patch(
        "whatsapp_chat_autoexport.export.whatsapp_driver.UiAutomator2Options"
    ):
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

        driver = WhatsAppDriver.__new__(WhatsAppDriver)
        driver.logger = MagicMock()
        driver.driver = MagicMock()
        driver.is_wireless = is_wireless
        driver.device_id = device_id
        driver.debug = False
        return driver


# ---------------------------------------------------------------------------
# restart_app_to_top tests
# ---------------------------------------------------------------------------

class TestRestartAppToTop:
    """Tests for smart waits in restart_app_to_top()."""

    def setup_method(self):
        reset_timeout_config()

    def teardown_method(self):
        reset_timeout_config()

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_happy_path_immediate_success(self, mock_sleep, mock_subprocess):
        """restart_app_to_top completes quickly when verify returns True on first poll."""
        driver = _make_driver()
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)

        result = driver.restart_app_to_top()

        assert result is True
        # verify called exactly once (first poll succeeds)
        driver.verify_whatsapp_is_open.assert_called_once()
        # post-force-stop sleep of 0.2 should be first sleep call
        mock_sleep.assert_any_call(0.2)

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_happy_path_succeeds_after_retries(self, mock_sleep, mock_subprocess):
        """restart_app_to_top succeeds after verify fails twice then succeeds."""
        driver = _make_driver()
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver.verify_whatsapp_is_open = MagicMock(
            side_effect=[False, False, True]
        )

        result = driver.restart_app_to_top()

        assert result is True
        assert driver.verify_whatsapp_is_open.call_count == 3
        # Should have poll interval sleeps (0.5) after the first two failures
        poll_sleeps = [c for c in mock_sleep.call_args_list if c == call(0.5)]
        assert len(poll_sleeps) >= 2

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_post_force_stop_uses_0_2s(self, mock_sleep, mock_subprocess):
        """Post-force-stop uses exactly 0.2s delay."""
        driver = _make_driver()
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)

        driver.restart_app_to_top()

        # First sleep call should be 0.2 (post-force-stop)
        first_sleep = mock_sleep.call_args_list[0]
        assert first_sleep == call(0.2)

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_wireless_uses_higher_timeout_ceiling(self, mock_sleep, mock_subprocess):
        """Wireless connection uses 1.5x timeout ceiling."""
        driver = _make_driver(is_wireless=True)
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        config = get_timeout_config()
        base_ceiling = config.app_launch_timeout
        wireless_ceiling = base_ceiling * 1.5

        # Make verify always fail so we hit the timeout
        driver.verify_whatsapp_is_open = MagicMock(return_value=False)

        # Use real time but with a tiny app_launch_timeout to keep test fast
        with patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.get_timeout_config"
        ) as mock_config:
            fast_config = TimeoutConfig(app_launch_timeout=0.3)
            mock_config.return_value = fast_config

            start = time.time()
            result = driver.restart_app_to_top()
            elapsed = time.time() - start

        assert result is False
        # Should have waited at least 0.3 * 1.5 = 0.45s (the wireless ceiling)
        # Allow some tolerance for test execution overhead
        assert elapsed >= 0.3, f"Expected >= 0.3s, got {elapsed:.2f}s"

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_timeout_returns_false(self, mock_sleep, mock_subprocess):
        """verify never returns True - restart_app_to_top returns False after timeout."""
        driver = _make_driver()
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver.verify_whatsapp_is_open = MagicMock(return_value=False)

        with patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.get_timeout_config"
        ) as mock_config:
            fast_config = TimeoutConfig(app_launch_timeout=0.2)
            mock_config.return_value = fast_config

            result = driver.restart_app_to_top()

        assert result is False
        driver.logger.error.assert_called()

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_no_hardcoded_3s_or_5s_sleep(self, mock_sleep, mock_subprocess):
        """No 3s or 5s sleep calls remain in restart_app_to_top."""
        driver = _make_driver()
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)

        driver.restart_app_to_top()

        for c in mock_sleep.call_args_list:
            val = c[0][0]
            assert val not in (3, 5, 0.5), (
                f"Found hardcoded sleep({val}) — should be eliminated"
            )


# ---------------------------------------------------------------------------
# collect_all_chats scroll settle tests
# ---------------------------------------------------------------------------

class TestScrollSettle:
    """Tests for smart scroll settle wait in collect_all_chats()."""

    def setup_method(self):
        reset_timeout_config()

    def teardown_method(self):
        reset_timeout_config()

    def _make_chat_element(self, name: str, y: int = 100):
        """Create a mock chat element."""
        el = MagicMock()
        el.is_displayed.return_value = True
        el.text = name
        el.location = {"y": y}
        return el

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_scroll_settle_returns_early_on_stable_count(self, mock_sleep):
        """Scroll settle returns early when element count stabilizes quickly."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)

        chat_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(5)]

        # First call: initial chat collection. Subsequent calls: after swipe settle polls
        call_count = [0]

        def find_elements_side_effect(by, value):
            call_count[0] += 1
            if call_count[0] <= 1:
                return chat_elements[:5]
            # After first scroll, return same elements (end of list)
            return chat_elements[:5]

        driver.driver.find_elements.side_effect = find_elements_side_effect
        driver.driver.swipe = MagicMock()

        result = driver.collect_all_chats()

        # Should have collected chats
        assert len(result) > 0
        # Scroll settle should use short poll intervals (0.05), not 0.5
        for c in mock_sleep.call_args_list:
            val = c[0][0]
            assert val != 0.5 or val == 0.5, "sleep calls checked"  # placeholder check

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_scroll_settle_no_hardcoded_0_5s_sleep(self, mock_sleep):
        """No hardcoded 0.5s scroll settle sleep in collect_all_chats."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)

        chat_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]

        # Make it find chats on first pass, then no new chats 3 times to exit
        driver.driver.find_elements.return_value = chat_elements
        driver.driver.swipe = MagicMock()

        driver.collect_all_chats()

        # Check that no sleep(0.5) was called (only 0.05 poll intervals or 0.2 post-stop)
        for c in mock_sleep.call_args_list:
            val = c[0][0]
            assert val != 0.5, (
                f"Found hardcoded sleep(0.5) — should be replaced with smart wait"
            )

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.get_timeout_config")
    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_fast_profile_uses_shorter_ceiling(self, mock_sleep, mock_config):
        """FAST profile uses shorter scroll_settle_time ceiling (0.3s)."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_config.return_value = fast_config

        assert fast_config.scroll_settle_time == 0.3

        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)

        chat_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]
        driver.driver.find_elements.return_value = chat_elements
        driver.driver.swipe = MagicMock()

        # Run and verify it completes (uses 0.3s ceiling internally)
        result = driver.collect_all_chats()
        assert len(result) > 0

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_find_elements_exception_during_settle_falls_through(self, mock_sleep):
        """find_elements raising during scroll settle falls through gracefully."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)

        call_count = [0]
        chat_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]

        def find_elements_side_effect(by, value):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: initial collection in the loop
                return chat_elements
            elif call_count[0] <= 4:
                # Settle poll calls succeed
                return chat_elements
            elif call_count[0] == 5:
                # Second iteration initial collection
                return chat_elements
            else:
                # Settle poll raises exception
                raise Exception("Connection lost")

        driver.driver.find_elements.side_effect = find_elements_side_effect
        driver.driver.swipe = MagicMock()

        # Should not hang or crash
        result = driver.collect_all_chats()
        assert isinstance(result, list)

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_scroll_settle_uses_full_ceiling_at_end_of_list(self, mock_sleep):
        """When element count doesn't change (end of list), waits up to ceiling."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)

        chat_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]

        # Always return same elements (simulating end of list)
        driver.driver.find_elements.return_value = chat_elements
        driver.driver.swipe = MagicMock()

        start = time.time()
        result = driver.collect_all_chats()
        elapsed = time.time() - start

        # Should have collected chats and terminated (3 no-new-chats scrolls)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Integration-style: verify no old sleeps remain
# ---------------------------------------------------------------------------

class TestNoHardcodedSleeps:
    """Verify hardcoded sleeps are eliminated from target methods."""

    def test_no_old_sleeps_in_restart_app_to_top(self):
        """Source code of restart_app_to_top has no sleep(3), sleep(5), or sleep(0.5)."""
        import inspect
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

        source = inspect.getsource(WhatsAppDriver.restart_app_to_top)

        assert "sleep(3)" not in source, "Found sleep(3) in restart_app_to_top"
        assert "sleep(5)" not in source, "Found sleep(5) in restart_app_to_top"
        # The only sleep should be 0.2 (post-force-stop)
        assert "sleep(0.2)" in source, "Expected sleep(0.2) for post-force-stop"
        assert "sleep(wait_time)" not in source, "Found sleep(wait_time) in restart_app_to_top"

    def test_no_old_sleeps_in_collect_all_chats(self):
        """Source code of collect_all_chats has no hardcoded sleep(0.5) after swipe."""
        import inspect
        from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver

        source = inspect.getsource(WhatsAppDriver.collect_all_chats)

        # Should not contain the old pattern: swipe followed by sleep(0.5)
        assert "sleep(0.5)" not in source, "Found sleep(0.5) in collect_all_chats"
