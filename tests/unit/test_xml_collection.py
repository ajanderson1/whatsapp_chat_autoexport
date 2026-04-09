"""Tests for XML-based chat collection in collect_all_chats().

Validates the XML page_source parsing approach including metadata extraction,
callback firing, termination detection, error handling, and proportional
scroll coordinates.
"""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from whatsapp_chat_autoexport.export.models import ChatMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_driver():
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
        driver.is_wireless = False
        driver.device_id = "emulator-5554"
        driver.debug = False
        return driver


def _build_xml(*chat_rows: str) -> str:
    """Build a minimal WhatsApp-like XML page source with given chat row fragments."""
    rows = "\n".join(chat_rows)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <android.widget.FrameLayout>
    <androidx.recyclerview.widget.RecyclerView resource-id="android:id/list">
      {rows}
    </androidx.recyclerview.widget.RecyclerView>
  </android.widget.FrameLayout>
</hierarchy>"""


def _chat_row(
    name: str,
    timestamp: str = "12:00",
    message_preview: str = "Hello",
    is_muted: bool = False,
    is_group: bool = False,
    group_sender: str = "",
    has_type_indicator: bool = False,
    photo_desc: str = "",
) -> str:
    """Build XML for a single chat row with optional metadata elements."""
    mute = '<android.widget.ImageView resource-id="com.whatsapp:id/mute_indicator" />' if is_muted else ""
    group_photo = '<android.widget.ImageView resource-id="com.whatsapp:id/parent_group_profile_photo" />' if is_group else ""
    sender = f'<android.widget.TextView resource-id="com.whatsapp:id/msg_from_tv" text="{group_sender}" />' if group_sender else ""
    type_ind = '<android.widget.ImageView resource-id="com.whatsapp:id/message_type_indicator" />' if has_type_indicator else ""
    contact_photo_desc = f' content-desc="{photo_desc}"' if photo_desc else ""

    return f"""
      <android.widget.LinearLayout resource-id="com.whatsapp:id/contact_row_container">
        <android.widget.ImageView resource-id="com.whatsapp:id/contact_photo"{contact_photo_desc} />
        <android.widget.LinearLayout resource-id="com.whatsapp:id/row_content">
          <android.widget.Button resource-id="com.whatsapp:id/conversations_row_header">
            <android.widget.FrameLayout>
              <android.widget.TextView resource-id="com.whatsapp:id/conversations_row_contact_name" text="{name}" />
            </android.widget.FrameLayout>
            <android.widget.TextView resource-id="com.whatsapp:id/conversations_row_date" text="{timestamp}" content-desc="{timestamp}" />
          </android.widget.Button>
          <android.widget.LinearLayout resource-id="com.whatsapp:id/bottom_row">
            {sender}
            <android.widget.TextView resource-id="com.whatsapp:id/single_msg_tv" text="{message_preview}" />
            {mute}
            {type_ind}
          </android.widget.LinearLayout>
          {group_photo}
        </android.widget.LinearLayout>
      </android.widget.LinearLayout>"""


def _setup_driver_for_collection(driver, xml_pages):
    """Configure a mocked driver for collect_all_chats with given XML pages.

    xml_pages: list of XML strings to return from successive page_source calls.
    The last page is repeated to allow settle-loop and end-of-list detection.
    """
    driver.restart_app_to_top = MagicMock(return_value=True)

    # page_source returns successive XML pages, then repeats last
    page_iter = iter(xml_pages)
    last_page = xml_pages[-1] if xml_pages else ""

    def page_source_getter():
        try:
            return next(page_iter)
        except StopIteration:
            return last_page

    type(driver.driver).page_source = property(lambda self: page_source_getter())

    # get_window_size for proportional scrolling
    driver.driver.get_window_size.return_value = {"width": 1080, "height": 2400}

    # find_elements for settle loop — return a fixed list of mock elements
    mock_elem = MagicMock()
    mock_elem.is_displayed.return_value = True
    mock_elem.text = "Chat"
    driver.driver.find_elements.return_value = [mock_elem]

    driver.driver.swipe = MagicMock()


# ===========================================================================
# Happy path tests
# ===========================================================================


class TestXmlCollectionHappyPath:
    """Happy path tests for XML-based collect_all_chats."""

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_three_chats_returns_metadata(self, _mock_sleep):
        """Mock page_source with 3 chat rows returns List[ChatMetadata] with correct names/metadata."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice", "09:00", "Hi there", photo_desc="Alice picture"),
            _chat_row("Bob", "10:30", "See you", is_muted=True),
            _chat_row("Charlie", "11:15", "Photo", is_group=True, group_sender="Dave"),
        )
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats()

        assert len(result) >= 3
        names = [m.name for m in result]
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" in names

        # Check metadata
        alice = next(m for m in result if m.name == "Alice")
        assert alice.timestamp == "09:00"
        assert alice.message_preview == "Hi there"
        assert alice.photo_description == "Alice picture"
        assert alice.is_muted is False

        bob = next(m for m in result if m.name == "Bob")
        assert bob.is_muted is True

        charlie = next(m for m in result if m.name == "Charlie")
        assert charlie.is_group is True
        assert charlie.group_sender == "Dave"

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_on_chat_found_fires_for_each_new_chat(self, _mock_sleep):
        """on_chat_found callback fires once per unique chat name."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice"),
            _chat_row("Bob"),
            _chat_row("Charlie"),
        )
        _setup_driver_for_collection(driver, [xml])

        found = []
        driver.collect_all_chats(on_chat_found=lambda m: found.append(m))

        found_names = [m.name for m in found]
        assert "Alice" in found_names
        assert "Bob" in found_names
        assert "Charlie" in found_names

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_limit_truncates_results(self, _mock_sleep):
        """limit=2 with 5 chats returns 2 items."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice"),
            _chat_row("Bob"),
            _chat_row("Charlie"),
            _chat_row("Dave"),
            _chat_row("Eve"),
        )
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats(limit=2)

        assert len(result) == 2

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_sort_alphabetical(self, _mock_sleep):
        """sort_alphabetical=True returns results sorted by name."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Charlie"),
            _chat_row("Alice"),
            _chat_row("Bob"),
        )
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats(sort_alphabetical=True)

        sorted_names = [m.name for m in result]
        # The first three should be alphabetically sorted
        alice_idx = next(i for i, m in enumerate(result) if m.name == "Alice")
        bob_idx = next(i for i, m in enumerate(result) if m.name == "Bob")
        charlie_idx = next(i for i, m in enumerate(result) if m.name == "Charlie")
        assert alice_idx < bob_idx < charlie_idx

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_returns_chat_metadata_instances(self, _mock_sleep):
        """Results are ChatMetadata instances."""
        driver = _make_driver()
        xml = _build_xml(_chat_row("Alice"))
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats()

        assert all(isinstance(m, ChatMetadata) for m in result)


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestXmlCollectionEdgeCases:
    """Edge case tests for XML-based collect_all_chats."""

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_empty_page_source_continues(self, _mock_sleep):
        """Empty page_source string triggers continue without crash."""
        driver = _make_driver()
        # First call: empty, second call: valid, then empty again for termination
        valid_xml = _build_xml(_chat_row("Alice"))
        empty_xml = ""
        _setup_driver_for_collection(driver, [empty_xml, valid_xml, empty_xml])

        result = driver.collect_all_chats()

        # Should still find Alice from the valid page
        names = [m.name for m in result]
        assert "Alice" in names

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_xml_parse_error_continues(self, _mock_sleep):
        """Invalid XML triggers ParseError, loop continues."""
        driver = _make_driver()
        valid_xml = _build_xml(_chat_row("Alice"))
        bad_xml = "<not valid xml <<<"
        _setup_driver_for_collection(driver, [bad_xml, valid_xml])

        result = driver.collect_all_chats()

        names = [m.name for m in result]
        assert "Alice" in names

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_xml_with_no_chat_rows(self, _mock_sleep):
        """XML with no chat rows triggers no-new-chats detection."""
        driver = _make_driver()
        empty_list_xml = _build_xml()  # No chat rows
        _setup_driver_for_collection(driver, [empty_list_xml])

        result = driver.collect_all_chats()

        assert result == []

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_missing_metadata_elements(self, _mock_sleep):
        """Chat row with only name element has None for optional fields."""
        driver = _make_driver()
        # Minimal row: just the name, no sibling metadata
        minimal_row = """
          <android.widget.LinearLayout resource-id="com.whatsapp:id/contact_row_container">
            <android.widget.LinearLayout resource-id="com.whatsapp:id/row_content">
              <android.widget.Button resource-id="com.whatsapp:id/conversations_row_header">
                <android.widget.FrameLayout>
                  <android.widget.TextView resource-id="com.whatsapp:id/conversations_row_contact_name" text="Minimal" />
                </android.widget.FrameLayout>
              </android.widget.Button>
            </android.widget.LinearLayout>
          </android.widget.LinearLayout>"""
        xml = _build_xml(minimal_row)
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats()

        minimal = next(m for m in result if m.name == "Minimal")
        assert minimal.timestamp is None
        assert minimal.message_preview is None
        assert minimal.is_muted is False
        assert minimal.is_group is False
        assert minimal.group_sender is None
        assert minimal.has_type_indicator is False
        assert minimal.photo_description is None

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_duplicate_names_deduped_in_results(self, _mock_sleep):
        """Duplicate chat names are deduped — only the first sighting is kept."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice", "09:00", "First"),
            _chat_row("Alice", "10:00", "Second"),
        )
        _setup_driver_for_collection(driver, [xml])

        result = driver.collect_all_chats()

        alice_entries = [m for m in result if m.name == "Alice"]
        assert len(alice_entries) == 1

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_callback_fires_only_for_first_occurrence(self, _mock_sleep):
        """on_chat_found fires once per unique name, even with duplicates on screen."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice"),
            _chat_row("Alice"),
        )
        _setup_driver_for_collection(driver, [xml])

        found = []
        driver.collect_all_chats(on_chat_found=lambda m: found.append(m.name))

        assert found.count("Alice") == 1


# ===========================================================================
# Error path tests
# ===========================================================================


class TestXmlCollectionErrors:
    """Error path tests for XML-based collect_all_chats."""

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_callback_exception_caught(self, _mock_sleep):
        """Callback that raises an exception does not crash collection."""
        driver = _make_driver()
        xml = _build_xml(
            _chat_row("Alice"),
            _chat_row("Bob"),
        )
        _setup_driver_for_collection(driver, [xml])

        def exploding_callback(m):
            raise RuntimeError("Boom!")

        result = driver.collect_all_chats(on_chat_found=exploding_callback)

        # Should still return results despite callback error
        names = [m.name for m in result]
        assert "Alice" in names
        assert "Bob" in names

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_page_source_exception_skips_iteration(self, _mock_sleep):
        """Exception from page_source property is caught, iteration skipped."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=True)
        driver.driver.get_window_size.return_value = {"width": 1080, "height": 2400}
        driver.driver.swipe = MagicMock()
        mock_elem = MagicMock()
        mock_elem.is_displayed.return_value = True
        mock_elem.text = "Chat"
        driver.driver.find_elements.return_value = [mock_elem]

        # page_source raises on first call, returns valid XML on second
        call_count = [0]
        valid_xml = _build_xml(_chat_row("Alice"))

        def page_source_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Connection lost")
            return valid_xml

        type(driver.driver).page_source = property(lambda self: page_source_side_effect())

        result = driver.collect_all_chats()

        names = [m.name for m in result]
        assert "Alice" in names


