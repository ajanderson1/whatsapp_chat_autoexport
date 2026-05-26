"""
Step 1: Open the three-dot menu in chat view.
"""

from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError, ElementNotFoundError
from ....config.selectors import create_default_selectors


class OpenMenuStep(BaseExportStep):
    """
    Opens the three-dot overflow menu in the chat view.

    This is the first step in the export workflow. The menu button
    can appear in different locations depending on WhatsApp version.
    """

    name = "open_menu"
    description = "Open the three-dot menu"
    step_index = 1

    max_retries = 2
    retry_delay_seconds = 1.0

    def execute(self, context: StepContext) -> StepResult:
        """
        Click the three-dot menu button.

        Args:
            context: Step context with driver and element finder

        Returns:
            StepResult indicating success or failure
        """
        context.log_debug(f"Opening menu for chat: {context.chat_name}")

        # Get menu button selectors
        selectors = create_default_selectors().get("menu_button")
        if not selectors:
            return StepResult.failed(
                ExportWorkflowError(
                    message="No selectors found for menu button",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )

        # Find and click the menu button
        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"chat_view_{self.name}",
        )

        if result.is_err():
            error = result.error
            context.log_error(f"Could not find menu button: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="Menu button not found",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        menu_button = find_result.element

        try:
            menu_button.click()
            context.log_debug("Menu button clicked successfully")

            # Store that menu is open in context
            context.step_data["menu_open"] = True

            return StepResult.success(
                "Menu opened successfully",
                element_strategy=find_result.strategy.strategy.value,
            )

        except Exception as e:
            context.log_error(f"Failed to click menu button: {e}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click menu button: {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def rollback(self, context: StepContext) -> bool:
        """
        Close the menu if it was opened.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded
        """
        if context.step_data.get("menu_open"):
            try:
                # Press back to close menu
                context.driver.press_keycode(4)  # Android BACK key
                context.step_data["menu_open"] = False
                return True
            except Exception:
                return False
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate we're in a chat view.

        Args:
            context: Step context

        Returns:
            Ok(True) if in chat view
        """
        # Check if chat header is visible
        selectors = create_default_selectors().get("chat_header")
        if selectors:
            is_present = context.element_finder.is_present(selectors, timeout=2.0)
            if not is_present:
                return Err(
                    ExportWorkflowError(
                        message="Not in chat view - chat header not visible",
                        step_name=self.name,
                        chat_name=context.chat_name,
                    )
                )

        return Ok(True)
