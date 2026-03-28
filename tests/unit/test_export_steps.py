"""
Tests for export step classes.
"""

import time
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

from whatsapp_chat_autoexport.whatsapp.export.steps import (
    BaseExportStep,
    StepContext,
    StepResult,
    StepStatus,
    OpenMenuStep,
    ClickMoreStep,
    ClickExportStep,
    SelectMediaStep,
    SelectDriveStep,
    ClickUploadStep,
)
from whatsapp_chat_autoexport.whatsapp.export import ExportWorkflow, WorkflowStatus
from whatsapp_chat_autoexport.automation import ElementFinder, ElementCache, FindResult
from whatsapp_chat_autoexport.config.selectors import (
    SelectorDefinition,
    SelectorStrategy,
    ElementSelectors,
)
from whatsapp_chat_autoexport.config.timeouts import (
    TimeoutConfig,
    TimeoutProfile,
    get_timeout_config,
    reset_timeout_config,
)
from whatsapp_chat_autoexport.core.result import Ok, Err


class MockElementFinder:
    """Mock element finder for testing."""

    def __init__(self, return_element=None, should_fail=False):
        self.return_element = return_element or Mock()
        self.should_fail = should_fail
        self.find_calls = []

    def find(self, selectors, timeout=5.0, wait_visible=True, context=None):
        self.find_calls.append((selectors, context))
        if self.should_fail:
            from whatsapp_chat_autoexport.core.errors import ElementNotFoundError

            return Err(
                ElementNotFoundError(
                    message="Element not found",
                    element_name=selectors.name,
                )
            )
        return Ok(
            FindResult(
                element=self.return_element,
                strategy=SelectorDefinition(
                    strategy=SelectorStrategy.ID,
                    value="test",
                ),
                attempts=1,
                duration_seconds=0.1,
            )
        )

    def is_present(self, selectors, timeout=1.0):
        return not self.should_fail


def create_test_context(
    element_finder=None,
    chat_name="Test Chat",
    include_media=True,
    timeout_config=None,
):
    """Create a StepContext for testing."""
    mock_driver = Mock()
    mock_driver.current_package = "com.whatsapp"
    mock_driver.find_elements.return_value = []
    mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

    kwargs = dict(
        driver=mock_driver,
        element_finder=element_finder or MockElementFinder(),
        chat_name=chat_name,
        include_media=include_media,
    )
    if timeout_config is not None:
        kwargs["timeout_config"] = timeout_config

    return StepContext(**kwargs)


class TestStepResult:
    """Tests for StepResult."""

    def test_success_result(self):
        """Test creating a success result."""
        result = StepResult.success("Step completed", key="value")
        assert result.status == StepStatus.COMPLETED
        assert result.message == "Step completed"
        assert result.data["key"] == "value"

    def test_failed_result(self):
        """Test creating a failed result."""
        from whatsapp_chat_autoexport.core.errors import ExportWorkflowError

        error = ExportWorkflowError(
            message="Something went wrong",
            step_name="test",
        )
        result = StepResult.failed(error, "Step failed")
        assert result.status == StepStatus.FAILED
        assert result.error is error

    def test_skipped_result(self):
        """Test creating a skipped result."""
        result = StepResult.skipped("Not applicable")
        assert result.status == StepStatus.SKIPPED
        assert result.message == "Not applicable"


