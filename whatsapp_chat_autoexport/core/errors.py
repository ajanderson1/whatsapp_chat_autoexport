"""
Structured error types for WhatsApp Chat Auto-Export.

Provides a hierarchical error system with:
- Error categories for classification
- Severity levels for prioritization
- Recovery hints for self-healing behavior
- Specific error types for different failure modes
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, List
from datetime import datetime


class ErrorCategory(Enum):
    """Categories of errors that can occur during export."""

    # Device and connection errors
    CONNECTION = auto()  # ADB connection failures
    DEVICE_DISCONNECTED = auto()  # Device went offline
    DEVICE_LOCKED = auto()  # Phone screen is locked

    # Application state errors
    APP_STATE = auto()  # WhatsApp not in expected state
    APP_NOT_FOUND = auto()  # WhatsApp not installed
    APP_CRASHED = auto()  # WhatsApp crashed during operation

    # UI automation errors
    ELEMENT_NOT_FOUND = auto()  # UI element not found
    ELEMENT_NOT_CLICKABLE = auto()  # Element found but not interactable
    ELEMENT_STALE = auto()  # Element reference became invalid
    SCREEN_CHANGED = auto()  # Unexpected screen transition

    # Export workflow errors
    MENU_NAVIGATION = auto()  # Failed to open menu
    EXPORT_OPTION_MISSING = auto()  # Export option not available
    MEDIA_SELECTION = auto()  # Failed to select media option
    DRIVE_SELECTION = auto()  # Failed to select Google Drive
    UPLOAD_FAILED = auto()  # Upload to Drive failed

    # Chat-specific errors
    CHAT_NOT_FOUND = auto()  # Chat not found in list
    CHAT_NOT_EXPORTABLE = auto()  # Community chat, etc.
    PRIVACY_RESTRICTION = auto()  # Advanced privacy enabled

    # Transcription errors
    TRANSCRIPTION_API = auto()  # API call failed
    AUDIO_FORMAT = auto()  # Unsupported audio format
    AUDIO_EXTRACTION = auto()  # Failed to extract audio from video

    # Pipeline errors
    DOWNLOAD_FAILED = auto()  # Google Drive download failed
    EXTRACTION_FAILED = auto()  # ZIP extraction failed
    OUTPUT_BUILD = auto()  # Failed to build output

    # System errors
    TIMEOUT = auto()  # Operation timed out
    PERMISSION_DENIED = auto()  # Insufficient permissions
    DISK_FULL = auto()  # No disk space
    UNKNOWN = auto()  # Unexpected error


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    DEBUG = auto()  # Informational, no action needed
    WARNING = auto()  # Non-fatal, operation can continue
    ERROR = auto()  # Operation failed, but recovery possible
    CRITICAL = auto()  # Unrecoverable, session must end
    FATAL = auto()  # System-level failure


@dataclass
class RecoveryHint:
    """Suggestions for recovering from an error."""

    action: str  # What to do (e.g., "retry", "skip", "reconnect")
    description: str  # Human-readable description
    auto_recoverable: bool = False  # Can the system try this automatically?
    max_retries: int = 0  # How many times to retry (0 = don't retry)
    retry_delay_seconds: float = 1.0  # Delay between retries
    requires_user_action: bool = False  # Does user need to do something?
    user_instruction: Optional[str] = None  # Instructions for user

    @classmethod
    def retry(
        cls, max_retries: int = 3, delay: float = 1.0, description: str = "Retry the operation"
    ) -> "RecoveryHint":
        """Create a retry hint."""
        return cls(
            action="retry",
            description=description,
            auto_recoverable=True,
            max_retries=max_retries,
            retry_delay_seconds=delay,
        )

    @classmethod
    def skip(cls, description: str = "Skip this item and continue") -> "RecoveryHint":
        """Create a skip hint."""
        return cls(
            action="skip",
            description=description,
            auto_recoverable=True,
        )

    @classmethod
    def reconnect(cls, description: str = "Reconnect to device") -> "RecoveryHint":
        """Create a reconnect hint."""
        return cls(
            action="reconnect",
            description=description,
            auto_recoverable=True,
            max_retries=3,
            retry_delay_seconds=5.0,
        )

    @classmethod
    def user_action(cls, instruction: str) -> "RecoveryHint":
        """Create a hint requiring user action."""
        return cls(
            action="user_action",
            description=instruction,
            requires_user_action=True,
            user_instruction=instruction,
        )

    @classmethod
    def abort(cls, reason: str = "Cannot recover from this error") -> "RecoveryHint":
        """Create an abort hint."""
        return cls(
            action="abort",
            description=reason,
        )


@dataclass
class ExportError(Exception):
    """
    Base error class for all export-related errors.

    Provides structured error information including category, severity,
    context, and recovery hints.
    """

    category: ErrorCategory
    message: str
    severity: ErrorSeverity = ErrorSeverity.ERROR
    context: Dict[str, Any] = field(default_factory=dict)
    recovery_hints: List[RecoveryHint] = field(default_factory=list)
    cause: Optional[Exception] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize the exception with message."""
        super().__init__(self.message)

    def __str__(self) -> str:
        """Format error as string."""
        parts = [f"[{self.category.name}] {self.message}"]
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        if self.recovery_hints:
            hints = [h.description for h in self.recovery_hints]
            parts.append(f"Recovery: {'; '.join(hints)}")
        return " | ".join(parts)

    def with_context(self, **kwargs) -> "ExportError":
        """Add context to the error and return self for chaining."""
        self.context.update(kwargs)
        return self

    def with_hint(self, hint: RecoveryHint) -> "ExportError":
        """Add a recovery hint and return self for chaining."""
        self.recovery_hints.append(hint)
        return self

    def can_auto_recover(self) -> bool:
        """Check if any recovery hint allows automatic recovery."""
        return any(h.auto_recoverable for h in self.recovery_hints)

    def get_auto_recovery_hint(self) -> Optional[RecoveryHint]:
        """Get the first auto-recoverable hint, if any."""
        for hint in self.recovery_hints:
            if hint.auto_recoverable:
                return hint
        return None


