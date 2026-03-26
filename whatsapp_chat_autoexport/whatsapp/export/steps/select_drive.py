"""
Step 5: Select Google Drive from the share sheet.
"""

import time
from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError
from ....config.selectors import create_default_selectors, ElementSelectors, SelectorDefinition, SelectorStrategy


class SelectDriveStep(BaseExportStep):
    """
    Selects Google Drive from the Android share sheet.

    Also handles selecting the 'My Drive' folder within the Drive picker.
    """

    name = "select_drive"
    description = "Select Google Drive destination"
    step_index = 5

    max_retries = 3
    retry_delay_seconds = 1.0

    def execute(self, context: StepContext) -> StepResult:
        """
        Select Google Drive and navigate to My Drive.

        Args:
            context: Step context with driver

        Returns:
            StepResult indicating success or failure
        """
        context.log_debug("Selecting Google Drive from share sheet")

        # Wait for share sheet to load
        time.sleep(0.5)

        # Step 1: Find and click Google Drive in share sheet
        drive_result = self._select_drive_app(context)
        if drive_result.status != StepStatus.COMPLETED:
            return drive_result

        # Wait for Drive picker to load
        time.sleep(1.0)

        # Step 2: Select My Drive folder
        folder_result = self._select_my_drive(context)
        if folder_result.status != StepStatus.COMPLETED:
            return folder_result

        context.step_data["drive_selected"] = True
        return StepResult.success("Google Drive selected with My Drive folder")

    def _select_drive_app(self, context: StepContext) -> StepResult:
        """Find and click the Google Drive option in share sheet."""
        selectors = create_default_selectors().get("google_drive_option")
        if not selectors:
            # Create fallback selectors
            selectors = ElementSelectors(
                name="google_drive_option",
                strategies=[
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT,
                        value="Drive",
                        priority=1,
                    ),
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT_CONTAINS,
                        value="drive",
                        case_sensitive=False,
                        priority=2,
                    ),
                ],
            )

        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"share_sheet_{self.name}",
        )

        if result.is_err():
            # Try scrolling the share sheet
            if self._scroll_share_sheet(context):
                result = context.element_finder.find(
                    selectors,
                    timeout=2.0,
                    context=f"share_sheet_{self.name}_scrolled",
                )

        if result.is_err():
            error = result.error
            context.log_error(f"Could not find Google Drive option: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="Google Drive not found in share sheet",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        drive_option = find_result.element

        try:
            drive_option.click()
            context.log_debug("Google Drive selected")
            return StepResult.success("Google Drive app selected")
        except Exception as e:
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click Google Drive: {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def _select_my_drive(self, context: StepContext) -> StepResult:
        """Select 'My Drive' folder in the Drive picker."""
        selectors = create_default_selectors().get("my_drive_folder")
        if not selectors:
            selectors = ElementSelectors(
                name="my_drive_folder",
                strategies=[
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT,
                        value="My Drive",
                        priority=1,
                    ),
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT,
                        value="Drive",
                        priority=2,
                    ),
                ],
            )

        result = context.element_finder.find(
            selectors,
            timeout=5.0,
            context=f"drive_picker_{self.name}",
        )

        if result.is_err():
            # My Drive might already be selected, check if we can proceed
            upload_selectors = create_default_selectors().get("upload_button")
            if upload_selectors:
                is_present = context.element_finder.is_present(
                    upload_selectors, timeout=2.0
                )
                if is_present:
                    context.log_debug("Upload button visible - My Drive may be pre-selected")
                    return StepResult.success("My Drive appears to be selected")

            error = result.error
            context.log_error(f"Could not find My Drive folder: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="'My Drive' folder not found",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        folder_option = find_result.element

        try:
            folder_option.click()
            context.log_debug("'My Drive' folder selected")
            time.sleep(0.5)
            return StepResult.success("'My Drive' folder selected")
        except Exception as e:
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click 'My Drive': {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def _scroll_share_sheet(self, context: StepContext) -> bool:
        """Scroll the share sheet to find more options."""
        try:
            # Get screen dimensions
            size = context.driver.get_window_size()
            start_x = size["width"] // 2
            start_y = size["height"] // 2
            end_x = start_x
            end_y = int(size["height"] * 0.3)

            context.driver.swipe(start_x, start_y, end_x, end_y, 300)
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def rollback(self, context: StepContext) -> bool:
        """
        Go back from Drive picker.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded
        """
        if context.step_data.get("drive_selected"):
            try:
                context.driver.press_keycode(4)  # Android BACK key
                context.step_data["drive_selected"] = False
                return True
            except Exception:
                return False
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that share dialog is open.

        Args:
            context: Step context

        Returns:
            Ok(True) if share dialog is open
        """
        if not context.step_data.get("share_dialog_open"):
            return Err(
                ExportWorkflowError(
                    message="Share dialog not open - previous step may have failed",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )
        return Ok(True)
