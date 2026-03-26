"""
Protocol and ABC definitions for WhatsApp Chat Auto-Export.

Defines the interfaces that components must implement, enabling
dependency injection and testability.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, Optional, List, Dict, Any, runtime_checkable
from pathlib import Path
from enum import Enum, auto

from .result import Result
from .errors import ExportError


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
    data: Optional[Dict[str, Any]] = None
    error: Optional[ExportError] = None
    duration_seconds: float = 0.0

    @classmethod
    def success(cls, message: str = "Step completed", **data) -> "StepResult":
        return cls(status=StepStatus.COMPLETED, message=message, data=data if data else None)

    @classmethod
    def failed(cls, error: ExportError, message: str = "Step failed") -> "StepResult":
        return cls(status=StepStatus.FAILED, message=message, error=error)

    @classmethod
    def skipped(cls, reason: str) -> "StepResult":
        return cls(status=StepStatus.SKIPPED, message=reason)


@runtime_checkable
class ExportStep(Protocol):
    """
    Protocol for individual export workflow steps.

    Each step in the export workflow (open menu, click more, etc.)
    implements this interface.
    """

    name: str  # Human-readable step name
    description: str  # Detailed description

    def execute(self, context: Dict[str, Any]) -> StepResult:
        """
        Execute the step.

        Args:
            context: Shared context dictionary with driver, chat info, etc.

        Returns:
            StepResult indicating success, failure, or skip
        """
        ...

    def can_retry(self) -> bool:
        """Check if this step supports retrying on failure."""
        ...

    def rollback(self, context: Dict[str, Any]) -> bool:
        """
        Attempt to undo this step's effects.

        Returns True if rollback succeeded or was unnecessary.
        """
        ...

    def validate_preconditions(self, context: Dict[str, Any]) -> Result[bool, ExportError]:
        """
        Validate that preconditions for this step are met.

        Returns Ok(True) if ready, Err with reason if not.
        """
        ...


class PhaseStatus(Enum):
    """Status of a pipeline phase."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()


@dataclass
class PhaseResult:
    """Result of executing a pipeline phase."""

    status: PhaseStatus
    message: str
    items_processed: int = 0
    items_failed: int = 0
    items_skipped: int = 0
    data: Optional[Dict[str, Any]] = None
    errors: List[ExportError] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @classmethod
    def success(
        cls,
        message: str,
        items_processed: int = 0,
        **data,
    ) -> "PhaseResult":
        return cls(
            status=PhaseStatus.COMPLETED,
            message=message,
            items_processed=items_processed,
            data=data if data else None,
        )

    @classmethod
    def failed(cls, message: str, errors: List[ExportError]) -> "PhaseResult":
        return cls(
            status=PhaseStatus.FAILED,
            message=message,
            errors=errors,
        )


@runtime_checkable
class PipelinePhase(Protocol):
    """
    Protocol for pipeline processing phases.

    Each phase (download, extract, transcribe, build output)
    implements this interface.
    """

    name: str  # Phase name (e.g., "download", "transcribe")
    description: str  # Human-readable description

    def execute(self, context: Dict[str, Any]) -> PhaseResult:
        """
        Execute the phase.

        Args:
            context: Shared context with paths, settings, etc.

        Returns:
            PhaseResult with status and statistics
        """
        ...

    def estimate_work(self, context: Dict[str, Any]) -> int:
        """
        Estimate the number of items to process.

        Used for progress reporting.
        """
        ...

    def cleanup(self, context: Dict[str, Any]) -> None:
        """Clean up temporary files from this phase."""
        ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Protocol for transcription service providers."""

    name: str  # Provider name (e.g., "whisper", "elevenlabs")

    def transcribe(self, audio_path: Path, **kwargs) -> Result[str, ExportError]:
        """
        Transcribe an audio or video file.

        Args:
            audio_path: Path to the media file
            **kwargs: Provider-specific options

        Returns:
            Result with transcription text or error
        """
        ...

    def is_available(self) -> bool:
        """Check if the provider is configured and available."""
        ...

    def get_supported_formats(self) -> List[str]:
        """Get list of supported file extensions."""
        ...


@runtime_checkable
class DeviceConnector(Protocol):
    """Protocol for device connection handlers."""

    def connect(self, device_id: Optional[str] = None) -> Result[str, ExportError]:
        """
        Connect to a device.

        Args:
            device_id: Optional specific device to connect to

        Returns:
            Result with connected device ID or error
        """
        ...

    def disconnect(self) -> None:
        """Disconnect from the current device."""
        ...

    def is_connected(self) -> bool:
        """Check if currently connected to a device."""
        ...

    def list_devices(self) -> List[str]:
        """List available devices."""
        ...

    def get_device_info(self) -> Optional[Dict[str, str]]:
        """Get information about the connected device."""
        ...


@dataclass
class ElementLocator:
    """Specification for locating a UI element."""

    strategy: str  # e.g., "id", "xpath", "text", "content_desc"
    value: str  # The locator value
    timeout: float = 5.0  # Wait timeout in seconds
    priority: int = 1  # Lower = higher priority


@runtime_checkable
class ElementFinder(Protocol):
    """Protocol for UI element finding strategies."""

    def find(
        self,
        locators: List[ElementLocator],
        wait_visible: bool = True,
    ) -> Result[Any, ExportError]:
        """
        Find an element using multiple locator strategies.

        Tries locators in priority order until one succeeds.

        Args:
            locators: List of locator strategies to try
            wait_visible: Whether to wait for element to be visible

        Returns:
            Result with found element or error
        """
        ...

    def find_all(
        self,
        locators: List[ElementLocator],
    ) -> Result[List[Any], ExportError]:
        """
        Find all matching elements.

        Args:
            locators: List of locator strategies to try

        Returns:
            Result with list of found elements or error
        """
        ...

    def is_present(
        self,
        locators: List[ElementLocator],
        timeout: float = 1.0,
    ) -> bool:
        """
        Check if an element is present without raising errors.

        Args:
            locators: List of locator strategies to try
            timeout: How long to wait

        Returns:
            True if element found, False otherwise
        """
        ...


@runtime_checkable
class StateObserver(Protocol):
    """Protocol for observing state changes."""

    def on_state_change(self, old_state: str, new_state: str, data: Dict[str, Any]) -> None:
        """Called when state changes."""
        ...

    def on_progress(self, current: int, total: int, message: str) -> None:
        """Called to report progress."""
        ...

    def on_error(self, error: ExportError) -> None:
        """Called when an error occurs."""
        ...


class Logger(ABC):
    """Abstract base class for logging implementations."""

    @abstractmethod
    def info(self, message: str) -> None:
        """Log an informational message."""
        ...

    @abstractmethod
    def success(self, message: str) -> None:
        """Log a success message."""
        ...

    @abstractmethod
    def warning(self, message: str) -> None:
        """Log a warning message."""
        ...

    @abstractmethod
    def error(self, message: str) -> None:
        """Log an error message."""
        ...

    @abstractmethod
    def debug(self, message: str) -> None:
        """Log a debug message."""
        ...


class ConfigProvider(ABC):
    """Abstract base class for configuration providers."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        ...

    @abstractmethod
    def get_selectors(self, name: str) -> List[ElementLocator]:
        """Get selectors for a named element."""
        ...

    @abstractmethod
    def get_timeout(self, operation: str) -> float:
        """Get timeout for an operation."""
        ...
