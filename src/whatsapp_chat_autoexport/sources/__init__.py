"""
Sources module for WhatsApp Chat Auto-Export.

Provides data source abstractions so the pipeline can accept messages
from Appium exports, existing vault transcripts, or the MCP bridge
without coupling to any single input format.
"""

from .base import MessageSource, ChatInfo
from .appium_source import AppiumSource
from .transcript_source import TranscriptSource

__all__ = [
    "MessageSource",
    "ChatInfo",
    "AppiumSource",
    "TranscriptSource",
]