# ===========================================================================
# Integration: Proportional scroll coordinates
# ===========================================================================


class TestProportionalScrollCoords:
    """Verify scroll coordinates are computed from get_window_size()."""

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_scroll_uses_proportional_coords(self, _mock_sleep):
        """Swipe coords are 50% width, 75%->25% height from get_window_size."""
        driver = _make_driver()
        xml = _build_xml(_chat_row("Alice"))
        _setup_driver_for_collection(driver, [xml])

        # Use specific window size
        driver.driver.get_window_size.return_value = {"width": 1080, "height": 2400}

        driver.collect_all_chats()

        # Verify swipe was called with proportional coords
        # center_x = 1080 // 2 = 540
        # start_y = int(2400 * 0.75) = 1800
        # end_y = int(2400 * 0.25) = 600
        swipe_calls = driver.driver.swipe.call_args_list
        assert len(swipe_calls) > 0

        first_swipe = swipe_calls[0]
        args = first_swipe[0]  # positional args
        assert args[0] == 540, f"Expected center_x=540, got {args[0]}"
        assert args[1] == 1800, f"Expected start_y=1800, got {args[1]}"
        assert args[2] == 540, f"Expected end_x=540, got {args[2]}"
        assert args[3] == 600, f"Expected end_y=600, got {args[3]}"

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_different_window_size(self, _mock_sleep):
        """Proportional coords adapt to different screen sizes."""
        driver = _make_driver()
        xml = _build_xml(_chat_row("Alice"))
        _setup_driver_for_collection(driver, [xml])

        # Smaller screen
        driver.driver.get_window_size.return_value = {"width": 720, "height": 1600}

        driver.collect_all_chats()

        swipe_calls = driver.driver.swipe.call_args_list
        assert len(swipe_calls) > 0

        first_swipe = swipe_calls[0]
        args = first_swipe[0]
        assert args[0] == 360   # 720 // 2
        assert args[1] == 1200  # int(1600 * 0.75)
        assert args[2] == 360   # 720 // 2
        assert args[3] == 400   # int(1600 * 0.25)


