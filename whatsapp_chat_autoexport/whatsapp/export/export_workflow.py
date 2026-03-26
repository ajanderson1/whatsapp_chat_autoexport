"""
Export workflow orchestrator.

Coordinates the execution of all export steps for a single chat.
"""

import time
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field
from enum import Enum, auto

from .steps import (
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
from ...core.result import Result, Ok, Err
from ...core.errors import ExportError, ExportWorkflowError
from ...core.events import (
    EventBus,
    EventType,
    ExportProgressEvent,
    emit,
)
from ...automation.elements import ElementFinder


class WorkflowStatus(Enum):
    """Status of the export workflow."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()
    PARTIALLY_COMPLETED = auto()


@dataclass
class WorkflowResult:
    """Result of running the export workflow."""

    status: WorkflowStatus
    chat_name: str
    message: str
    steps_completed: int = 0
    steps_total: int = 6
    step_results: List[StepResult] = field(default_factory=list)
    error: Optional[ExportError] = None
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """Check if workflow completed successfully."""
        return self.status == WorkflowStatus.COMPLETED

    @property
    def skipped(self) -> bool:
        """Check if workflow was skipped."""
        return self.status == WorkflowStatus.SKIPPED


class ExportWorkflow:
    """
    Orchestrates the export of a single WhatsApp chat.

    Executes steps in sequence with retry support and event emission.
    """

    def __init__(
        self,
        driver: Any,
        element_finder: ElementFinder,
        logger: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the workflow.

        Args:
            driver: Appium WebDriver
            element_finder: Element finder instance
            logger: Optional logger
            event_bus: Optional event bus for progress updates
        """
        self.driver = driver
        self.element_finder = element_finder
        self.logger = logger
        self.event_bus = event_bus

        # Initialize steps
        self.steps: List[BaseExportStep] = [
            OpenMenuStep(),
            ClickMoreStep(),
            ClickExportStep(),
            SelectMediaStep(),
            SelectDriveStep(),
            ClickUploadStep(),
        ]

    @classmethod
    def from_whatsapp_driver(
        cls,
        whatsapp_driver: Any,
        logger: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        cache: Optional[Any] = None,
    ) -> "ExportWorkflow":
        """
        Create an ExportWorkflow from an existing WhatsAppDriver.

        This factory method bridges the legacy WhatsAppDriver (from export/)
        with the new modular workflow system. It extracts the underlying
        Appium WebDriver and creates the necessary ElementFinder.

        Args:
            whatsapp_driver: WhatsAppDriver instance with .driver attribute
            logger: Optional logger for debug output
            event_bus: Optional event bus for progress updates
            cache: Optional ElementCache for strategy persistence

        Returns:
            ExportWorkflow configured with the driver's Appium connection

        Example:
            >>> from whatsapp_chat_autoexport.export.whatsapp_driver import WhatsAppDriver
            >>> from whatsapp_chat_autoexport.whatsapp.export import ExportWorkflow
            >>>
            >>> # Assuming whatsapp_driver is already connected
            >>> workflow = ExportWorkflow.from_whatsapp_driver(
            ...     whatsapp_driver,
            ...     logger=logger,
            ... )
            >>> result = workflow.execute("Chat Name", include_media=True)
        """
        # Extract the underlying Appium WebDriver from WhatsAppDriver
        appium_driver = whatsapp_driver.driver

        if appium_driver is None:
            raise ValueError(
                "WhatsAppDriver is not connected. Call connect() first."
            )

        # Create ElementFinder with the raw Appium driver
        element_finder = ElementFinder(
            driver=appium_driver,
            cache=cache,
            logger=logger,
        )

        return cls(
            driver=appium_driver,
            element_finder=element_finder,
            logger=logger,
            event_bus=event_bus,
        )

    def execute(
        self,
        chat_name: str,
        chat_index: int = 0,
        include_media: bool = True,
        timeout_seconds: float = 5.0,
    ) -> WorkflowResult:
        """
        Execute the export workflow for a chat.

        Args:
            chat_name: Name of the chat to export
            chat_index: Index of chat in the list
            include_media: Whether to include media
            timeout_seconds: Timeout for element finding

        Returns:
            WorkflowResult with status and details
        """
        start_time = time.time()

        # Create context
        context = StepContext(
            driver=self.driver,
            element_finder=self.element_finder,
            chat_name=chat_name,
            chat_index=chat_index,
            include_media=include_media,
            timeout_seconds=timeout_seconds,
            total_steps=len(self.steps),
            logger=self.logger,
        )

        # Emit workflow started event
        self._emit_progress(
            chat_name=chat_name,
            step_name="workflow",
            step_index=0,
            status="started",
            message=f"Starting export for {chat_name}",
        )

        step_results: List[StepResult] = []
        last_error: Optional[ExportError] = None

        for i, step in enumerate(self.steps):
            context.current_step = step.name
            context.steps_completed = i

            # Emit step started event
            self._emit_progress(
                chat_name=chat_name,
                step_name=step.name,
                step_index=i + 1,
                status="in_progress",
                message=f"Executing: {step.description}",
            )

            # Validate preconditions
            precondition_result = step.validate_preconditions(context)
            if precondition_result.is_err():
                error = precondition_result.error
                self._log_error(f"Precondition failed for {step.name}: {error}")

                step_results.append(
                    StepResult.failed(error, f"Precondition failed: {error}")
                )
                last_error = error

                # Emit failure event
                self._emit_progress(
                    chat_name=chat_name,
                    step_name=step.name,
                    step_index=i + 1,
                    status="failed",
                    message=f"Precondition failed: {error}",
                )

                break

            # Execute step with retry
            result = step.execute_with_retry(context)
            step_results.append(result)

            if result.status == StepStatus.COMPLETED:
                self._log_debug(f"Step {step.name} completed")
                self._emit_progress(
                    chat_name=chat_name,
                    step_name=step.name,
                    step_index=i + 1,
                    status="completed",
                    message=result.message,
                )

            elif result.status == StepStatus.SKIPPED:
                self._log_info(f"Step {step.name} skipped: {result.message}")
                self._emit_progress(
                    chat_name=chat_name,
                    step_name=step.name,
                    step_index=i + 1,
                    status="skipped",
                    message=result.message,
                )

                # Chat was skipped (e.g., community chat)
                duration = time.time() - start_time
                return WorkflowResult(
                    status=WorkflowStatus.SKIPPED,
                    chat_name=chat_name,
                    message=result.message,
                    steps_completed=i + 1,
                    steps_total=len(self.steps),
                    step_results=step_results,
                    duration_seconds=duration,
                )

            else:  # FAILED
                last_error = result.error
                self._log_error(f"Step {step.name} failed: {result.message}")
                self._emit_progress(
                    chat_name=chat_name,
                    step_name=step.name,
                    step_index=i + 1,
                    status="failed",
                    message=result.message,
                )

                # Attempt rollback of previous steps
                self._rollback_steps(context, step_results)
                break

        duration = time.time() - start_time

        # Determine final status
        completed_count = sum(
            1 for r in step_results if r.status == StepStatus.COMPLETED
        )

        if completed_count == len(self.steps):
            status = WorkflowStatus.COMPLETED
            message = f"Export completed for {chat_name}"
            self._log_info(message)
        elif last_error:
            status = WorkflowStatus.FAILED
            message = f"Export failed for {chat_name}: {last_error.message if last_error else 'Unknown error'}"
        elif completed_count > 0:
            status = WorkflowStatus.PARTIALLY_COMPLETED
            message = f"Export partially completed for {chat_name}"
        else:
            status = WorkflowStatus.FAILED
            message = f"Export failed for {chat_name}"

        # Emit workflow completed event
        self._emit_progress(
            chat_name=chat_name,
            step_name="workflow",
            step_index=len(self.steps),
            status=status.name.lower(),
            message=message,
        )

        return WorkflowResult(
            status=status,
            chat_name=chat_name,
            message=message,
            steps_completed=completed_count,
            steps_total=len(self.steps),
            step_results=step_results,
            error=last_error,
            duration_seconds=duration,
        )

    def _rollback_steps(
        self,
        context: StepContext,
        step_results: List[StepResult],
    ) -> None:
        """
        Rollback completed steps in reverse order.

        Args:
            context: Step context
            step_results: Results of executed steps
        """
        self._log_debug("Attempting rollback of completed steps")

        for i in range(len(step_results) - 1, -1, -1):
            result = step_results[i]
            if result.status == StepStatus.COMPLETED:
                step = self.steps[i]
                try:
                    step.rollback(context)
                    self._log_debug(f"Rolled back step: {step.name}")
                except Exception as e:
                    self._log_debug(f"Rollback failed for {step.name}: {e}")

    def _emit_progress(
        self,
        chat_name: str,
        step_name: str,
        step_index: int,
        status: str,
        message: str,
    ) -> None:
        """Emit a progress event."""
        if self.event_bus:
            event = ExportProgressEvent(
                chat_name=chat_name,
                step_name=step_name,
                step_index=step_index,
                total_steps=len(self.steps),
                status=status,
                message=message,
            )
            self.event_bus.emit(event)
        else:
            emit(
                ExportProgressEvent(
                    chat_name=chat_name,
                    step_name=step_name,
                    step_index=step_index,
                    total_steps=len(self.steps),
                    status=status,
                    message=message,
                )
            )

    def _log_info(self, message: str) -> None:
        """Log an info message."""
        if self.logger:
            self.logger.info(message)

    def _log_debug(self, message: str) -> None:
        """Log a debug message."""
        if self.logger:
            if hasattr(self.logger, "debug_msg"):
                self.logger.debug_msg(message)
            else:
                self.logger.debug(message)

    def _log_error(self, message: str) -> None:
        """Log an error message."""
        if self.logger:
            self.logger.error(message)
