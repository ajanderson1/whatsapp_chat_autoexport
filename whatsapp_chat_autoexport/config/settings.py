"""
Pydantic settings models for WhatsApp Chat Auto-Export.

Provides type-safe configuration with validation and environment
variable support.
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeviceConfig(BaseModel):
    """Configuration for device connection."""

    # Connection settings
    connection_type: Literal["usb", "wireless"] = "usb"
    wireless_ip: Optional[str] = None
    wireless_port: int = 5555
    pairing_port: Optional[int] = None

    # ADB settings
    adb_path: Optional[str] = None
    adb_timeout: int = 30

    # Appium settings
    appium_host: str = "127.0.0.1"
    appium_port: int = 4723
    appium_auto_start: bool = True

    # Device capabilities
    device_name: str = "Android"
    platform_name: str = "Android"
    platform_version: Optional[str] = None
    udid: Optional[str] = None
    no_reset: bool = True
    full_reset: bool = False
    auto_grant_permissions: bool = True


class ExportConfig(BaseModel):
    """Configuration for WhatsApp export process."""

    # Export settings
    include_media: bool = True
    limit: Optional[int] = None
    resume_enabled: bool = False
    resume_directory: Optional[Path] = None

    # Chat selection
    skip_community_chats: bool = True
    skip_broadcast_lists: bool = True
    chat_filter_pattern: Optional[str] = None

    # Retry behavior
    max_retries_per_chat: int = 2
    retry_delay_seconds: float = 2.0
    max_scroll_attempts: int = 240

    # Timing
    step_delay_seconds: float = 0.5
    animation_wait_seconds: float = 1.0
    long_press_duration_ms: int = 500

    # Checkpointing
    checkpoint_enabled: bool = True
    checkpoint_directory: Optional[Path] = None
    checkpoint_interval: int = 5  # Save every N chats

    # Google Drive
    google_drive_timeout: int = 60
    wait_for_upload: bool = True

    @field_validator("resume_directory", "checkpoint_directory", mode="before")
    @classmethod
    def expand_path(cls, v):
        if v is None:
            return v
        path = Path(v).expanduser()
        return path


class TranscriptionConfig(BaseModel):
    """Configuration for audio/video transcription."""

    # Provider settings
    provider: Literal["whisper", "elevenlabs"] = "whisper"
    api_key: Optional[str] = None

    # Whisper settings
    whisper_model: str = "whisper-1"

    # ElevenLabs settings
    elevenlabs_model: str = "scribe_v1"

    # Processing settings
    force_transcribe: bool = False
    skip_existing: bool = True
    max_concurrent: int = 3
    timeout_seconds: int = 300

    # Supported formats
    audio_formats: list[str] = Field(
        default=[".opus", ".m4a", ".mp3", ".wav", ".ogg", ".aac"]
    )
    video_formats: list[str] = Field(default=[".mp4", ".mov", ".avi", ".webm"])


class PipelineConfig(BaseModel):
    """Configuration for the processing pipeline."""

    # Phase control
    skip_download: bool = False
    skip_extraction: bool = False
    skip_transcription: bool = False
    skip_output_build: bool = False

    # Output settings
    copy_media: bool = True
    include_transcriptions: bool = True
    merge_transcripts: bool = True

    # Google Drive settings
    delete_from_drive: bool = False
    cleanup_drive_duplicates: bool = True
    drive_folder_name: str = "WhatsApp"

    # Paths
    temp_directory: Optional[Path] = None
    output_directory: Path = Field(
        default=Path("/Users/ajanderson/Journal/People/Correspondence/Whatsapp")
    )

    # Cleanup
    cleanup_temp_files: bool = True
    keep_archives: bool = False

    @field_validator("temp_directory", "output_directory", mode="before")
    @classmethod
    def expand_path(cls, v):
        if v is None:
            return v
        return Path(v).expanduser()


class TUIConfig(BaseModel):
    """Configuration for the TUI interface."""

    # Display settings
    show_progress_bar: bool = True
    show_queue_panel: bool = True
    show_log_panel: bool = True
    refresh_rate: float = 0.1  # seconds

    # Colors (Rich color names)
    success_color: str = "green"
    warning_color: str = "yellow"
    error_color: str = "red"
    info_color: str = "blue"

    # Keybindings
    pause_key: str = "space"
    quit_key: str = "q"
    retry_key: str = "r"
    skip_key: str = "s"

    # Log settings
    max_log_lines: int = 100
    log_timestamps: bool = True


class LoggingConfig(BaseModel):
    """Configuration for file logging."""

    # File logging settings
    log_dir: Optional[Path] = None  # Default: project_root/.logs/
    log_file_enabled: bool = True
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    max_size_mb: int = 10  # Maximum size per log file in MB
    backup_count: int = 5  # Number of backup files to keep

    @field_validator("log_dir", mode="before")
    @classmethod
    def expand_log_dir(cls, v):
        if v is None:
            return v
        return Path(v).expanduser()


class AppConfig(BaseSettings):
    """Root application configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="WHATSAPP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    transcription: TranscriptionConfig = Field(default_factory=TranscriptionConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    tui: TUIConfig = Field(default_factory=TUIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Global settings
    debug: bool = False
    dry_run: bool = False
    verbose: bool = False
    selectors_path: Optional[Path] = None

    @field_validator("selectors_path", mode="before")
    @classmethod
    def expand_selectors_path(cls, v):
        if v is None:
            # Default to selectors directory in package
            return Path(__file__).parent / "selectors"
        return Path(v).expanduser()


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def load_config(
    config_file: Optional[Path] = None,
    **overrides,
) -> AppConfig:
    """
    Load configuration from file and/or overrides.

    Args:
        config_file: Optional YAML/JSON config file path
        **overrides: Direct configuration overrides

    Returns:
        Configured AppConfig instance
    """
    global _config

    if config_file and config_file.exists():
        import yaml

        with open(config_file) as f:
            file_config = yaml.safe_load(f)
        _config = AppConfig(**{**file_config, **overrides})
    else:
        _config = AppConfig(**overrides)

    return _config


def reset_config() -> None:
    """Reset the global configuration (mainly for testing)."""
    global _config
    _config = None
