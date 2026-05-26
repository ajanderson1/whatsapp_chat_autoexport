"""
Step 4: Select media option (Include/Without media).
"""

from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError
from ....config.selectors import create_default_selectors


class SelectMediaStep(BaseExportStep):
    """
    Selects the media option in the export dialog.

    Chooses either 'Include media' or 'Without media' based on
    the export configuration.
    """

    name = "select_media"
    description = "Select media option"
    step_index = 4

    max_retries = 2
    retry_delay_seconds = 0.5

    def execute(self, context: StepContext) -> StepResult:
        """
        Select the appropriate media option.

        Args:
            context: Step context with include_media flag

        Returns:
            StepResult indicating success or failure
        """
        include_media = context.include_media
        option_name = "Include media" if include_media else "Without media"
        selector_key = "include_media_button" if include_media else "without_media_button"

        context.log_debug(f"Selecting '{option_name}'")

        # Check if this is a text-only chat (element_finder.find() already waits) (share dialog appeared directly)
        if self._is_share_dialog_visible(context):
            context.log_debug(
                "Share dialog visible - chat may have no media, skipping media selection"
            )
            context.step_data["share_dialog_open"] = True
            return StepResult.success(
                "Media selection skipped (text-only chat)",
                skipped_reason="share_dialog_visible",
            )

        # Get media option selectors
        selectors = create_default_selectors().get(selector_key)
        if not selectors:
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"No selectors found for '{option_name}' option",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )

        # Find and click the media option
        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"export_dialog_{self.name}",
        )

        if result.is_err():
            # Check again if share dialog appeared (race condition)
            if self._is_share_dialog_visible(context):
                context.step_data["share_dialog_open"] = True
                return StepResult.success(
                    "Media selection skipped (text-only chat)",
                    skipped_reason="share_dialog_visible",
                )

            error = result.error
            context.log_error(f"Could not find '{option_name}' option: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"'{option_name}' option not found",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        media_option = find_result.element

        try:
            media_option.click()
            context.log_debug(f"'{option_name}' selected successfully")

            # Wait for share dialog by looking for the Drive option
            # instead of a hardcoded sleep
            drive_selectors = create_default_selectors().get("google_drive_option")
            if drive_selectors:
                context.element_finder.find(
                    drive_selectors,
                    timeout=context.timeout_config.screen_transition_wait,
                    context=f"share_dialog_wait_{self.name}",
                )
                # Result intentionally ignored — just need the wait.
                # The share dialog check or subsequent steps handle failures.

            context.step_data["share_dialog_open"] = True

            return StepResult.success(
                f"'{option_name}' selected",
                include_media=include_media,
            )

        except Exception as e:
            context.log_error(f"Failed to click '{option_name}': {e}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click '{option_name}': {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def _is_share_dialog_visible(self, context: StepContext) -> bool:
        """
        Check if the Android share dialog is visible.

        This indicates WhatsApp skipped the media selection dialog,
        likely because the chat has no media.
        """
        try:
            # Check for share dialog package
            current_package = context.driver.current_package
            if current_package == "com.android.intentresolver":
                return True

            # Check for share dialog indicators
            all_text = context.driver.find_elements("xpath", "//android.widget.TextView")
            for elem in all_text:
                try:
                    text = elem.text.lower() if elem.text else ""
                    if "sharing" in text and ("file" in text or "files" in text):
                        return True
                    if text == "my drive":
                        return True
                except Exception:
                    continue

        except Exception:
            pass

        return False

    def rollback(self, context: StepContext) -> bool:
        """
        Close the share dialog.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded
        """
        if context.step_data.get("share_dialog_open"):
            try:
                context.driver.press_keycode(4)  # Android BACK key
                context.step_data["share_dialog_open"] = False
                return True
            except Exception:
                return False
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that export dialog is open.

        Args:
            context: Step context

        Returns:
            Ok(True) if export dialog is open
        """
        if not context.step_data.get("export_dialog_open"):
            return Err(
                ExportWorkflowError(
                    message="Export dialog not open - previous step may have failed",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )
        return Ok(True)
