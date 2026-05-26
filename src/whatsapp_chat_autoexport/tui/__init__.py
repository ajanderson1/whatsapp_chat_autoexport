"""
TUI (Text User Interface) for WhatsApp Chat Auto-Export.

Provides:
- Interactive Textual-based terminal UI
- Tab-based navigation (Connect, Select, Export, Summary)
- Real-time progress updates
"""

# Textual-based TUI
from .textual_app import PipelineStage, WhatsAppExporterApp
from .textual_screens import (
    HelpScreen,
    MainScreen,
)
from .textual_widgets import (
    ActivityLog,
    ChatListWidget,
    ProgressDisplay,
    QueueWidget,
    SettingsPanel,
)

__all__ = [
    # Main Textual app
    "WhatsAppExporterApp",
    "PipelineStage",
    # Textual Widgets
    "ChatListWidget",
    "SettingsPanel",
    "ActivityLog",
    "QueueWidget",
    "ProgressDisplay",
    # Textual Screens
    "MainScreen",
    "HelpScreen",
]
