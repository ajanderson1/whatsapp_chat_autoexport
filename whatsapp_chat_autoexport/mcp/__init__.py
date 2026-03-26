"""
MCP bridge integration for WhatsApp Chat Auto-Export.

Provides direct SQLite access to the WhatsApp MCP bridge database,
incremental sync state management, and contact resolution.
"""

from .bridge_reader import BridgeReader
from .state import MCPState

__all__ = [
    "BridgeReader",
    "MCPState",
]
