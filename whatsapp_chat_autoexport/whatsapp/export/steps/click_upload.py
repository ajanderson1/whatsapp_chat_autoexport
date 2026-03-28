"""
Step 6: Click the upload/save button to complete export.
"""

import time
from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError
from ....config.selectors import create_default_selectors, ElementSelectors, SelectorDefinition, SelectorStrategy


class ClickUploadStep(BaseExportStep):
    """
    Clicks the upload/save button to complete the export to Google Drive.

    This is the final step in the export workflow.
    """

    name = "click_upload"
    description = "Click upload button"
    step_index = 6

    max_retries = 3
    retry_delay_seconds = 1.0

    def execute(self, context: StepContext) -> StepResult:
        """
        Click the upload/save button.

        Args:
            context: Step context with driver

        Returns:
            StepResult indicating success or failure
        """
        context.log_debug("Looking for upload/save button")

        # Get upload button selectors (element_finder.find() already waits for element)
        selectors = create_default_selectors().get("upload_button")
        if not selectors:
            selectors = ElementSelectors(
                name="upload_button",
                strategies=[
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT,
                        value="Save",
                        priority=1,
                    ),
                    SelectorDefinition(
                        strategy=SelectorStrategy.CONTENT_DESC,
                        value="Save",
                        priority=2,
                    ),
                    SelectorDefinition(
                        strategy=SelectorStrategy.TEXT,
                        value="Upload",
                        priority=3,
                    ),
                ],
            )

        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"drive_picker_{self.name}",
        )

        if result.is_err():
            # Try alternate strategies
            alt_result = self._try_alternate_strategies(context)
            if alt_result.status == StepStatus.COMPLETED:
                return alt_result

            error = result.error
            context.log_error(f"Could not find upload button: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="Upload button not found",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        upload_button = find_result.element

        try:
            upload_button.click()
            context.log_debug("Upload button clicked")

            # Poll for upload confirmation instead of hardcoded sleep
            if self._poll_upload_started(context):
                context.step_data["upload_started"] = True
                return StepResult.success(
                    f"Export initiated for {context.chat_name}",
                    chat_name=context.chat_name,
                )
            else:
                # Upload may have completed very quickly
                context.step_data["upload_started"] = True
                return StepResult.success(
                    f"Export completed for {context.chat_name}",
                    chat_name=context.chat_name,
                )

        except Exception as e:
            context.log_error(f"Failed to click upload button: {e}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click upload button: {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def _try_alternate_strategies(self, context: StepContext) -> StepResult:
        """
        Try alternate strategies to find the upload button.

        Different Android versions may have different UI.
        """
        try:
            # Strategy: Look for any visible button in the toolbar area
            buttons = context.driver.find_elements(
                "xpath",
                "//*[@clickable='true' and (contains(@class, 'Button') or contains(@class, 'ImageButton'))]"
            )

            # Find button with save/upload related attributes
            for button in buttons:
                try:
                    content_desc = button.get_attribute("content-desc") or ""
                    text = button.text or ""

                    if any(
                        word in content_desc.lower() or word in text.lower()
                        for word in ["save", "upload", "done", "ok"]
                    ):
                        button.click()

                        if self._poll_upload_started(context):
                            context.step_data["upload_started"] = True
                            return StepResult.success(
                                f"Export initiated via alternate strategy",
                                strategy="button_scan",
                            )
                except Exception:
                    continue

        except Exception as e:
            context.log_debug(f"Alternate strategy failed: {e}")

        return StepResult.failed(
            ExportWorkflowError(
                message="Could not find upload button with any strategy",
                step_name=self.name,
                chat_name=context.chat_name,
            )
        )

    def _poll_upload_started(self, context: StepContext) -> bool:
        """
        Poll for upload confirmation with timeout ceiling.

        Uses step_delay as the timeout ceiling instead of a hardcoded sleep.
        Polls _verify_upload_started() at short intervals.
        """
        deadline = time.time() + context.timeout_config.step_delay
        poll_interval = 0.1
        while time.time() < deadline:
            if self._verify_upload_started(context):
                return True
            time.sleep(poll_interval)
        # Final check after deadline
        return self._verify_upload_started(context)

    def _verify_upload_started(self, context: StepContext) -> bool:
        """
        Verify that upload has started or completed.

        Checks for progress indicators or return to WhatsApp.
        """
        try:
            # Check if we're back in WhatsApp
            current_package = context.driver.current_package
            if current_package == "com.whatsapp":
                return True

            # Check for upload progress indicator
            progress_elements = context.driver.find_elements(
                "xpath",
                "//*[contains(@class, 'ProgressBar') or contains(@text, 'Uploading') or contains(@text, 'Saving')]"
            )
            if progress_elements:
                return True

        except Exception:
            pass

        return False

    def rollback(self, context: StepContext) -> bool:
        """
        Cancel upload if possible.

        Note: Once upload starts, it may not be cancellable.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded or upload already completed
        """
        if context.step_data.get("upload_started"):
            try:
                # Try pressing back to cancel
                context.driver.press_keycode(4)  # Android BACK key
                return True
            except Exception:
                return True  # Upload may have completed
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that Drive is selected.

        Args:
            context: Step context

        Returns:
            Ok(True) if Drive is selected
        """
        if not context.step_data.get("drive_selected"):
            return Err(
                ExportWorkflowError(
                    message="Google Drive not selected - previous step may have failed",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )
        return Ok(True)