# Specific error types for common scenarios


@dataclass
class DeviceConnectionError(ExportError):
    """Error connecting to or communicating with the Android device."""

    def __init__(
        self,
        message: str,
        device_id: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            category=ErrorCategory.CONNECTION,
            message=message,
            severity=ErrorSeverity.CRITICAL,
            context={"device_id": device_id} if device_id else {},
            recovery_hints=[
                RecoveryHint.reconnect("Check USB connection and try again"),
                RecoveryHint.user_action("Ensure USB debugging is enabled on device"),
            ],
            cause=cause,
        )


@dataclass
class AppStateError(ExportError):
    """Error with WhatsApp application state."""

    def __init__(
        self,
        message: str,
        expected_state: Optional[str] = None,
        actual_state: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        context = {}
        if expected_state:
            context["expected"] = expected_state
        if actual_state:
            context["actual"] = actual_state

        super().__init__(
            category=ErrorCategory.APP_STATE,
            message=message,
            severity=ErrorSeverity.ERROR,
            context=context,
            recovery_hints=[
                RecoveryHint.retry(3, 2.0, "Restart WhatsApp and retry"),
            ],
            cause=cause,
        )


@dataclass
class ElementNotFoundError(ExportError):
    """Error when a UI element cannot be found."""

    def __init__(
        self,
        message: str,
        element_name: str,
        strategies_tried: Optional[List[str]] = None,
        screen_context: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        context = {"element": element_name}
        if strategies_tried:
            context["strategies"] = strategies_tried
        if screen_context:
            context["screen"] = screen_context

        super().__init__(
            category=ErrorCategory.ELEMENT_NOT_FOUND,
            message=message,
            severity=ErrorSeverity.ERROR,
            context=context,
            recovery_hints=[
                RecoveryHint.retry(2, 1.0, "Wait and retry finding element"),
                RecoveryHint.skip("Skip this operation if element is optional"),
            ],
            cause=cause,
        )


@dataclass
class ExportWorkflowError(ExportError):
    """Error during the export workflow."""

    def __init__(
        self,
        message: str,
        step_name: str,
        chat_name: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        context = {"step": step_name}
        if chat_name:
            context["chat"] = chat_name

        super().__init__(
            category=ErrorCategory.MENU_NAVIGATION,
            message=message,
            severity=ErrorSeverity.ERROR,
            context=context,
            recovery_hints=[
                RecoveryHint.retry(2, 1.0, "Retry the export step"),
                RecoveryHint.skip("Skip this chat and continue with next"),
            ],
            cause=cause,
        )


@dataclass
class TranscriptionError(ExportError):
    """Error during audio/video transcription."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        provider: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        context = {}
        if file_path:
            context["file"] = file_path
        if provider:
            context["provider"] = provider

        super().__init__(
            category=ErrorCategory.TRANSCRIPTION_API,
            message=message,
            severity=ErrorSeverity.WARNING,
            context=context,
            recovery_hints=[
                RecoveryHint.retry(2, 5.0, "Retry API call after delay"),
                RecoveryHint.skip("Skip transcription for this file"),
            ],
            cause=cause,
        )


@dataclass
class PipelineError(ExportError):
    """Error during pipeline processing."""

    def __init__(
        self,
        message: str,
        phase: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            category=ErrorCategory.DOWNLOAD_FAILED,
            message=message,
            severity=ErrorSeverity.ERROR,
            context={"phase": phase},
            recovery_hints=[
                RecoveryHint.retry(3, 2.0, "Retry the pipeline phase"),
            ],
            cause=cause,
        )
