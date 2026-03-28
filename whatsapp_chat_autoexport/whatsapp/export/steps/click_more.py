"""
Step 2: Click the 'More' option in the menu.
"""

from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError
from ....config.selectors import create_default_selectors


class ClickMoreStep(BaseExportStep):
    """
    Clicks the 'More' option in the overflow menu.

    This step navigates to the submenu containing the Export option.
    """

    name = "click_more"
    description = "Click the 'More' option"
    step_index = 2

    max_retries = 2
    retry_delay_seconds = 0.5

    def execute(self, context: StepContext) -> StepResult:
        """
        Click the 'More' menu option.

        Args:
            context: Step context with driver and element finder

        Returns:
            StepResult indicating success or failure
        """
        context.log_debug("Looking for 'More' option")

        # Get 'More' option selectors (element_finder.find() already waits for element)
        selectors = create_default_selectors().get("more_option")
        if not selectors:
            return StepResult.failed(
                ExportWorkflowError(
                    message="No selectors found for 'More' option",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )

        # Find and click the 'More' option
        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"menu_{self.name}",
        )

        if result.is_err():
            error = result.error
            context.log_error(f"Could not find 'More' option: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="'More' option not found in menu",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        more_option = find_result.element

        try:
            more_option.click()
            context.log_debug("'More' option clicked successfully")

            # Store that submenu is open
            context.step_data["submenu_open"] = True

            return StepResult.success(
                "'More' clicked successfully",
                element_strategy=find_result.strategy.strategy.value,
            )

        except Exception as e:
            context.log_error(f"Failed to click 'More' option: {e}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click 'More' option: {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def rollback(self, context: StepContext) -> bool:
        """
        Go back to close submenu.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded
        """
        if context.step_data.get("submenu_open"):
            try:
                context.driver.press_keycode(4)  # Android BACK key
                context.step_data["submenu_open"] = False
                return True
            except Exception:
                return False
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that menu is open.

        Args:
            context: Step context

        Returns:
            Ok(True) if menu is open
        """
        if not context.step_data.get("menu_open"):
            return Err(
                ExportWorkflowError(
                    message="Menu not open - previous step may have failed",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )
        return Ok(True)
