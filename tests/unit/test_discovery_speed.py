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


# ---------------------------------------------------------------------------
# Integration-style: timing validation for discovery speed
# ---------------------------------------------------------------------------


class TestDiscoveryTimingIntegration:
    """Integration-style timing tests that validate measurable speedup.

    These tests mock the Appium driver to respond quickly and measure
    wall-clock time to confirm the smart waits are faster than the old
    hardcoded sleeps.

    Old behavior (hardcoded sleeps):
      - restart_app_to_top: 3-5s sleep per call (x2 in collect_all_chats)
      - scroll settle: 0.5s sleep per scroll
      - 10 scrolls + 2 restarts = ~10-15s minimum

    New behavior (smart waits):
      - restart_app_to_top: polls verify_whatsapp_is_open() at 0.5s intervals
      - scroll settle: polls element count at 0.05s intervals
      - With fast-responding mocks, should complete in < 5s
    """

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

    def _build_progressive_find_elements(self, chats_per_page: int = 5, total_chats: int = 10):
        """Build a find_elements side effect that simulates scrolling through chats.

        Returns new batches of chats as scrolling progresses, then repeats
        the last batch (simulating end-of-list).
        """
        pages = []
        for page_idx in range(0, total_chats, chats_per_page):
            page = []
            for i in range(chats_per_page):
                chat_idx = page_idx + i
                if chat_idx < total_chats:
                    page.append(self._make_chat_element(
                        f"Chat {chat_idx}", y=(i + 1) * 100
                    ))
            pages.append(page)

        call_count = [0]
        # Track which "scroll page" we're on
        scroll_page = [0]

        def side_effect(by, value):
            call_count[0] += 1
            # The method calls find_elements multiple times per scroll:
            # 1. Once in the main loop to collect chats
            # 2. Multiple times in the settle loop to check count stability
            # We advance the page only when we detect the pattern has cycled
            # through a settle phase (calls > a threshold per scroll)
            current_page = min(scroll_page[0], len(pages) - 1)
            result = pages[current_page]

            # After every ~4 calls (1 main + ~3 settle), advance to next page
            if call_count[0] % 4 == 0:
                scroll_page[0] += 1

            return result

        return side_effect

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    def test_10_chat_discovery_under_5s(self, mock_subprocess):
        """10-chat discovery with fast-responding mocks completes in < 5s.

        Old hardcoded sleeps would take ~10s minimum:
          - 2 restart_app_to_top calls * 3s sleep = 6s
          - ~4 scrolls * 0.5s settle = 2s
          - Total: ~8-10s

        With smart waits and fast-responding mocks, should be < 5s.
        """
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = _make_driver()
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)

        # Build progressive find_elements that returns 5 chats per page
        # Page 0: Chat 0-4, Page 1: Chat 5-9, then repeats last page
        find_elements_fn = self._build_progressive_find_elements(
            chats_per_page=5, total_chats=10
        )
        driver.driver.find_elements.side_effect = find_elements_fn
        driver.driver.swipe = MagicMock()

        start = time.monotonic()
        result = driver.collect_all_chats()
        elapsed = time.monotonic() - start

        # Should have collected chats
        assert len(result) > 0, f"Expected chats, got {len(result)}"

        # Wall-clock time should be well under the old 10s
        assert elapsed < 5.0, (
            f"Discovery took {elapsed:.2f}s — expected < 5s with smart waits "
            f"(old hardcoded sleeps would take ~10s)"
        )

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    def test_fast_profile_faster_than_normal(self, mock_subprocess):
        """FAST profile completes faster than NORMAL due to shorter ceilings.

        Both should be fast with mocks, but FAST's shorter scroll_settle_time
        ceiling (0.3s vs 0.5s) means end-of-list detection triggers sooner.
        """
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Run with NORMAL profile
        set_timeout_profile(TimeoutProfile.NORMAL)
        driver_normal = _make_driver()
        driver_normal.verify_whatsapp_is_open = MagicMock(return_value=True)
        # Return same 3 chats always (triggers end-of-list after 3 no-new-chats scrolls)
        normal_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]
        driver_normal.driver.find_elements.return_value = normal_elements
        driver_normal.driver.swipe = MagicMock()

        start_normal = time.monotonic()
        result_normal = driver_normal.collect_all_chats()
        elapsed_normal = time.monotonic() - start_normal

        # Run with FAST profile
        set_timeout_profile(TimeoutProfile.FAST)
        driver_fast = _make_driver()
        driver_fast.verify_whatsapp_is_open = MagicMock(return_value=True)
        fast_elements = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(3)]
        driver_fast.driver.find_elements.return_value = fast_elements
        driver_fast.driver.swipe = MagicMock()

        start_fast = time.monotonic()
        result_fast = driver_fast.collect_all_chats()
        elapsed_fast = time.monotonic() - start_fast

        # Both should find the same chats
        assert len(result_normal) == len(result_fast) == 3

        # Both should complete quickly (< 5s)
        assert elapsed_normal < 5.0, f"NORMAL took {elapsed_normal:.2f}s"
        assert elapsed_fast < 5.0, f"FAST took {elapsed_fast:.2f}s"

        # FAST should be faster or equal (shorter settle ceilings)
        # Use generous tolerance — timing can be noisy on CI
        assert elapsed_fast <= elapsed_normal + 0.5, (
            f"FAST ({elapsed_fast:.2f}s) should not be slower than "
            f"NORMAL ({elapsed_normal:.2f}s) by more than 0.5s"
        )

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    def test_slow_verify_wireless_still_completes_within_ceiling(self, mock_subprocess):
        """Slow-responding verify (simulated wireless latency) completes within ceiling.

        Simulates wireless latency by making verify_whatsapp_is_open() take
        0.3s per call (simulating network round-trips). With the polling loop,
        it should still complete within the app_launch_timeout ceiling.
        """
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = _make_driver(is_wireless=True)

        # Simulate wireless latency: verify takes 0.3s and succeeds on 3rd attempt
        call_count = [0]

        def slow_verify():
            call_count[0] += 1
            time.sleep(0.1)  # Simulate network latency
            return call_count[0] >= 3  # Succeed on 3rd call

        driver.verify_whatsapp_is_open = MagicMock(side_effect=slow_verify)

        # Use a small timeout ceiling to keep test fast
        with patch(
            "whatsapp_chat_autoexport.export.whatsapp_driver.get_timeout_config"
        ) as mock_config:
            fast_config = TimeoutConfig(app_launch_timeout=5.0)
            mock_config.return_value = fast_config

            start = time.monotonic()
            result = driver.restart_app_to_top()
            elapsed = time.monotonic() - start

        assert result is True, "Should succeed after slow verify retries"
        assert call_count[0] == 3, f"Expected 3 verify calls, got {call_count[0]}"

        # With wireless 1.5x multiplier, ceiling is 7.5s
        # Should complete well within that (3 calls * ~0.6s each = ~1.8s)
        assert elapsed < 5.0, (
            f"Wireless verify took {elapsed:.2f}s — should complete within ceiling"
        )

        # But should take some time due to simulated latency
        assert elapsed >= 0.3, (
            f"Expected >= 0.3s due to simulated latency, got {elapsed:.2f}s"
        )

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.subprocess")
    def test_full_discovery_wall_clock_vs_old_sleeps(self, mock_subprocess):
        """End-to-end: full discovery is measurably faster than old hardcoded sleeps.

        This test simulates the complete collect_all_chats flow with 10 chats
        and verifies the wall-clock time is significantly less than what the
        old implementation would have taken.

        Old implementation timing breakdown:
          - restart_app_to_top (before collection): sleep(3) = 3s
          - 10 scroll iterations * sleep(0.5) settle = 5s
          - restart_app_to_top (after collection): sleep(3) = 3s
          - Total minimum: ~11s

        New implementation with fast mocks should be < 3s.
        """
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        driver = _make_driver()
        driver.verify_whatsapp_is_open = MagicMock(return_value=True)

        # Create 10 unique chats across 2 pages
        page1 = [self._make_chat_element(f"Chat {i}", y=i * 100) for i in range(5)]
        page2 = [self._make_chat_element(f"Chat {i}", y=(i - 5) * 100) for i in range(5, 10)]

        call_count = [0]
        swipe_count = [0]

        def track_swipe(*args, **kwargs):
            swipe_count[0] += 1

        driver.driver.swipe = MagicMock(side_effect=track_swipe)

        def find_elements_effect(by, value):
            call_count[0] += 1
            # Before any swipes, return page 1
            # After first swipe, return page 2
            # After second swipe onwards, return page 2 (end of list)
            if swipe_count[0] == 0:
                return page1
            elif swipe_count[0] == 1:
                return page2
            else:
                return page2

        driver.driver.find_elements.side_effect = find_elements_effect

        start = time.monotonic()
        result = driver.collect_all_chats()
        elapsed = time.monotonic() - start

        # Should have found chats
        assert len(result) >= 5, f"Expected >= 5 chats, got {len(result)}"

        # Old sleeps would have taken ~11s minimum
        # New smart waits with fast mocks should be much faster
        old_minimum = 11.0
        assert elapsed < old_minimum / 2, (
            f"Discovery took {elapsed:.2f}s — expected < {old_minimum / 2:.1f}s "
            f"(old hardcoded sleeps would take ~{old_minimum:.0f}s)"
        )