class TestStepContext:
    """Tests for StepContext."""

    def test_basic_creation(self):
        """Test basic context creation."""
        context = create_test_context()
        assert context.chat_name == "Test Chat"
        assert context.include_media is True
        assert context.total_steps == 6

    def test_step_data_sharing(self):
        """Test that step data can be shared between steps."""
        context = create_test_context()
        context.step_data["menu_open"] = True
        assert context.step_data["menu_open"] is True

    def test_default_timeout_config_has_normal_profile_values(self):
        """Test that StepContext created with default TimeoutConfig has NORMAL profile values."""
        reset_timeout_config()
        context = create_test_context()
        normal = TimeoutConfig()
        assert context.timeout_config.animation_complete_wait == normal.animation_complete_wait
        assert context.timeout_config.screen_transition_wait == normal.screen_transition_wait
        assert context.timeout_config.step_delay == normal.step_delay

    def test_explicit_fast_profile_has_reduced_values(self):
        """Test that StepContext created with explicit FAST profile has reduced values."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        context = create_test_context(timeout_config=fast_config)
        normal = TimeoutConfig()
        assert context.timeout_config.animation_complete_wait < normal.animation_complete_wait
        assert context.timeout_config.screen_transition_wait < normal.screen_transition_wait
        assert context.timeout_config.step_delay < normal.step_delay

    def test_without_explicit_timeout_config_falls_back_to_global(self):
        """Test that StepContext without explicit timeout_config falls back to global default."""
        reset_timeout_config()
        context = create_test_context()
        global_config = get_timeout_config()
        assert context.timeout_config is global_config

    def test_steps_can_access_timeout_config_fields(self):
        """Test that steps can access timeout_config fields through context."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        context = create_test_context(timeout_config=fast_config)
        assert context.timeout_config.animation_complete_wait == 0.3
        assert context.timeout_config.screen_transition_wait == 0.5
        assert context.timeout_config.step_delay == 0.3
        assert context.timeout_config.element_find_timeout == 3.0


class TestOpenMenuStep:
    """Tests for OpenMenuStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = OpenMenuStep()
        assert step.name == "open_menu"
        assert step.step_index == 1
        assert step.max_retries == 2

    def test_execute_success(self):
        """Test successful menu open."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)

        step = OpenMenuStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("menu_open") is True
        mock_element.click.assert_called_once()

    def test_execute_failure(self):
        """Test failed menu open."""
        finder = MockElementFinder(should_fail=True)
        context = create_test_context(element_finder=finder)

        step = OpenMenuStep()
        result = step.execute(context)

        assert result.status == StepStatus.FAILED

    def test_can_retry(self):
        """Test that step supports retry."""
        step = OpenMenuStep()
        assert step.can_retry() is True

    def test_rollback(self):
        """Test rollback closes menu."""
        context = create_test_context()
        context.step_data["menu_open"] = True

        step = OpenMenuStep()
        success = step.rollback(context)

        assert success is True
        context.driver.press_keycode.assert_called_with(4)


class TestClickMoreStep:
    """Tests for ClickMoreStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = ClickMoreStep()
        assert step.name == "click_more"
        assert step.step_index == 2

    def test_execute_success(self):
        """Test successful 'More' click."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["menu_open"] = True

        step = ClickMoreStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("submenu_open") is True

    def test_validate_preconditions(self):
        """Test precondition validation."""
        context = create_test_context()

        step = ClickMoreStep()

        # Without menu_open, should fail
        result = step.validate_preconditions(context)
        assert result.is_err()

        # With menu_open, should pass
        context.step_data["menu_open"] = True
        result = step.validate_preconditions(context)
        assert result.is_ok()


class TestClickExportStep:
    """Tests for ClickExportStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = ClickExportStep()
        assert step.name == "click_export"
        assert step.step_index == 3

    def test_execute_success(self):
        """Test successful 'Export chat' click."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["submenu_open"] = True

        step = ClickExportStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("export_dialog_open") is True


class TestSelectMediaStep:
    """Tests for SelectMediaStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = SelectMediaStep()
        assert step.name == "select_media"
        assert step.step_index == 4

    def test_execute_with_media(self):
        """Test selecting 'Include media'."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, include_media=True)
        context.step_data["export_dialog_open"] = True

        step = SelectMediaStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert result.data.get("include_media") is True

    def test_execute_without_media(self):
        """Test selecting 'Without media'."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, include_media=False)
        context.step_data["export_dialog_open"] = True

        step = SelectMediaStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert result.data.get("include_media") is False


class TestSelectDriveStep:
    """Tests for SelectDriveStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = SelectDriveStep()
        assert step.name == "select_drive"
        assert step.step_index == 5

    def test_execute_success(self):
        """Test successful Drive selection."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["share_dialog_open"] = True

        step = SelectDriveStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("drive_selected") is True


class TestClickUploadStep:
    """Tests for ClickUploadStep."""

    def test_step_metadata(self):
        """Test step metadata."""
        step = ClickUploadStep()
        assert step.name == "click_upload"
        assert step.step_index == 6

    def test_execute_success(self):
        """Test successful upload click."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["drive_selected"] = True
        context.driver.current_package = "com.whatsapp"

        step = ClickUploadStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("upload_started") is True


