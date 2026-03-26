"""
CLI module for WhatsApp Chat Auto-Export.

Provides a unified command-line interface with:
- export: Export chats from WhatsApp
- process: Process exported files
- wizard: Interactive step-by-step mode
"""

from .main import main, app

__all__ = [
    "main",
    "app",
]
