"""
Timing profiles for UI automation.

Provides configurable timeouts and delays for different operations
and device performance profiles.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class TimeoutProfile(Enum):
    """Predefined timeout profiles for different scenarios."""

    FAST = "fast"  # Fast device, stable connection
    NORMAL = "normal"  # Default settings
    SLOW = "slow"  # Slower device or unstable connection
    DEBUG = "debug"  # Extended timeouts for debugging


@dataclass
class TimeoutConfig:
    """Configuration for operation timeouts and delays."""

    # Element finding
    element_find_timeout: float = 5.0
    element_visible_timeout: float = 3.0
    element_clickable_timeout: float = 3.0

    # Screen transitions
    screen_transition_wait: float = 1.0
    animation_complete_wait: float = 0.5

    # Step delays
    step_delay: float = 0.5
    between_chats_delay: float = 1.0

    # Scroll operations
    scroll_delay: float = 0.3
    scroll_settle_time: float = 0.5

    # Long operations
    export_timeout: float = 120.0
    upload_timeout: float = 60.0
    app_launch_timeout: float = 30.0

    # Retry delays
    retry_delay: float = 2.0
    reconnect_delay: float = 5.0

    # User interaction
    long_press_duration: float = 0.5
    tap_duration: float = 0.1
    swipe_duration: float = 0.3

    @classmethod
    def for_profile(cls, profile: TimeoutProfile) -> "TimeoutConfig":
        """Get timeout configuration for a profile."""
        if profile == TimeoutProfile.FAST:
            return cls(
                element_find_timeout=3.0,
                element_visible_timeout=2.0,
                element_clickable_timeout=2.0,
                screen_transition_wait=0.5,
                animation_complete_wait=0.3,
                step_delay=0.3,
                between_chats_delay=0.5,
                scroll_delay=0.2,
                scroll_settle_time=0.3,
            )
        elif profile == TimeoutProfile.SLOW:
            return cls(
                element_find_timeout=10.0,
                element_visible_timeout=8.0,
                element_clickable_timeout=8.0,
                screen_transition_wait=2.0,
                animation_complete_wait=1.0,
                step_delay=1.0,
                between_chats_delay=2.0,
                scroll_delay=0.5,
                scroll_settle_time=1.0,
                export_timeout=300.0,
                upload_timeout=120.0,
            )
        elif profile == TimeoutProfile.DEBUG:
            return cls(
                element_find_timeout=15.0,
                element_visible_timeout=10.0,
                element_clickable_timeout=10.0,
                screen_transition_wait=3.0,
                animation_complete_wait=2.0,
                step_delay=2.0,
                between_chats_delay=3.0,
                scroll_delay=1.0,
                scroll_settle_time=2.0,
                export_timeout=600.0,
                upload_timeout=300.0,
                retry_delay=5.0,
            )
        else:  # NORMAL
            return cls()

    def scale(self, factor: float) -> "TimeoutConfig":
        """Return a new config with all timeouts scaled by a factor."""
        return TimeoutConfig(
            element_find_timeout=self.element_find_timeout * factor,
            element_visible_timeout=self.element_visible_timeout * factor,
            element_clickable_timeout=self.element_clickable_timeout * factor,
            screen_transition_wait=self.screen_transition_wait * factor,
            animation_complete_wait=self.animation_complete_wait * factor,
            step_delay=self.step_delay * factor,
            between_chats_delay=self.between_chats_delay * factor,
            scroll_delay=self.scroll_delay * factor,
            scroll_settle_time=self.scroll_settle_time * factor,
            export_timeout=self.export_timeout * factor,
            upload_timeout=self.upload_timeout * factor,
            app_launch_timeout=self.app_launch_timeout * factor,
            retry_delay=self.retry_delay * factor,
            reconnect_delay=self.reconnect_delay * factor,
            long_press_duration=self.long_press_duration,  # Keep interaction times
            tap_duration=self.tap_duration,
            swipe_duration=self.swipe_duration,
        )


# Global timeout configuration
_timeout_config: Optional[TimeoutConfig] = None


def get_timeout_config() -> TimeoutConfig:
    """Get the global timeout configuration."""
    global _timeout_config
    if _timeout_config is None:
        _timeout_config = TimeoutConfig()
    return _timeout_config


def set_timeout_profile(profile: TimeoutProfile) -> None:
    """Set the global timeout profile."""
    global _timeout_config
    _timeout_config = TimeoutConfig.for_profile(profile)


def get_timeout(operation: str) -> float:
    """
    Get timeout for a specific operation.

    Args:
        operation: Name of the operation (e.g., "element_find", "upload")

    Returns:
        Timeout in seconds
    """
    config = get_timeout_config()

    # Map common operation names to config attributes
    timeout_map: Dict[str, str] = {
        "element": "element_find_timeout",
        "element_find": "element_find_timeout",
        "find": "element_find_timeout",
        "visible": "element_visible_timeout",
        "clickable": "element_clickable_timeout",
        "transition": "screen_transition_wait",
        "animation": "animation_complete_wait",
        "step": "step_delay",
        "scroll": "scroll_delay",
        "export": "export_timeout",
        "upload": "upload_timeout",
        "launch": "app_launch_timeout",
        "retry": "retry_delay",
        "reconnect": "reconnect_delay",
        "long_press": "long_press_duration",
        "tap": "tap_duration",
        "swipe": "swipe_duration",
    }

    attr_name = timeout_map.get(operation.lower())
    if attr_name:
        return getattr(config, attr_name)

    # Try direct attribute access
    if hasattr(config, operation):
        return getattr(config, operation)

    # Default fallback
    return config.element_find_timeout


def reset_timeout_config() -> None:
    """Reset the global timeout configuration (mainly for testing)."""
    global _timeout_config
    _timeout_config = None
