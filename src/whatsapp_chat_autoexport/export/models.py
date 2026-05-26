"""
Data models for the export layer.

Lightweight transport types used during chat collection and discovery.
These are plain dataclasses (not Pydantic) to keep the driver layer
independent of the state layer's serialization framework.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatMetadata:
    """
    Metadata for a single chat row discovered during collection.

    Carries the chat name plus optional metadata extracted from
    WhatsApp's XML page source. All fields except `name` default
    to None/False so callers can create minimal instances with
    just a name.
    """

    name: str
    timestamp: Optional[str] = None
    message_preview: Optional[str] = None
    is_muted: bool = False
    is_group: bool = False
    group_sender: Optional[str] = None
    has_type_indicator: bool = False
    photo_description: Optional[str] = None

    def __str__(self) -> str:
        return self.name
