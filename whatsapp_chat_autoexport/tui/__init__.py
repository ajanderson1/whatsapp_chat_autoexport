"""
TUI (Text User Interface) for WhatsApp Chat Auto-Export.

Provides:
- Interactive Textual-based terminal UI
- Pipeline stage navigation
- Real-time progress updates
- Screen-based navigation
"""

# Textual-based TUI
from .textual_app import WhatsAppExporterApp, PipelineStage
from .textual_widgets import (
    PipelineHeader,
    ChatListWidget,
    SettingsPanel,
    ActivityLog,
    QueueWidget,
    ProgressDisplay,
)
from .textual_screens import (
    DiscoveryScreen,
    SelectionScreen,
    HelpScreen,
)

__all__ = [
    # Main Textual app
    "WhatsAppExporterApp",
    "PipelineStage",
    # Textual Widgets
    "PipelineHeader",
    "ChatListWidget",
    "SettingsPanel",
    "ActivityLog",
    "QueueWidget",
    "ProgressDisplay",
    # Textual Screens
    "DiscoveryScreen",
    "SelectionScreen",
    "HelpScreen",
]
