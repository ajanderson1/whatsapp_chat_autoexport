"""
Textual-based TUI application for WhatsApp Chat Auto-Export.

Provides an interactive terminal interface with:
- Pipeline stage navigation (Connect, Discover Messages, Select Messages, Process Messages)
- Keyboard-only navigation
- Real-time progress updates
- Event-driven state management
"""

from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Any, TYPE_CHECKING
import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header
from textual.reactive import reactive, var

from ..export.models import ChatMetadata
from ..state.models import SessionState, ChatState, SessionStatus
from ..state.state_manager import StateManager
from ..core.events import EventBus, EventType, Event, get_event_bus
from ..utils.logger import Logger

if TYPE_CHECKING:
    from ..export.whatsapp_driver import WhatsAppDriver
    from ..export.chat_exporter import ChatExporter
    from ..export.appium_manager import AppiumManager


class PipelineStage(Enum):
    """Pipeline stages for the export workflow.

    Deprecated: will be removed once all references are migrated to the
    tab-based MainScreen workflow.
    """
    CONNECT = auto()
    DISCOVER = auto()
    SELECT = auto()
    PROCESS = auto()


class WhatsAppExporterApp(App):
    """
    Main Textual application for WhatsApp export workflow.

    Manages:
    - Screen transitions between pipeline stages
    - Global keyboard bindings
    - State manager integration
    - Event bus subscriptions
    """

    CSS_PATH = "styles.tcss"

    TITLE = "WhatsApp Exporter"

    # Disable mouse support for cleaner keyboard-only navigation
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("q", "quit_app", "Quit", show=True, priority=True),
        Binding("ctrl+q", "quit_app", "Quit", show=False, priority=True),
        Binding("ctrl+c", "quit_app", "Quit", show=False, priority=True),
        Binding("h", "show_help", "Help", show=True),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("escape", "go_back", "Back", show=False),
        Binding("slash", "show_secret_settings", "Settings", show=False),
        Binding("1", "switch_tab('connect')", show=False),
        Binding("2", "switch_tab('discover-select')", show=False),
        Binding("3", "switch_tab('export')", show=False),
        Binding("4", "switch_tab('summary')", show=False),
    ]

    # Reactive state
    current_stage: reactive[PipelineStage] = reactive(PipelineStage.CONNECT)

    # Default output directory
    DEFAULT_OUTPUT_DIR = Path.home() / "whatsapp_exports"

    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        event_bus: Optional[EventBus] = None,
        output_dir: Optional[Path] = None,
        include_media: bool = True,
        transcribe_audio: bool = True,
        delete_from_drive: bool = False,
        transcription_provider: str = "whisper",
        limit: Optional[int] = None,
        debug: bool = False,
        dry_run: bool = False,
    ):
        """
        Initialize the WhatsApp Exporter TUI application.

        Args:
            state_manager: State manager for session tracking
            event_bus: Event bus for notifications
            output_dir: Output directory for processed files
            include_media: Whether to include media in exports
            transcribe_audio: Whether to transcribe audio files
            delete_from_drive: Whether to delete from Drive after processing
            transcription_provider: Transcription provider ('whisper' or 'elevenlabs')
            limit: Maximum number of chats to export
            debug: Enable debug mode
            dry_run: Run in dry-run mode (no actual exports)
        """
        super().__init__()

        # Configuration - use default output dir if not specified
        self.output_dir = output_dir or self.DEFAULT_OUTPUT_DIR
        self.include_media = include_media
        self.transcribe_audio = transcribe_audio
        self.delete_from_drive = delete_from_drive
        self.transcription_provider = transcription_provider
        self.limit = limit
        self.debug_mode = debug
        self.dry_run = dry_run

        # State management
        self._state_manager = state_manager or StateManager()
        self._event_bus = event_bus or get_event_bus()

        # Driver and exporter (set during discovery)
        self._whatsapp_driver: Optional["WhatsAppDriver"] = None
        self._exporter: Optional["ChatExporter"] = None
        self._appium_manager: Optional["AppiumManager"] = None

        # Chat data
        self._discovered_chats: List[ChatMetadata] = []
        self._selected_chats: List[str] = []

        # Selection state (locked after export starts)
        self._selection_locked = False

        # Activity log
        self._activity_log: List[str] = []

        # Subscribe to events
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Set up event bus handlers."""
        self._event_bus.subscribe(
            EventType.STATE_CHANGED,
            self._on_state_changed,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_STEP_COMPLETED,
            self._on_export_progress,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_COMPLETED,
            self._on_export_completed,
        )
        self._event_bus.subscribe(
            EventType.EXPORT_FAILED,
            self._on_export_failed,
        )
        self._event_bus.subscribe(
            EventType.CHAT_COLLECTION_COMPLETED,
            self._on_chat_collection_completed,
        )

    def _on_state_changed(self, event: Event) -> None:
        """Handle state change events."""
        self._log_activity(f"State: {event.data.get('new_state', 'unknown')}")

    def _on_export_progress(self, event: Event) -> None:
        """Handle export progress events."""
        chat_name = event.data.get("chat_name", "")
        step_name = event.data.get("step_name", "")
        if chat_name and step_name:
            self._log_activity(f"[{chat_name}] {step_name}")

    def _on_export_completed(self, event: Event) -> None:
        """Handle export completed events."""
        chat_name = event.data.get("chat_name", "")
        if chat_name:
            self._log_activity(f"[green]Completed:[/green] {chat_name}")

    def _on_export_failed(self, event: Event) -> None:
        """Handle export failed events."""
        chat_name = event.data.get("chat_name", "")
        error = event.data.get("error", "Unknown error")
        if chat_name:
            self._log_activity(f"[red]Failed:[/red] {chat_name} - {error}")

    def _on_chat_collection_completed(self, event: Event) -> None:
        """Handle chat collection completed events."""
        total = event.data.get("total_chats", 0)
        self._log_activity(f"Found {total} chats")

    def _log_activity(self, message: str) -> None:
        """Add a message to the activity log."""
        self._activity_log.append(message)
        # Keep last 100 messages
        if len(self._activity_log) > 100:
            self._activity_log = self._activity_log[-100:]

    def compose(self) -> ComposeResult:
        """Compose the main application layout."""
        yield Header(show_clock=True)
        yield Footer()

    async def on_mount(self) -> None:
        """Handle app mount - register themes and show initial screen."""
        # Register all color themes
        from ..config.themes import ALL_THEMES
        from ..config.theme_manager import get_theme_manager

        for theme in ALL_THEMES:
            self.register_theme(theme)

        # Load and apply saved theme
        theme_manager = get_theme_manager()
        saved_theme = theme_manager.get_saved_theme()
        self.theme = saved_theme

        # Show initial screen
        from .textual_screens.main_screen import MainScreen
        await self.push_screen(MainScreen())

    def watch_current_stage(self, stage: PipelineStage) -> None:
        """React to stage changes."""
        self._log_activity(f"Stage: {stage.name}")

    def _cleanup_resources(self) -> None:
        """Clean up driver and Appium server resources."""
        # Set shutdown flag to suppress all logging during cleanup
        # This prevents ugly error messages when workers are cancelled
        Logger.set_shutdown(True)

        # Cancel all running workers to prevent them from accessing closed resources
        try:
            self.workers.cancel_all()
        except Exception:
            pass

        # Cleanup driver if connected
        if self._whatsapp_driver:
            try:
                self._whatsapp_driver.quit()
            except Exception:
                pass
            self._whatsapp_driver = None

        # Cleanup Appium server if running
        if self._appium_manager:
            try:
                self._appium_manager.stop_appium()
            except Exception:
                pass
            self._appium_manager = None

    async def action_quit_app(self) -> None:
        """Quit the application with clean shutdown."""
        # Suppress logging before any cleanup to prevent ugly error output
        Logger.set_shutdown(True)

        # Cancel all workers first - this stops background tasks from
        # accessing resources that are about to be cleaned up
        try:
            self.workers.cancel_all()
        except Exception:
            pass

        # Now cleanup resources
        self._cleanup_resources()

        # Exit the app
        self.exit()

    async def on_unmount(self) -> None:
        """Clean up resources when app unmounts."""
        # Suppress logging during unmount cleanup
        Logger.set_shutdown(True)
        self._cleanup_resources()

    def action_show_help(self) -> None:
        """Show help overlay."""
        from .textual_screens.help_screen import HelpScreen
        self.push_screen(HelpScreen())

    def action_go_back(self) -> None:
        """Go back -- only pops modal screens, never the main screen."""
        from textual.screen import ModalScreen

        if len(self.screen_stack) > 1:
            top_screen = self.screen_stack[-1]
            if isinstance(top_screen, ModalScreen):
                self.pop_screen()

    def action_show_secret_settings(self) -> None:
        """Show the secret settings modal (triggered by '/' key)."""
        from .textual_widgets import SecretSettingsModal
        self.push_screen(SecretSettingsModal())

    def action_switch_tab(self, tab_id: str) -> None:
        """Delegate tab switching to MainScreen."""
        from .textual_screens.main_screen import MainScreen
        if isinstance(self.screen, MainScreen):
            self.screen.action_switch_tab(tab_id)

    # =========================================================================
    # Stage transitions
    # =========================================================================

    def start_export_session(self, selected_chats: List[str]) -> None:
        """
        Initialize an export session (called from SelectionScreen).

        This sets up the state manager for tracking export progress
        without transitioning to a different screen.

        Args:
            selected_chats: List of chat names to export
        """
        self._selected_chats = selected_chats
        self._selection_locked = True  # Lock selection
        self.current_stage = PipelineStage.PROCESS

        # Create session and add chats
        session = self._state_manager.create_session(
            include_media=self.include_media,
            limit=self.limit,
        )
        self._state_manager.add_chats(selected_chats)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def state_manager(self) -> StateManager:
        """Get the state manager."""
        return self._state_manager

    @property
    def driver(self) -> Optional["WhatsAppDriver"]:
        """Get the WhatsApp driver."""
        return self._whatsapp_driver

    @property
    def discovered_chats(self) -> List[ChatMetadata]:
        """Get list of discovered chats."""
        return self._discovered_chats

    @property
    def selected_chats(self) -> List[str]:
        """Get list of selected chats."""
        return self._selected_chats

    @property
    def selection_locked(self) -> bool:
        """Check if selection is locked."""
        return self._selection_locked

    @property
    def activity_log(self) -> List[str]:
        """Get the activity log."""
        return self._activity_log
