"""
Core abstractions for WhatsApp Chat Auto-Export.

This package provides the foundational types, interfaces, and patterns
used throughout the application.
"""

from .errors import (
    ErrorCategory,
    ErrorSeverity,
    ExportError,
    RecoveryHint,
    DeviceConnectionError,
    AppStateError,
    ElementNotFoundError,
    ExportWorkflowError,
    TranscriptionError,
    PipelineError,
)
from .result import Result, Ok, Err
from .interfaces import (
    ExportStep,
    PipelinePhase,
    TranscriptionProvider,
    DeviceConnector,
    ElementFinder,
    StateObserver,
)
from .events import (
    Event,
    EventType,
    EventBus,
    StateChangeEvent,
    ExportProgressEvent,
    PipelineProgressEvent,
    ErrorEvent,
)

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
