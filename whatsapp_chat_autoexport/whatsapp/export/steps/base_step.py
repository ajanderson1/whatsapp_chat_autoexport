"""
Base class for export workflow steps.

Provides the interface and common functionality for all export steps.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional
import time

from ....core.result import Result, Ok, Err
from ....core.errors import ExportError, ExportWorkflowError, ErrorCategory
from ....automation.elements import ElementFinder
from ....config.timeouts import TimeoutConfig, get_timeout_config


class StepStatus(Enum):
    """Status of an export step."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()
    RETRYING = auto()


@dataclass
class StepResult:
    """Result of executing an export step."""

    status: StepStatus
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ExportError] = None
    duration_seconds: float = 0.0
    attempts: int = 1

    @classmethod
    def success(cls, message: str = "Step completed", **data) -> "StepResult":
        """Create a success result."""
        return cls(status=StepStatus.COMPLETED, message=message, data=data)

    @classmethod
    def failed(cls, error: ExportError, message: str = "Step failed") -> "StepResult":
        """Create a failure result."""
        return cls(status=StepStatus.FAILED, message=message, error=error)

    @classmethod
    def skipped(cls, reason: str) -> "StepResult":
        """Create a skipped result."""
        return cls(status=StepStatus.SKIPPED, message=reason)


@dataclass
class StepContext:
    """
    Shared context passed between export steps.

    Contains the driver, element finder, chat information, and
    configuration for the export process.
    """

    # Core automation components
    driver: Any  # Appium WebDriver
    element_finder: ElementFinder

    # Chat being exported
    chat_name: str = ""
    chat_index: int = 0

    # Export configuration
    include_media: bool = True
    timeout_seconds: float = 5.0

    # State tracking
    current_step: str = ""
    steps_completed: int = 0
    total_steps: int = 6

    # Additional data from previous steps
    step_data: Dict[str, Any] = field(default_factory=dict)

    # Timeout configuration
    timeout_config: TimeoutConfig = field(default_factory=get_timeout_config)

    # Logger
    logger: Any = None

    def log_info(self, message: str) -> None:
        """Log an info message."""
        if self.logger:
            self.logger.info(message)

    def log_debug(self, message: str) -> None:
        """Log a debug message."""
        if self.logger:
            if hasattr(self.logger, "debug_msg"):
                self.logger.debug_msg(message)
            else:
                self.logger.debug(message)

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        if self.logger:
            self.logger.warning(message)

    def log_error(self, message: str) -> None:
        """Log an error message."""
        if self.logger:
            self.logger.error(message)


class BaseExportStep(ABC):
    """
    Abstract base class for export workflow steps.

    Each step implements:
    - execute(): Main step logic
    - can_retry(): Whether retry is supported
    - rollback(): Attempt to undo step effects
    - validate_preconditions(): Check if step can run
    """

    # Step metadata
    name: str = "base_step"
    description: str = "Base export step"
    step_index: int = 0

    # Retry configuration
    max_retries: int = 2
    retry_delay_seconds: float = 1.0

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the step.

        Args:
            config: Optional step-specific configuration
        """
        self.config = config or {}

    @abstractmethod
    def execute(self, context: StepContext) -> StepResult:
        """
        Execute the step.

        Args:
            context: Shared context with driver, chat info, etc.

        Returns:
            StepResult indicating success, failure, or skip
        """
        pass

    def can_retry(self) -> bool:
        """
        Check if this step supports retrying on failure.

        Returns:
            True if retry is supported
        """
        return self.max_retries > 0

    def rollback(self, context: StepContext) -> bool:
        """
        Attempt to undo this step's effects.

        Default implementation returns True (no rollback needed).

        Args:
            context: Shared context

        Returns:
            True if rollback succeeded or was unnecessary
        """
        return True

    def validate_preconditions(
        self, context: StepContext
    ) -> Result[bool, ExportError]:
        """
        Validate that preconditions for this step are met.

        Default implementation always returns Ok(True).

        Args:
            context: Shared context

        Returns:
            Ok(True) if ready, Err with reason if not
        """
        return Ok(True)

    def execute_with_retry(self, context: StepContext) -> StepResult:
        """
        Execute the step with retry logic.

        Args:
            context: Shared context

        Returns:
            StepResult after retries exhausted or success
        """
        start_time = time.time()
        last_result = None
        attempts = 0

        while attempts <= self.max_retries:
            attempts += 1
            context.log_debug(f"Executing {self.name} (attempt {attempts})")

            try:
                result = self.execute(context)

                if result.status == StepStatus.COMPLETED:
                    result.duration_seconds = time.time() - start_time
                    result.attempts = attempts
                    return result

                if result.status == StepStatus.SKIPPED:
                    result.duration_seconds = time.time() - start_time
                    result.attempts = attempts
                    return result

                last_result = result

                if not self.can_retry() or attempts > self.max_retries:
                    break

                context.log_debug(
                    f"Step {self.name} failed, retrying in {self.retry_delay_seconds}s"
                )
                time.sleep(self.retry_delay_seconds)

            except Exception as e:
                error = ExportWorkflowError(
                    message=f"Step {self.name} raised exception: {e}",
                    step_name=self.name,
                    chat_name=context.chat_name,
                    cause=e,
                )
                last_result = StepResult.failed(error)

                if not self.can_retry() or attempts > self.max_retries:
                    break

                context.log_debug(f"Step {self.name} raised exception, retrying")
                time.sleep(self.retry_delay_seconds)

        if last_result:
            last_result.duration_seconds = time.time() - start_time
            last_result.attempts = attempts
            return last_result

        return StepResult.failed(
            ExportWorkflowError(
                message=f"Step {self.name} failed with no result",
                step_name=self.name,
                chat_name=context.chat_name,
            )
        )
