"""
Tests for legacy migration (Unit 9).

Verifies that:
- Active Textual TUI imports work correctly
- Headless mode imports work correctly
- Legacy directory exists with moved code
- Active tui/ code does not import Rich or Typer libraries
"""

import ast
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent
TUI_PACKAGE = PROJECT_ROOT / "whatsapp_chat_autoexport" / "tui"
LEGACY_PACKAGE = PROJECT_ROOT / "whatsapp_chat_autoexport" / "legacy"


class TestActiveImports:
    """Verify that active Textual TUI imports still work."""

    def test_import_whatsapp_exporter_app(self):
        """WhatsAppExporterApp should be importable from tui package."""
        from whatsapp_chat_autoexport.tui import WhatsAppExporterApp

        assert WhatsAppExporterApp is not None

    def test_import_pipeline_stage(self):
        """PipelineStage enum should be importable."""
        from whatsapp_chat_autoexport.tui import PipelineStage

        assert PipelineStage is not None

    def test_import_textual_screens(self):
        """Active Textual screens should be importable."""
        from whatsapp_chat_autoexport.tui.textual_screens import (
            MainScreen,
            HelpScreen,
        )

        assert MainScreen is not None
        assert HelpScreen is not None

    def test_import_textual_widgets(self):
        """Textual widgets should be importable."""
        from whatsapp_chat_autoexport.tui.textual_widgets import (
            ChatListWidget,
            SettingsPanel,
            ActivityLog,
            QueueWidget,
            ProgressDisplay,
        )

        assert ChatListWidget is not None
        assert SettingsPanel is not None
        assert ActivityLog is not None
        assert QueueWidget is not None
        assert ProgressDisplay is not None

    def test_import_headless(self):
        """Headless mode should be importable."""
        from whatsapp_chat_autoexport.headless import run_headless

        assert callable(run_headless)


class TestLegacyDirectoryExists:
    """Verify the legacy directory structure."""

    def test_legacy_package_exists(self):
        """Legacy package directory should exist."""
        assert LEGACY_PACKAGE.is_dir()
        assert (LEGACY_PACKAGE / "__init__.py").is_file()

    def test_legacy_tui_exists(self):
        """Legacy tui subdirectory should contain moved Rich TUI code."""
        legacy_tui = LEGACY_PACKAGE / "tui"
        assert legacy_tui.is_dir()
        assert (legacy_tui / "app.py").is_file()
        assert (legacy_tui / "wizard.py").is_file()
        assert (legacy_tui / "screens").is_dir()
        assert (legacy_tui / "components").is_dir()

    def test_legacy_cli_exists(self):
        """Legacy cli directory should contain moved Typer CLI code."""
        legacy_cli = LEGACY_PACKAGE / "cli"
        assert legacy_cli.is_dir()

    def test_legacy_textual_screens_exist(self):
        """Dead Textual screens should be in legacy."""
        legacy_screens = LEGACY_PACKAGE / "textual_screens"
        assert legacy_screens.is_dir()
        assert (legacy_screens / "export_screen.py").is_file()
        assert (legacy_screens / "processing_screen.py").is_file()


class TestNoRichOrTyperInActiveTUI:
    """Verify that active tui/ code does not import Rich TUI or Typer libraries."""

    # Rich imports that indicate Rich TUI usage (not just textual markup strings)
    RICH_IMPORTS = {
        "rich.console",
        "rich.progress",
        "rich.panel",
        "rich.table",
        "rich.live",
        "rich.layout",
    }

    TYPER_IMPORT = "typer"

    def _collect_active_tui_files(self):
        """Collect all .py files in active tui/ code (excluding __pycache__)."""
        files = []
        for root, dirs, filenames in os.walk(TUI_PACKAGE):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".py"):
                    files.append(Path(root) / fn)
        return files

    def _get_imports_from_file(self, filepath: Path):
        """Parse a Python file and return all import module strings."""
        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_no_rich_console_or_live_imports(self):
        """Active tui/ code should not import Rich Console, Progress, Panel, Table, or Live."""
        violations = []
        for filepath in self._collect_active_tui_files():
            imports = self._get_imports_from_file(filepath)
            for imp in imports:
                for rich_mod in self.RICH_IMPORTS:
                    if imp == rich_mod or imp.startswith(rich_mod + "."):
                        rel = filepath.relative_to(PROJECT_ROOT)
                        violations.append(f"{rel}: imports {imp}")

        assert violations == [], (
            f"Active tui/ code should not import Rich TUI modules:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_typer_imports(self):
        """Active tui/ code should not import typer."""
        violations = []
        for filepath in self._collect_active_tui_files():
            imports = self._get_imports_from_file(filepath)
            for imp in imports:
                if imp == self.TYPER_IMPORT or imp.startswith(self.TYPER_IMPORT + "."):
                    rel = filepath.relative_to(PROJECT_ROOT)
                    violations.append(f"{rel}: imports {imp}")

        assert violations == [], (
            f"Active tui/ code should not import typer:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestHardcodedPathsRemoved:
    """Verify no hardcoded user paths remain in active tui/ code."""

    def test_no_hardcoded_home_paths(self):
        """Active tui/ code should not contain hardcoded /Users/ paths."""
        violations = []
        for root, dirs, filenames in os.walk(TUI_PACKAGE):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".py"):
                    filepath = Path(root) / fn
                    content = filepath.read_text()
                    for i, line in enumerate(content.splitlines(), 1):
                        if "/Users/" in line and not line.strip().startswith("#"):
                            rel = filepath.relative_to(PROJECT_ROOT)
                            violations.append(f"{rel}:{i}: {line.strip()}")

        assert violations == [], (
            f"Hardcoded /Users/ paths found in active tui/ code:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