class TestBaseExportStep:
    """Tests for BaseExportStep abstract class."""

    def test_execute_with_retry_success(self):
        """Test retry logic with eventual success."""
        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)

        step = OpenMenuStep()
        result = step.execute_with_retry(context)

        assert result.status == StepStatus.COMPLETED
        assert result.attempts == 1

    def test_execute_with_retry_failure(self):
        """Test retry logic with persistent failure."""
        finder = MockElementFinder(should_fail=True)
        context = create_test_context(element_finder=finder)

        step = OpenMenuStep()
        step.max_retries = 1
        step.retry_delay_seconds = 0.01

        result = step.execute_with_retry(context)

        assert result.status == StepStatus.FAILED
        assert result.attempts == 2  # Initial + 1 retry


class TestExportWorkflow:
    """Tests for ExportWorkflow orchestrator."""

    def test_workflow_creation(self):
        """Test workflow creation."""
        mock_driver = Mock()
        finder = MockElementFinder()

        workflow = ExportWorkflow(driver=mock_driver, element_finder=finder)

        assert len(workflow.steps) == 6

    def test_workflow_execute_all_success(self):
        """Test workflow with all steps succeeding."""
        mock_driver = Mock()
        mock_driver.current_package = "com.whatsapp"
        mock_driver.find_elements.return_value = []
        mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)

        workflow = ExportWorkflow(driver=mock_driver, element_finder=finder)

        result = workflow.execute(chat_name="Test Chat")

        assert result.status == WorkflowStatus.COMPLETED
        assert result.steps_completed == 6
        assert result.success is True

    def test_workflow_execute_with_skip(self):
        """Test workflow with a step being skipped."""
        mock_driver = Mock()
        mock_driver.current_package = "com.whatsapp"
        mock_driver.find_elements.return_value = []

        mock_element = Mock()

        # Create a custom finder that fails for export step
        class SkipFinder(MockElementFinder):
            def find(self, selectors, **kwargs):
                context = kwargs.get("context", "")
                if "click_export" in context or selectors.name == "export_chat_option":
                    from whatsapp_chat_autoexport.core.errors import (
                        ElementNotFoundError,
                    )

                    return Err(
                        ElementNotFoundError(
                            message="Not found",
                            element_name=selectors.name,
                        )
                    )
                return super().find(selectors, **kwargs)

        finder = SkipFinder(return_element=mock_element)

        # Mock _is_community_chat to return True
        workflow = ExportWorkflow(driver=mock_driver, element_finder=finder)

        # Patch ClickExportStep._is_community_chat
        with patch.object(
            ClickExportStep, "_is_community_chat", return_value=True
        ):
            result = workflow.execute(chat_name="Community Chat")

        assert result.status == WorkflowStatus.SKIPPED
        assert result.skipped is True

    def test_workflow_result_properties(self):
        """Test WorkflowResult properties."""
        from whatsapp_chat_autoexport.whatsapp.export.export_workflow import (
            WorkflowResult,
        )

        # Success result
        success_result = WorkflowResult(
            status=WorkflowStatus.COMPLETED,
            chat_name="Test",
            message="Done",
            steps_completed=6,
        )
        assert success_result.success is True
        assert success_result.skipped is False

        # Skipped result
        skipped_result = WorkflowResult(
            status=WorkflowStatus.SKIPPED,
            chat_name="Test",
            message="Skipped",
            steps_completed=3,
        )
        assert skipped_result.success is False
        assert skipped_result.skipped is True

    def test_workflow_passes_timeout_config_to_context(self):
        """Test that ExportWorkflow passes its timeout_config to the StepContext."""
        mock_driver = Mock()
        mock_driver.current_package = "com.whatsapp"
        mock_driver.find_elements.return_value = []
        mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

        mock_element = Mock()
        finder = MockElementFinder(return_element=mock_element)
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)

        workflow = ExportWorkflow(
            driver=mock_driver,
            element_finder=finder,
            timeout_config=fast_config,
        )

        assert workflow.timeout_config is fast_config

        result = workflow.execute(chat_name="Test Chat")
        assert result.status == WorkflowStatus.COMPLETED

    def test_workflow_defaults_to_global_timeout_config(self):
        """Test that ExportWorkflow uses global timeout config when none provided."""
        reset_timeout_config()
        mock_driver = Mock()
        finder = MockElementFinder()

        workflow = ExportWorkflow(driver=mock_driver, element_finder=finder)

        global_config = get_timeout_config()
        assert workflow.timeout_config is global_config


