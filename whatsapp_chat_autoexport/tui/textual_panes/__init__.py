"""
Textual pane widgets for the MainScreen tabbed layout.

Each pane is a Container subclass that lives inside a TabPane.
"""

from .connect_pane import ConnectPane
from .discover_select_pane import DiscoverSelectPane

__all__ = ["ConnectPane", "DiscoverSelectPane"]
