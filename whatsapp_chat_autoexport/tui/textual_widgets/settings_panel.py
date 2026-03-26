"""
Settings panel widget with toggle options and configurable settings.

Displays export settings with:
- Checkboxes for include media, transcribe audio, delete from Drive
- Output folder input
- Transcription provider selection
- API key configuration with validation status
"""

from pathlib import Path
from typing import Optional, List

from textual.app import ComposeResult
from textual.events import Key
from textual.widget import Widget
from textual.widgets import Static, Checkbox, Input, Label, RadioButton, RadioSet
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.reactive import reactive


# Default output directory
DEFAULT_OUTPUT_DIR = str(Path.home() / "whatsapp_exports")


class SettingsPanel(Widget):
    """
    Settings panel with toggle checkboxes and configuration inputs.

    Displays configurable export options including:
    - Export toggles (include media, transcribe audio, delete from Drive)
    - Output folder path
    - Transcription provider selection
    - API key configuration
    """

    DEFAULT_CSS = """
    SettingsPanel {
        border: solid $primary;
        padding: 1;
        height: 100%;
        overflow-y: auto;
    }
    """

    # Settings values - basic toggles
    include_media: reactive[bool] = reactive(True)
    transcribe_audio: reactive[bool] = reactive(True)
    delete_from_drive: reactive[bool] = reactive(False)

    # New settings
    output_folder: reactive[str] = reactive(DEFAULT_OUTPUT_DIR)
    transcription_provider: reactive[str] = reactive("whisper")

    class SettingsChanged(Message):
        """Message sent when settings change."""

        def __init__(
            self,
            include_media: bool,
            transcribe_audio: bool,
            delete_from_drive: bool,
            output_folder: str = "",
            transcription_provider: str = "whisper",
        ) -> None:
            self.include_media = include_media
            self.transcribe_audio = transcribe_audio
            self.delete_from_drive = delete_from_drive
            self.output_folder = output_folder
            self.transcription_provider = transcription_provider
            super().__init__()

    def __init__(
        self,
        include_media: bool = True,
        transcribe_audio: bool = True,
        delete_from_drive: bool = False,
        output_folder: str = DEFAULT_OUTPUT_DIR,
        transcription_provider: str = "whisper",
        locked: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize the settings panel.

        Args:
            include_media: Initial value for include media
            transcribe_audio: Initial value for transcribe audio
            delete_from_drive: Initial value for delete from drive
            output_folder: Initial output folder path
            transcription_provider: Initial transcription provider
            locked: If True, settings cannot be changed
        """
        super().__init__(**kwargs)
        self.include_media = include_media
        self.transcribe_audio = transcribe_audio
        self.delete_from_drive = delete_from_drive
        self.output_folder = output_folder
        self.transcription_provider = transcription_provider
        self._locked = locked

        # API key manager instance
        self._api_key_manager = None

    def _get_api_key_manager(self):
        """Lazy load API key manager."""
        if self._api_key_manager is None:
            from ...config.api_key_manager import get_api_key_manager
            self._api_key_manager = get_api_key_manager()
        return self._api_key_manager

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        manager = self._get_api_key_manager()

        yield Static(" SETTINGS ", classes="settings-title")

        with Vertical(classes="settings-container"):
            # Export Options Section
            yield Static("Export Options", classes="section-title")
            yield Checkbox(
                "Include Media",
                value=self.include_media,
                id="setting-media",
                disabled=self._locked,
            )
            yield Checkbox(
                "Delete from Drive",
                value=self.delete_from_drive,
                id="setting-delete",
                disabled=self._locked,
            )

            # Output Folder Section
            yield Static("", classes="section-spacer")
            yield Static("Output Folder", classes="section-title")
            yield Input(
                value=self.output_folder,
                placeholder="Enter output folder path...",
                id="setting-output-folder",
                disabled=self._locked,
            )

            # Transcription Section
            yield Static("", classes="section-spacer")
            yield Static("Transcription", classes="section-title")
            yield Checkbox(
                "Transcribe Audio",
                value=self.transcribe_audio,
                id="setting-transcribe",
                disabled=self._locked,
            )

            # Provider Selection
            yield Static("Provider:", classes="field-label")
            with RadioSet(id="setting-provider"):
                for provider in manager.get_all_providers():
                    info = manager.get_provider_info(provider)
                    display_name = info["display_name"]
                    if info["is_valid"]:
                        label = f"{display_name} \u2713"
                    elif info["has_key"]:
                        label = f"{display_name} (invalid key)"
                    else:
                        label = f"{display_name} (no key)"
                    is_selected = (provider == self.transcription_provider)
                    is_disabled = not info["is_valid"] or self._locked
                    yield RadioButton(
                        label,
                        value=is_selected,
                        id=f"provider-{provider}",
                        disabled=is_disabled,
                    )

            # API Keys Section
            yield Static("", classes="section-spacer")
            yield Static("API Keys", classes="section-title")

            # OpenAI API Key
            openai_info = manager.get_provider_info("whisper")
            openai_key = manager.get_api_key("whisper") or ""
            yield Static("OpenAI API Key (for Whisper):", classes="field-label")
            with Horizontal(classes="api-key-row"):
                yield Input(
                    value=openai_key,
                    placeholder="sk-...",
                    id="setting-openai-key",
                    disabled=self._locked,
                    classes="api-key-input",
                )
                status_class = self._get_status_class(openai_info["status"])
                yield Static(
                    openai_info["status"],
                    id="openai-key-status",
                    classes=f"api-status {status_class}",
                )

            # ElevenLabs API Key
            elevenlabs_info = manager.get_provider_info("elevenlabs")
            elevenlabs_key = manager.get_api_key("elevenlabs") or ""
            yield Static("ElevenLabs API Key:", classes="field-label")
            with Horizontal(classes="api-key-row"):
                yield Input(
                    value=elevenlabs_key,
                    placeholder="Enter key...",
                    id="setting-elevenlabs-key",
                    disabled=self._locked,
                    classes="api-key-input",
                )
                status_class = self._get_status_class(elevenlabs_info["status"])
                yield Static(
                    elevenlabs_info["status"],
                    id="elevenlabs-key-status",
                    classes=f"api-status {status_class}",
                )



    def on_mount(self) -> None:
        """Auto-select valid provider and disable transcription if no providers available."""
        manager = self._get_api_key_manager()
        available = manager.get_available_providers()
        if not available:
            # No valid providers - disable transcription
            try:
                cb = self.query_one("#setting-transcribe", Checkbox)
                cb.value = False
                cb.disabled = True
                self.transcribe_audio = False
            except Exception:
                pass
        elif self.transcription_provider not in available:
            # Current provider invalid, auto-select first valid one
            self.transcription_provider = available[0]
            try:
                rb = self.query_one(f"#provider-{available[0]}", RadioButton)
                rb.value = True
            except Exception:
                pass

    def on_key(self, event: Key) -> None:
        """Handle arrow key navigation between settings widgets.

        When the provider RadioSet is focused, up/down/enter/space are
        left to RadioSet's built-in bindings so the user can navigate
        between providers. Tab / Shift+Tab exits the RadioSet.
        """
        focused = self.screen.focused
        is_provider_radio = (
            isinstance(focused, RadioSet)
            and getattr(focused, "id", None) == "setting-provider"
        )

        # Let the RadioSet handle its own navigation keys
        if is_provider_radio and event.key in ("up", "down", "enter", "space"):
            return

        if event.key == "down":
            self.screen.focus_next()
            event.stop()
        elif event.key == "up":
            self.screen.focus_previous()
            event.stop()

    def _get_status_class(self, status: str) -> str:
        """Get CSS class for status display."""
        if status == "Valid":
            return "api-status-valid"
        elif status == "Invalid":
            return "api-status-invalid"
        else:
            return "api-status-unknown"

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        if self._locked:
            # Revert the change
            event.checkbox.value = not event.value
            return

        checkbox_id = event.checkbox.id
        if checkbox_id == "setting-media":
            self.include_media = event.value
        elif checkbox_id == "setting-transcribe":
            self.transcribe_audio = event.value
            # Update provider select enabled state
            self._update_provider_select_state()
        elif checkbox_id == "setting-delete":
            self.delete_from_drive = event.value

        self._notify_settings_changed()

    def _update_provider_select_state(self) -> None:
        """Enable/disable provider RadioSet based on transcribe checkbox."""
        try:
            radio_set = self.query_one("#setting-provider", RadioSet)
            radio_set.disabled = self._locked or not self.transcribe_audio
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input field changes."""
        if self._locked:
            return

        if event.input.id == "setting-output-folder":
            self.output_folder = event.value
            self._notify_settings_changed()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input field submission (Enter key)."""
        if self._locked:
            return

        input_id = event.input.id

        # Handle API key submission
        if input_id in ("setting-openai-key", "setting-elevenlabs-key"):
            self._save_api_key(input_id, event.value)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio set changes."""
        if self._locked:
            return
        if event.radio_set.id == "setting-provider":
            button_id = event.pressed.id
            if button_id and button_id.startswith("provider-"):
                provider = button_id[len("provider-"):]
                self.transcription_provider = provider
                self._notify_settings_changed()

    def _save_api_key(self, input_id: str, value: str) -> None:
        """
        Save an API key and update status.

        Args:
            input_id: The input field ID
            value: The API key value
        """
        value = value.strip()
        if not value:
            return

        manager = self._get_api_key_manager()

        if input_id == "setting-openai-key":
            provider = "whisper"
            status_id = "openai-key-status"
        elif input_id == "setting-elevenlabs-key":
            provider = "elevenlabs"
            status_id = "elevenlabs-key-status"
        else:
            return

        # Save the key
        success = manager.set_api_key(provider, value)

        if success:
            # Validate and update status
            is_valid, error_msg = manager.validate_api_key(provider, value)
            status = "Valid" if is_valid else "Invalid"
        else:
            status = "Save failed"
            is_valid = False

        # Update status display
        try:
            status_widget = self.query_one(f"#{status_id}", Static)
            status_class = self._get_status_class(status)
            status_widget.update(status)
            status_widget.remove_class("api-status-valid", "api-status-invalid", "api-status-unknown")
            status_widget.add_class(status_class)
        except Exception:
            pass

        # Update provider dropdown labels
        self._refresh_provider_options()

        # Notify about change
        self._notify_settings_changed()

        # Show feedback
        if is_valid:
            self.notify(f"{provider.title()} API key saved and validated", severity="information")
        else:
            self.notify(f"API key saved but validation failed", severity="warning")

    def _refresh_provider_options(self) -> None:
        """Refresh provider radio buttons with updated labels and disabled state."""
        manager = self._get_api_key_manager()
        available = manager.get_available_providers()

        for provider in manager.get_all_providers():
            info = manager.get_provider_info(provider)
            display_name = info["display_name"]
            if info["is_valid"]:
                label = f"{display_name} \u2713"
            elif info["has_key"]:
                label = f"{display_name} (invalid key)"
            else:
                label = f"{display_name} (no key)"
            try:
                rb = self.query_one(f"#provider-{provider}", RadioButton)
                rb.label = label
                rb.disabled = not info["is_valid"] or self._locked
            except Exception:
                pass

        # Update transcribe checkbox availability
        try:
            cb = self.query_one("#setting-transcribe", Checkbox)
            if not available and not self._locked:
                cb.value = False
                cb.disabled = True
                self.transcribe_audio = False
            elif available and not self._locked:
                cb.disabled = False
        except Exception:
            pass

        # Auto-select first valid provider if current is invalid
        if available and self.transcription_provider not in available:
            self.transcription_provider = available[0]
            try:
                rb = self.query_one(f"#provider-{available[0]}", RadioButton)
                rb.value = True
            except Exception:
                pass

    def _notify_settings_changed(self) -> None:
        """Post message about settings change."""
        self.post_message(
            self.SettingsChanged(
                include_media=self.include_media,
                transcribe_audio=self.transcribe_audio,
                delete_from_drive=self.delete_from_drive,
                output_folder=self.output_folder,
                transcription_provider=self.transcription_provider,
            )
        )

    def set_locked(self, locked: bool) -> None:
        """
        Lock or unlock settings.

        Args:
            locked: If True, settings cannot be changed
        """
        self._locked = locked

        # Update all interactive widgets
        for checkbox in self.query(Checkbox):
            checkbox.disabled = locked

        for input_widget in self.query(Input):
            input_widget.disabled = locked

        for radio_set in self.query(RadioSet):
            radio_set.disabled = locked

        # Provider select should also respect transcribe checkbox state
        if not locked:
            self._update_provider_select_state()

    def get_settings(self) -> dict:
        """
        Get current settings as a dictionary.

        Returns:
            Dictionary with setting values
        """
        return {
            "include_media": self.include_media,
            "transcribe_audio": self.transcribe_audio,
            "delete_from_drive": self.delete_from_drive,
            "output_folder": self.output_folder,
            "transcription_provider": self.transcription_provider,
        }

    def refresh_api_key_status(self) -> None:
        """Refresh API key status displays."""
        manager = self._get_api_key_manager()

        for provider, status_id in [("whisper", "openai-key-status"), ("elevenlabs", "elevenlabs-key-status")]:
            info = manager.get_provider_info(provider)
            status = info["status"]
            status_class = self._get_status_class(status)

            try:
                status_widget = self.query_one(f"#{status_id}", Static)
                status_widget.update(status)
                status_widget.remove_class("api-status-valid", "api-status-invalid", "api-status-unknown")
                status_widget.add_class(status_class)
            except Exception:
                pass

        self._refresh_provider_options()

    def get_valid_providers(self) -> List[str]:
        """Get list of providers with valid API keys."""
        manager = self._get_api_key_manager()
        return manager.get_available_providers()

    def has_valid_transcription_provider(self) -> bool:
        """Check if the selected transcription provider has a valid API key."""
        if not self.transcribe_audio:
            return True  # Transcription disabled, so no provider needed

        manager = self._get_api_key_manager()
        info = manager.get_provider_info(self.transcription_provider)
        return info["is_valid"]