# ============================================================================
# Smart Wait Characterization Tests (Unit 2)
#
# These tests verify that all hardcoded time.sleep() calls have been replaced
# with condition-based waits using element_finder.find() and timeout_config.
# ============================================================================


class TrackingElementFinder(MockElementFinder):
    """Element finder that records find calls with context and timeout info."""

    def __init__(self, return_element=None, should_fail=False, fail_contexts=None):
        super().__init__(return_element, should_fail)
        self.fail_contexts = fail_contexts or set()
        self.find_call_details = []

    def find(self, selectors, timeout=5.0, wait_visible=True, context=None):
        self.find_call_details.append({
            "selectors_name": selectors.name,
            "timeout": timeout,
            "context": context,
        })
        if context and any(fc in context for fc in self.fail_contexts):
            from whatsapp_chat_autoexport.core.errors import ElementNotFoundError
            return Err(
                ElementNotFoundError(
                    message="Element not found",
                    element_name=selectors.name,
                )
            )
        return super().find(selectors, timeout=timeout, wait_visible=wait_visible, context=context)


class TestClickMoreStepSmartWaits:
    """Characterization tests for ClickMoreStep smart wait behavior."""

    def test_no_time_sleep_in_source(self):
        """Verify no time.sleep() calls exist in click_more.py."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.click_more import ClickMoreStep
        source = inspect.getsource(ClickMoreStep)
        assert "time.sleep" not in source

    def test_completes_without_sleep_when_element_immediately_available(self):
        """ClickMoreStep completes without any sleep when element is immediately found."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["menu_open"] = True

        step = ClickMoreStep()
        start = time.monotonic()
        result = step.execute(context)
        elapsed = time.monotonic() - start

        assert result.status == StepStatus.COMPLETED
        # Should be nearly instantaneous (no 0.3s sleep)
        assert elapsed < 0.2
        mock_element.click.assert_called_once()

    def test_element_finder_receives_correct_timeout(self):
        """ClickMoreStep uses context.timeout_seconds for element find."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["menu_open"] = True

        step = ClickMoreStep()
        step.execute(context)

        assert len(finder.find_call_details) == 1
        assert finder.find_call_details[0]["timeout"] == context.timeout_seconds


class TestClickExportStepSmartWaits:
    """Characterization tests for ClickExportStep smart wait behavior."""

    def test_no_time_sleep_in_source(self):
        """Verify no time.sleep() calls exist in click_export.py."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.click_export import ClickExportStep
        source = inspect.getsource(ClickExportStep)
        assert "time.sleep" not in source

    def test_waits_for_media_dialog_element_after_click(self):
        """After clicking export, waits for media selection dialog element."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["submenu_open"] = True

        step = ClickExportStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        # Should have two find calls: one for export option, one for dialog wait
        assert len(finder.find_call_details) >= 2
        dialog_wait = finder.find_call_details[1]
        assert "export_dialog_wait" in dialog_wait["context"]
        assert dialog_wait["timeout"] == context.timeout_config.screen_transition_wait

    def test_uses_screen_transition_wait_as_timeout_ceiling(self):
        """Post-click wait uses screen_transition_wait from timeout config."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, timeout_config=fast_config)
        context.step_data["submenu_open"] = True

        step = ClickExportStep()
        step.execute(context)

        dialog_wait = finder.find_call_details[1]
        assert dialog_wait["timeout"] == fast_config.screen_transition_wait
        assert dialog_wait["timeout"] == 0.5  # FAST profile value

    def test_fast_profile_uses_shorter_ceiling_than_normal(self):
        """FAST profile uses shorter screen_transition_wait than NORMAL."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        normal_config = TimeoutConfig()

        assert fast_config.screen_transition_wait < normal_config.screen_transition_wait

    def test_completes_when_dialog_wait_element_not_found(self):
        """Step still completes even if dialog wait element is not found (graceful degradation)."""
        mock_element = Mock()
        # Fail only the dialog wait find, succeed on the main element find
        finder = TrackingElementFinder(
            return_element=mock_element,
            fail_contexts={"export_dialog_wait"},
        )
        context = create_test_context(element_finder=finder)
        context.step_data["submenu_open"] = True

        step = ClickExportStep()
        result = step.execute(context)

        # Should still succeed — the dialog wait is best-effort
        assert result.status == StepStatus.COMPLETED


class TestSelectMediaStepSmartWaits:
    """Characterization tests for SelectMediaStep smart wait behavior."""

    def test_no_time_sleep_in_source(self):
        """Verify no time.sleep() calls exist in select_media.py."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.select_media import SelectMediaStep
        source = inspect.getsource(SelectMediaStep)
        assert "time.sleep" not in source

    def test_waits_for_drive_option_after_media_selection(self):
        """After selecting media option, waits for Drive option to appear."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, include_media=True)
        context.step_data["export_dialog_open"] = True

        step = SelectMediaStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        # Should have find calls: media option + share dialog wait
        share_wait_calls = [
            c for c in finder.find_call_details
            if c["context"] and "share_dialog_wait" in c["context"]
        ]
        assert len(share_wait_calls) == 1
        assert share_wait_calls[0]["timeout"] == context.timeout_config.screen_transition_wait

    def test_completes_when_share_dialog_wait_element_not_found(self):
        """Step still completes even if share dialog wait element is not found."""
        mock_element = Mock()
        finder = TrackingElementFinder(
            return_element=mock_element,
            fail_contexts={"share_dialog_wait"},
        )
        context = create_test_context(element_finder=finder, include_media=True)
        context.step_data["export_dialog_open"] = True

        step = SelectMediaStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED


class TestSelectDriveStepSmartWaits:
    """Characterization tests for SelectDriveStep smart wait behavior."""

    def test_no_time_sleep_in_source(self):
        """Verify no time.sleep() calls exist in select_drive.py."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.select_drive import SelectDriveStep
        source = inspect.getsource(SelectDriveStep)
        assert "time.sleep" not in source

    def test_waits_for_upload_button_after_my_drive_selection(self):
        """After clicking My Drive, waits for upload button to appear."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["share_dialog_open"] = True

        step = SelectDriveStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        # Should have a wait call for upload button after My Drive click
        folder_wait_calls = [
            c for c in finder.find_call_details
            if c["context"] and "drive_folder_wait" in c["context"]
        ]
        assert len(folder_wait_calls) == 1
        assert folder_wait_calls[0]["timeout"] == context.timeout_config.screen_transition_wait

    def test_completes_without_pre_find_sleep(self):
        """SelectDriveStep has no pre-find sleep before finding Drive in share sheet."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["share_dialog_open"] = True

        step = SelectDriveStep()
        start = time.monotonic()
        result = step.execute(context)
        elapsed = time.monotonic() - start

        assert result.status == StepStatus.COMPLETED
        # No 0.5s + 1.0s pre-find sleeps
        assert elapsed < 0.3

    def test_fast_profile_uses_shorter_ceiling_for_drive_wait(self):
        """FAST profile uses shorter screen_transition_wait for Drive picker wait."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, timeout_config=fast_config)
        context.step_data["share_dialog_open"] = True

        step = SelectDriveStep()
        step.execute(context)

        folder_wait_calls = [
            c for c in finder.find_call_details
            if c["context"] and "drive_folder_wait" in c["context"]
        ]
        assert len(folder_wait_calls) == 1
        assert folder_wait_calls[0]["timeout"] == 0.5  # FAST profile screen_transition_wait


class TestClickUploadStepSmartWaits:
    """Characterization tests for ClickUploadStep smart wait behavior."""

    def test_no_hardcoded_sleep_in_main_execute_path(self):
        """Verify no hardcoded time.sleep() calls in main execute flow (only in poll loop)."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.click_upload import ClickUploadStep
        source = inspect.getsource(ClickUploadStep)
        # time.sleep is only allowed inside _poll_upload_started
        # Check that it doesn't appear in execute() itself
        execute_source = inspect.getsource(ClickUploadStep.execute)
        assert "time.sleep" not in execute_source

    def test_polls_for_upload_started_instead_of_sleeping(self):
        """After clicking upload, polls _verify_upload_started instead of sleeping 1.0s."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["drive_selected"] = True
        context.driver.current_package = "com.whatsapp"  # Upload "started" immediately

        step = ClickUploadStep()
        start = time.monotonic()
        result = step.execute(context)
        elapsed = time.monotonic() - start

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("upload_started") is True
        # Should be nearly instant since mock returns whatsapp package immediately
        assert elapsed < 0.3

    def test_poll_uses_step_delay_as_timeout_ceiling(self):
        """_poll_upload_started uses timeout_config.step_delay as deadline."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder, timeout_config=fast_config)
        context.step_data["drive_selected"] = True
        # Make verify always return False to hit timeout
        context.driver.current_package = "com.google.android.apps.docs"
        context.driver.find_elements.return_value = []

        step = ClickUploadStep()
        start = time.monotonic()
        result = step.execute(context)
        elapsed = time.monotonic() - start

        # Should timeout around step_delay (0.3s for FAST) not 1.0s hardcoded
        assert elapsed < fast_config.step_delay + 0.3  # Allow margin for test overhead
        # Still succeeds (upload may have completed very quickly)
        assert result.status == StepStatus.COMPLETED

    def test_poll_detects_upload_started_within_deadline(self):
        """Poll detects upload started when package changes mid-poll."""
        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["drive_selected"] = True

        # First call: still in Drive; subsequent calls: back in WhatsApp
        call_count = [0]
        def mock_current_package():
            call_count[0] += 1
            if call_count[0] <= 2:
                return "com.google.android.apps.docs"
            return "com.whatsapp"

        type(context.driver).current_package = property(lambda self: mock_current_package())

        step = ClickUploadStep()
        result = step.execute(context)

        assert result.status == StepStatus.COMPLETED
        assert context.step_data.get("upload_started") is True

    def test_element_not_found_within_timeout_fails_with_clear_error(self):
        """When upload button is not found within timeout, step fails clearly."""
        finder = TrackingElementFinder(should_fail=True)
        context = create_test_context(element_finder=finder)
        context.step_data["drive_selected"] = True
        # Also make alternate strategy find no buttons
        context.driver.find_elements.return_value = []

        step = ClickUploadStep()
        result = step.execute(context)

        assert result.status == StepStatus.FAILED
        assert result.error is not None
        assert "upload" in result.error.message.lower() or "Upload" in result.error.message


