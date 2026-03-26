"""
Tests for export step classes.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
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
):
    """Create a StepContext for testing."""
    mock_driver = Mock()
    mock_driver.current_package = "com.whatsapp"
    mock_driver.find_elements.return_value = []
    mock_driver.get_window_size.return_value = {"width": 1080, "height": 1920}

    return StepContext(
        driver=mock_driver,
        element_finder=element_finder or MockElementFinder(),
        chat_name=chat_name,
        include_media=include_media,
    )


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
