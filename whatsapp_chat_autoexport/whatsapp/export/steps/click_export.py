"""
Step 3: Click the 'Export chat' option.
"""

import time
from typing import Any, Dict, Optional

from .base_step import BaseExportStep, StepContext, StepResult, StepStatus
from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError, ErrorCategory
from ....config.selectors import create_default_selectors


class ClickExportStep(BaseExportStep):
    """
    Clicks the 'Export chat' option in the More submenu.

    This step may encounter chats that cannot be exported (community chats,
    privacy-restricted chats). These cases result in a SKIPPED status.
    """

    name = "click_export"
    description = "Click 'Export chat' option"
    step_index = 3

    max_retries = 2
    retry_delay_seconds = 0.5

    def execute(self, context: StepContext) -> StepResult:
        """
        Click the 'Export chat' menu option.

        Args:
            context: Step context with driver and element finder

        Returns:
            StepResult - may be SKIPPED if chat is not exportable
        """
        context.log_debug("Looking for 'Export chat' option")

        # Wait for submenu animation
        time.sleep(0.3)

        # Get 'Export chat' selectors
        selectors = create_default_selectors().get("export_chat_option")
        if not selectors:
            return StepResult.failed(
                ExportWorkflowError(
                    message="No selectors found for 'Export chat' option",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )

        # Find the 'Export chat' option
        result = context.element_finder.find(
            selectors,
            timeout=context.timeout_seconds,
            context=f"submenu_{self.name}",
        )

        if result.is_err():
            # Export option not found - check if this is a non-exportable chat
            if self._is_community_chat(context):
                context.log_warning(f"Skipping community chat: {context.chat_name}")
                return StepResult.skipped("Community chat - cannot export")

            error = result.error
            context.log_error(f"Could not find 'Export chat' option: {error}")
            return StepResult.failed(
                ExportWorkflowError(
                    message="'Export chat' option not found",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=error if isinstance(error, Exception) else None,
                )
            )

        find_result = result.unwrap()
        export_option = find_result.element

        try:
            export_option.click()
            context.log_debug("'Export chat' clicked successfully")

            # Wait for export dialog to appear
            time.sleep(0.5)

            # Check for privacy error dialog
            if self._check_privacy_error(context):
                context.log_warning(
                    f"Chat has privacy restrictions: {context.chat_name}"
                )
                return StepResult.skipped("Advanced chat privacy enabled")

            context.step_data["export_dialog_open"] = True

            return StepResult.success(
                "'Export chat' clicked successfully",
                element_strategy=find_result.strategy.strategy.value,
            )

        except Exception as e:
            context.log_error(f"Failed to click 'Export chat': {e}")
            return StepResult.failed(
                ExportWorkflowError(
                    message=f"Failed to click 'Export chat': {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
            )

    def _is_community_chat(self, context: StepContext) -> bool:
        """
        Check if this appears to be a community chat.

        Community chats don't have an export option.
        """
        try:
            # Look for community indicators in the visible text
            all_text = context.driver.find_elements("xpath", "//android.widget.TextView")
            for elem in all_text:
                try:
                    text = elem.text.lower() if elem.text else ""
                    if "community" in text or "announcement" in text:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _check_privacy_error(self, context: StepContext) -> bool:
        """
        Check if an advanced chat privacy error dialog appeared.

        Some chats have privacy settings that prevent export.
        """
        try:
            all_text = context.driver.find_elements("xpath", "//android.widget.TextView")
            for elem in all_text:
                try:
                    text = elem.text.lower() if elem.text else ""
                    if (
                        "advanced chat privacy" in text
                        or "can't export" in text
                        or "cannot export" in text
                        or "prevents the exporting" in text
                    ):
                        # Dismiss the error dialog
                        self._dismiss_error_dialog(context)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _dismiss_error_dialog(self, context: StepContext) -> None:
        """Attempt to dismiss an error dialog by clicking OK."""
        try:
            ok_selectors = create_default_selectors().get("ok_button")
            if ok_selectors:
                result = context.element_finder.find(ok_selectors, timeout=2.0)
                if result.is_ok():
                    result.unwrap().element.click()
        except Exception:
            # Try pressing back as fallback
            try:
                context.driver.press_keycode(4)
            except Exception:
                pass

    def rollback(self, context: StepContext) -> bool:
        """
        Close the export dialog.

        Args:
            context: Step context

        Returns:
            True if rollback succeeded
        """
        if context.step_data.get("export_dialog_open"):
            try:
                context.driver.press_keycode(4)  # Android BACK key
                context.step_data["export_dialog_open"] = False
                return True
            except Exception:
                return False
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that submenu is open.

        Args:
            context: Step context

        Returns:
            Ok(True) if submenu is open
        """
        if not context.step_data.get("submenu_open"):
            return Err(
                ExportWorkflowError(
                    message="Submenu not open - previous step may have failed",
                    step_name=self.name,
                    chat_name=context.chat_name,
                )
            )
        return Ok(True)