class TestStaleElementHandling:
    """Test that steps handle stale elements gracefully."""

    def test_click_export_handles_stale_element(self):
        """ClickExportStep handles element that becomes stale after find."""
        mock_element = Mock()
        mock_element.click.side_effect = Exception("StaleElementReferenceException")
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["submenu_open"] = True

        step = ClickExportStep()
        result = step.execute(context)

        # Should fail gracefully, not crash
        assert result.status == StepStatus.FAILED
        assert result.error is not None

    def test_select_drive_handles_stale_element(self):
        """SelectDriveStep handles element that becomes stale after find."""
        mock_element = Mock()
        mock_element.click.side_effect = Exception("StaleElementReferenceException")
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["share_dialog_open"] = True

        step = SelectDriveStep()
        result = step.execute(context)

        assert result.status == StepStatus.FAILED
        assert result.error is not None

    def test_click_upload_handles_stale_element(self):
        """ClickUploadStep handles element that becomes stale after find."""
        mock_element = Mock()
        mock_element.click.side_effect = Exception("StaleElementReferenceException")
        finder = MockElementFinder(return_element=mock_element)
        context = create_test_context(element_finder=finder)
        context.step_data["drive_selected"] = True

        step = ClickUploadStep()
        result = step.execute(context)

        assert result.status == StepStatus.FAILED
        assert result.error is not None


