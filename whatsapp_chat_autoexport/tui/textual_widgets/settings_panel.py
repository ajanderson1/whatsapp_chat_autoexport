"""
Settings panel widget with toggle options and configurable settings.

Displays export settings with:
- Checkboxes for include media, transcribe audio, delete from Drive
- Output folder input
- Transcription provider selection
- API key configuration with validation status
"""

import shutil
from pathlib import Path
from typing import Optional, List

from textual.app import ComposeResult
from textual.events import Key
from textual.widget import Widget
from textual.widgets import Static, Checkbox, Input, Label, RadioButton, RadioSet, Button
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.worker import Worker, WorkerState


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

    class DriveStatusChanged(Message):
        """Posted when Drive auth state changes (sign in, sign out, file pick)."""

        def __init__(self, signed_in: bool, user_email: Optional[str] = None) -> None:
            self.signed_in = signed_in
            self.user_email = user_email
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
        # Drive auth instance (lazy)
        self._drive_auth = None
        self._drive_signing_in = False

    def _get_drive_auth(self):
        """Lazy load Google Drive auth manager."""
        if self._drive_auth is None:
            from ...google_drive.auth import GoogleDriveAuth
            self._drive_auth = GoogleDriveAuth()
        return self._drive_auth

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

            # Google Drive Section
            yield Static("", classes="section-spacer")
            yield Static("Google Drive", classes="section-title")
            yield Static(
                "[dim]Checking...[/dim]",
                id="drive-status",
                classes="drive-status",
            )
            yield Input(
                value="",
                placeholder="Path to client_secrets.json...",
                id="setting-client-secrets-path",
                disabled=self._locked,
                classes="client-secrets-input",
            )
            with Horizontal(classes="drive-buttons"):
                yield Button(
                    "Choose file\u2026",
                    id="btn-choose-secrets",
                    variant="default",
                    disabled=self._locked,
                )
                yield Button(
                    "Sign in to Drive",
                    id="btn-drive-sign-in",
                    variant="primary",
                    disabled=True,
                )
                yield Button(
                    "Sign out",
                    id="btn-drive-sign-out",
                    variant="error",
                    disabled=True,
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
        """Auto-select valid provider, disable transcription if no providers, refresh Drive."""
        self._refresh_drive_section()

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
        elif input_id == "setting-client-secrets-path":
            self._handle_choose_secrets()

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

    # ------------------------------------------------------------------
    # Google Drive section
    # ------------------------------------------------------------------

    def _refresh_drive_section(self) -> None:
        """Update Drive section UI from current auth state."""
        try:
            auth = self._get_drive_auth()
            status = auth.get_credentials_status()

            status_widget = self.query_one("#drive-status", Static)
            sign_in_btn = self.query_one("#btn-drive-sign-in", Button)
            sign_out_btn = self.query_one("#btn-drive-sign-out", Button)
            secrets_input = self.query_one("#setting-client-secrets-path", Input)

            # Check app-level email (set after sign-in via Drive API)
            app_email = getattr(self.app, "_drive_user_email", None)

            if not status["client_secrets_present"]:
                status_widget.update(
                    "[yellow]Not configured[/yellow] — "
                    "provide client_secrets.json below"
                )
                sign_in_btn.disabled = True
                sign_out_btn.disabled = True
            elif status["token_valid"] or (status["token_present"] and app_email):
                email = app_email or status.get("user_email") or "unknown"
                status_widget.update(
                    f"[green]Signed in[/green] as {email}"
                )
                sign_in_btn.disabled = True
                sign_out_btn.disabled = self._locked
            elif status["token_present"]:
                status_widget.update(
                    "[yellow]Token expired[/yellow] — click Sign in to refresh"
                )
                sign_in_btn.disabled = self._locked or self._drive_signing_in
                sign_out_btn.disabled = self._locked
            else:
                status_widget.update(
                    "[dim]Ready to authenticate[/dim] — click Sign in"
                )
                sign_in_btn.disabled = self._locked or self._drive_signing_in
                sign_out_btn.disabled = True

            # Show current secrets path
            secrets_path = str(auth.client_secrets_file)
            if status["client_secrets_present"]:
                secrets_input.value = secrets_path
            else:
                secrets_input.value = ""
                secrets_input.placeholder = f"Path to client_secrets.json (will copy to {secrets_path})"

        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Drive section button clicks."""
        if event.button.id == "btn-choose-secrets":
            self._handle_choose_secrets()
        elif event.button.id == "btn-drive-sign-in":
            self._handle_drive_sign_in()
        elif event.button.id == "btn-drive-sign-out":
            self._handle_drive_sign_out()

    def _handle_choose_secrets(self) -> None:
        """Copy user-provided client_secrets.json path to the credentials dir."""
        try:
            secrets_input = self.query_one("#setting-client-secrets-path", Input)
            source_path = Path(secrets_input.value.strip())

            if not source_path.exists():
                self._log("client_secrets.json not found at that path")
                return
            if not source_path.is_file():
                self._log("Path is not a file")
                return

            auth = self._get_drive_auth()
            auth.setup_credentials_directory()
            dest = auth.client_secrets_file

            if source_path.resolve() != dest.resolve():
                shutil.copy2(str(source_path), str(dest))
                self._log(f"Copied client_secrets.json to {dest}")
            else:
                self._log("client_secrets.json already in place")

            self._refresh_drive_section()
            self.post_message(self.DriveStatusChanged(signed_in=False))
        except Exception as e:
            self._log(f"Failed to copy client_secrets.json: {e}")

    def _handle_drive_sign_in(self) -> None:
        """Start the OAuth sign-in flow in a worker thread."""
        if self._drive_signing_in:
            return

        self._drive_signing_in = True
        try:
            self.query_one("#btn-drive-sign-in", Button).disabled = True
            self.query_one("#drive-status", Static).update(
                "[dim]Opening browser for authentication...[/dim]"
            )
        except Exception:
            pass

        self._log("Starting Google Drive sign-in — check your browser...")
        self.run_worker(self._do_drive_sign_in, thread=True, name="drive_sign_in")

    def _do_drive_sign_in(self) -> dict:
        """Worker thread: run the OAuth flow."""
        auth = self._get_drive_auth()
        creds = auth.authenticate()
        if creds is None:
            return {"success": False, "error": "Authentication failed or was cancelled"}

        # Fetch the user's email via the Drive API about endpoint.
        # The `drive` scope doesn't include id_token claims, so we
        # can't read it from the token itself.
        email = None
        try:
            from googleapiclient.discovery import build
            service = build("drive", "v3", credentials=creds)
            about = service.about().get(fields="user(emailAddress)").execute()
            email = about.get("user", {}).get("emailAddress")
        except Exception:
            pass

        return {"success": True, "credentials": creds, "email": email}

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle Drive sign-in worker completion."""
        if event.worker.name != "drive_sign_in":
            return

        self._drive_signing_in = False

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result or {}
            if result.get("success"):
                email = result.get("email", "unknown")
                self.app._drive_credentials = result.get("credentials")
                self.app._drive_user_email = email
                self._log(f"Signed in to Google Drive as {email}")
                self.post_message(self.DriveStatusChanged(signed_in=True, user_email=email))
            else:
                error = result.get("error", "Unknown error")
                self._log(f"Drive sign-in failed: {error}")
                self.post_message(self.DriveStatusChanged(signed_in=False))

        elif event.state == WorkerState.ERROR:
            self._log("Drive sign-in failed — check the activity log for details")
            self.post_message(self.DriveStatusChanged(signed_in=False))

        elif event.state == WorkerState.CANCELLED:
            self._log("Drive sign-in cancelled")
            self.post_message(self.DriveStatusChanged(signed_in=False))

        self._refresh_drive_section()

    def _handle_drive_sign_out(self) -> None:
        """Sign out: delete the token file and clear app state."""
        auth = self._get_drive_auth()
        auth.revoke_credentials()
        self.app._drive_credentials = None
        self.app._drive_user_email = None
        self._log("Signed out of Google Drive")
        self._refresh_drive_section()
        self.post_message(self.DriveStatusChanged(signed_in=False))

    def _log(self, message: str) -> None:
        """Write to the screen-level ActivityLog."""
        try:
            from .activity_log import ActivityLog
            log_widget = self.screen.query_one(ActivityLog)
            log_widget.log(message)
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

        for button in self.query(Button):
            button.disabled = locked

        # Provider select should also respect transcribe checkbox state
        if not locked:
            self._update_provider_select_state()
            self._refresh_drive_section()

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