# ===========================================================================
# Restart calls preserved
# ===========================================================================


class TestRestartCalls:
    """Verify restart_app_to_top is called at start and end."""

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_restart_called_per_pass_and_at_end(self, _mock_sleep):
        """restart_app_to_top called at the start of each pass + once at end."""
        driver = _make_driver()
        xml = _build_xml(_chat_row("Alice"))
        _setup_driver_for_collection(driver, [xml])

        # Default passes=2: pass 1 restart + pass 2 restart (early-out after
        # finding 0 new) + final restart = 3 calls.  But pass 2 sees all chats
        # already in seen_names, adds 0, and triggers early-out — so pass 2
        # still calls restart_app_to_top before scrolling.
        driver.collect_all_chats()

        # 2 pass starts + 1 final restart = 3
        assert driver.restart_app_to_top.call_count == 3

    @patch("whatsapp_chat_autoexport.export.whatsapp_driver.sleep")
    def test_restart_failure_at_start_returns_empty(self, _mock_sleep):
        """If restart fails at start of pass 1, returns empty list."""
        driver = _make_driver()
        driver.restart_app_to_top = MagicMock(return_value=False)

        result = driver.collect_all_chats()

        assert result == []
        # Pass 1 restart fails (1 call) → break → final restart (1 call) = 2
        assert driver.restart_app_to_top.call_count == 2
