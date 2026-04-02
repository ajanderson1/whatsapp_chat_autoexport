"""
TUI (Text User Interface) for WhatsApp Chat Auto-Export.

Provides:
- Interactive Textual-based terminal UI
- Tab-based navigation (Connect, Discover & Select, Export, Summary)
- Real-time progress updates
"""

# Textual-based TUI
from .textual_app import WhatsAppExporterApp, PipelineStage
from .textual_widgets import (
    ChatListWidget,
    SettingsPanel,
    ActivityLog,
    QueueWidget,
    ProgressDisplay,
)
from .textual_screens import (
    MainScreen,
    HelpScreen,
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
