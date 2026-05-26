"""
Core abstractions for WhatsApp Chat Auto-Export.

This package provides the foundational types, interfaces, and patterns
used throughout the application.
"""

from .errors import (
    AppStateError,
    DeviceConnectionError,
    ElementNotFoundError,
    ErrorCategory,
    ErrorSeverity,
    ExportError,
    ExportWorkflowError,
    PipelineError,
    RecoveryHint,
    TranscriptionError,
)
from .events import (
    ErrorEvent,
    Event,
    EventBus,
    EventType,
    ExportProgressEvent,
    PipelineProgressEvent,
    StateChangeEvent,
)
from .interfaces import (
    DeviceConnector,
    ElementFinder,
    ExportStep,
    PipelinePhase,
    StateObserver,
    TranscriptionProvider,
)
from .result import Err, Ok, Result

__all__ = [
    # Errors
    "ErrorCategory",
    "ErrorSeverity",
    "ExportError",
    "RecoveryHint",
    "DeviceConnectionError",
    "AppStateError",
    "ElementNotFoundError",
    "ExportWorkflowError",
    "TranscriptionError",
    "PipelineError",
    # Result type
    "Result",
    "Ok",
    "Err",
    # Interfaces
    "ExportStep",
    "PipelinePhase",
    "TranscriptionProvider",
    "DeviceConnector",
    "ElementFinder",
    "StateObserver",
    # Events
    "Event",
    "EventType",
    "EventBus",
    "StateChangeEvent",
    "ExportProgressEvent",
    "PipelineProgressEvent",
    "ErrorEvent",
]