class TestNoSleepsInStepFiles:
    """Meta-test: verify that no time.sleep() calls remain in any step file."""

    def test_no_time_sleep_in_click_more(self):
        """click_more.py has no time.sleep() calls."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps import click_more
        source = inspect.getsource(click_more)
        assert "time.sleep" not in source

    def test_no_time_sleep_in_click_export(self):
        """click_export.py has no time.sleep() calls."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps import click_export
        source = inspect.getsource(click_export)
        assert "time.sleep" not in source

    def test_no_time_sleep_in_select_media(self):
        """select_media.py has no time.sleep() calls."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps import select_media
        source = inspect.getsource(select_media)
        assert "time.sleep" not in source

    def test_no_time_sleep_in_select_drive(self):
        """select_drive.py has no time.sleep() calls."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps import select_drive
        source = inspect.getsource(select_drive)
        assert "time.sleep" not in source

    def test_time_sleep_only_in_poll_loop_for_click_upload(self):
        """click_upload.py only has time.sleep inside _poll_upload_started."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.click_upload import ClickUploadStep

        # No sleep in execute()
        execute_source = inspect.getsource(ClickUploadStep.execute)
        assert "time.sleep" not in execute_source

        # No sleep in _try_alternate_strategies()
        alt_source = inspect.getsource(ClickUploadStep._try_alternate_strategies)
        assert "time.sleep" not in alt_source

        # Sleep IS expected in _poll_upload_started() (polling loop)
        poll_source = inspect.getsource(ClickUploadStep._poll_upload_started)
        assert "time.sleep" in poll_source

    def test_base_step_retry_delays_preserved(self):
        """base_step.py retains time.sleep for retry delays (intentional)."""
        import inspect
        from whatsapp_chat_autoexport.whatsapp.export.steps.base_step import BaseExportStep
        source = inspect.getsource(BaseExportStep.execute_with_retry)
        assert "time.sleep(self.retry_delay_seconds)" in source


class TestWorkflowSmartWaitsIntegration:
    """Integration test: full workflow completes with smart waits and timeout_config."""

    def test_workflow_completes_faster_with_fast_profile(self):
        """Workflow with FAST profile completes without unnecessary delays."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_driver = Mock()
        mock_driver.current_package = "com.whatsapp"
        mock_driver.find_elements.return_value = []
        mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)

        workflow = ExportWorkflow(
            driver=mock_driver,
            element_finder=finder,
            timeout_config=fast_config,
        )

        start = time.monotonic()
        result = workflow.execute(chat_name="Test Chat")
        elapsed = time.monotonic() - start

        assert result.status == WorkflowStatus.COMPLETED
        assert result.steps_completed == 6
        # With mocked elements returning immediately, should complete very fast
        # Old code with hardcoded sleeps would take ~6.5s
        assert elapsed < 2.0

    def test_workflow_steps_use_timeout_config_values(self):
        """Steps in the workflow use timeout_config values for waits."""
        fast_config = TimeoutConfig.for_profile(TimeoutProfile.FAST)
        mock_driver = Mock()
        mock_driver.current_package = "com.whatsapp"
        mock_driver.find_elements.return_value = []
        mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

        mock_element = Mock()
        finder = TrackingElementFinder(return_element=mock_element)

        workflow = ExportWorkflow(
            driver=mock_driver,
            element_finder=finder,
            timeout_config=fast_config,
        )

        result = workflow.execute(chat_name="Test Chat")
        assert result.status == WorkflowStatus.COMPLETED

        # Check that screen_transition_wait values were used in find calls
        transition_wait_calls = [
            c for c in finder.find_call_details
            if c["timeout"] == fast_config.screen_transition_wait
        ]
        # Should have at least the post-click waits from click_export, select_media, select_drive
        assert len(transition_wait_calls) >= 3
