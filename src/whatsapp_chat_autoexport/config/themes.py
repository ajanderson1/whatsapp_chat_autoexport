"""
Color scheme definitions for the WhatsApp Exporter TUI.

Provides 18 distinct color schemes using Textual's Theme class.
Each theme defines primary, secondary, accent, and semantic colors.
"""

from textual.theme import Theme


# =============================================================================
# Theme Definitions
# =============================================================================

WHATSAPP_THEME = Theme(
    name="whatsapp",
    primary="#25D366",  # WhatsApp green
    secondary="#128C7E",  # WhatsApp dark teal
    accent="#34B7F1",  # WhatsApp blue
    warning="#FFC107",
    error="#E53935",
    success="#25D366",
    background="#1E1E1E",
    surface="#2D2D2D",
    panel="#3D3D3D",
)

NORD_THEME = Theme(
    name="nord",
    primary="#88C0D0",  # Nord frost blue
    secondary="#81A1C1",  # Nord blue
    accent="#5E81AC",  # Nord darker blue
    warning="#EBCB8B",  # Nord yellow
    error="#BF616A",  # Nord red
    success="#A3BE8C",  # Nord green
    background="#2E3440",  # Nord polar night
    surface="#3B4252",
    panel="#434C5E",
)

GRUVBOX_THEME = Theme(
    name="gruvbox",
    primary="#83A598",  # Gruvbox aqua
    secondary="#8EC07C",  # Gruvbox green
    accent="#D3869B",  # Gruvbox purple
    warning="#FABD2F",  # Gruvbox yellow
    error="#FB4934",  # Gruvbox red
    success="#B8BB26",  # Gruvbox bright green
    background="#282828",  # Gruvbox dark bg
    surface="#3C3836",
    panel="#504945",
)

DRACULA_THEME = Theme(
    name="dracula",
    primary="#BD93F9",  # Dracula purple
    secondary="#FF79C6",  # Dracula pink
    accent="#8BE9FD",  # Dracula cyan
    warning="#F1FA8C",  # Dracula yellow
    error="#FF5555",  # Dracula red
    success="#50FA7B",  # Dracula green
    background="#282A36",  # Dracula background
    surface="#44475A",  # Dracula current line
    panel="#6272A4",  # Dracula comment
)

TOKYO_NIGHT_THEME = Theme(
    name="tokyo_night",
    primary="#7AA2F7",  # Tokyo Night blue
    secondary="#BB9AF7",  # Tokyo Night purple
    accent="#7DCFFF",  # Tokyo Night cyan
    warning="#E0AF68",  # Tokyo Night yellow
    error="#F7768E",  # Tokyo Night red
    success="#9ECE6A",  # Tokyo Night green
    background="#1A1B26",  # Tokyo Night background
    surface="#24283B",
    panel="#414868",
)

CATPPUCCIN_MOCHA_THEME = Theme(
    name="catppuccin_mocha",
    primary="#89B4FA",  # Catppuccin blue
    secondary="#CBA6F7",  # Catppuccin mauve
    accent="#94E2D5",  # Catppuccin teal
    warning="#F9E2AF",  # Catppuccin yellow
    error="#F38BA8",  # Catppuccin red
    success="#A6E3A1",  # Catppuccin green
    background="#1E1E2E",  # Catppuccin base
    surface="#313244",  # Catppuccin surface0
    panel="#45475A",  # Catppuccin surface1
)

SOLARIZED_LIGHT_THEME = Theme(
    name="solarized_light",
    primary="#268BD2",  # Solarized blue
    secondary="#2AA198",  # Solarized cyan
    accent="#6C71C4",  # Solarized violet
    warning="#B58900",  # Solarized yellow
    error="#DC322F",  # Solarized red
    success="#859900",  # Solarized green
    background="#FDF6E3",  # Solarized base3
    surface="#EEE8D5",  # Solarized base2
    panel="#93A1A1",  # Solarized base1
    dark=False,
)

ONE_LIGHT_THEME = Theme(
    name="one_light",
    primary="#4078F2",  # One Light blue
    secondary="#A626A4",  # One Light magenta
    accent="#0184BC",  # One Light cyan
    warning="#C18401",  # One Light yellow
    error="#E45649",  # One Light red
    success="#50A14F",  # One Light green
    background="#FAFAFA",  # One Light background
    surface="#F0F0F0",
    panel="#E5E5E5",
    dark=False,
)

HIGH_CONTRAST_THEME = Theme(
    name="high_contrast",
    primary="#00FFFF",  # Cyan
    secondary="#FF00FF",  # Magenta
    accent="#FFFF00",  # Yellow
    warning="#FFFF00",  # Yellow
    error="#FF0000",  # Red
    success="#00FF00",  # Green
    background="#000000",  # Pure black
    surface="#1A1A1A",
    panel="#333333",
)

MONOCHROME_THEME = Theme(
    name="monochrome",
    primary="#CCCCCC",  # Light grey
    secondary="#999999",  # Medium grey
    accent="#FFFFFF",  # White
    warning="#AAAAAA",  # Grey
    error="#888888",  # Dark grey
    success="#DDDDDD",  # Lighter grey
    background="#0A0A0A",  # Near black
    surface="#1A1A1A",
    panel="#2A2A2A",
)

MONOKAI_THEME = Theme(
    name="monokai",
    primary="#F92672",  # Monokai pink
    secondary="#66D9EF",  # Monokai cyan
    accent="#A6E22E",  # Monokai green
    warning="#E6DB74",  # Monokai yellow
    error="#F92672",  # Monokai pink
    success="#A6E22E",  # Monokai green
    background="#272822",  # Monokai bg
    surface="#3E3D32",
    panel="#49483E",
)

SYNTHWAVE_THEME = Theme(
    name="synthwave",
    primary="#FF7EDB",  # Neon pink
    secondary="#36F9F6",  # Cyan glow
    accent="#FEDE5D",  # Yellow
    warning="#FEDE5D",
    error="#FE4450",  # Red
    success="#72F1B8",  # Green glow
    background="#262335",  # Dark purple
    surface="#34294F",
    panel="#463465",
)

EVERFOREST_THEME = Theme(
    name="everforest",
    primary="#A7C080",  # Everforest green
    secondary="#7FBBB3",  # Aqua
    accent="#D699B6",  # Purple
    warning="#DBBC7F",  # Yellow
    error="#E67E80",  # Red
    success="#A7C080",  # Green
    background="#2D353B",  # Dark bg
    surface="#343F44",
    panel="#3D484D",
)

ROSE_PINE_THEME = Theme(
    name="rose_pine",
    primary="#EBBCBA",  # Rose
    secondary="#C4A7E7",  # Iris
    accent="#9CCFD8",  # Foam
    warning="#F6C177",  # Gold
    error="#EB6F92",  # Love
    success="#31748F",  # Pine
    background="#191724",  # Base
    surface="#1F1D2E",  # Surface
    panel="#26233A",  # Overlay
)

AYU_DARK_THEME = Theme(
    name="ayu_dark",
    primary="#FFB454",  # Ayu orange
    secondary="#36A3D9",  # Blue
    accent="#95E6CB",  # Cyan
    warning="#FFB454",  # Orange
    error="#FF3333",  # Red
    success="#B8CC52",  # Green
    background="#0D1017",  # Ayu bg
    surface="#131721",
    panel="#1C232E",
)

MATERIAL_OCEAN_THEME = Theme(
    name="material_ocean",
    primary="#82AAFF",  # Blue
    secondary="#C792EA",  # Purple
    accent="#89DDFF",  # Cyan
    warning="#FFCB6B",  # Yellow
    error="#FF5370",  # Red
    success="#C3E88D",  # Green
    background="#0F111A",  # Ocean bg
    surface="#181A1F",
    panel="#1F2233",
)

GITHUB_DARK_THEME = Theme(
    name="github_dark",
    primary="#58A6FF",  # GitHub blue
    secondary="#A371F7",  # Purple
    accent="#79C0FF",  # Light blue
    warning="#D29922",  # Yellow
    error="#F85149",  # Red
    success="#3FB950",  # Green
    background="#0D1117",  # GitHub dark bg
    surface="#161B22",
    panel="#21262D",
)

KANAGAWA_THEME = Theme(
    name="kanagawa",
    primary="#7E9CD8",  # Crystal blue
    secondary="#957FB8",  # Spring violet
    accent="#7FB4CA",  # Spring blue
    warning="#DCA561",  # Autumn yellow
    error="#C34043",  # Autumn red
    success="#76946A",  # Autumn green
    background="#1F1F28",  # Sumi ink
    surface="#2A2A37",
    panel="#363646",
)


# =============================================================================
# Theme Registry
# =============================================================================

# All available themes in display order
ALL_THEMES = [
    WHATSAPP_THEME,
    NORD_THEME,
    GRUVBOX_THEME,
    DRACULA_THEME,
    TOKYO_NIGHT_THEME,
    CATPPUCCIN_MOCHA_THEME,
    SOLARIZED_LIGHT_THEME,
    ONE_LIGHT_THEME,
    HIGH_CONTRAST_THEME,
    MONOCHROME_THEME,
    MONOKAI_THEME,
    SYNTHWAVE_THEME,
    EVERFOREST_THEME,
    ROSE_PINE_THEME,
    AYU_DARK_THEME,
    MATERIAL_OCEAN_THEME,
    GITHUB_DARK_THEME,
    KANAGAWA_THEME,
]

# Theme names to display names mapping
THEME_DISPLAY_NAMES = {
    "whatsapp": "WhatsApp",
    "nord": "Nord",
    "gruvbox": "Gruvbox",
    "dracula": "Dracula",
    "tokyo_night": "Tokyo Night",
    "catppuccin_mocha": "Catppuccin Mocha",
    "solarized_light": "Solarized Light",
    "one_light": "One Light",
    "high_contrast": "High Contrast",
    "monochrome": "Monochrome",
    "monokai": "Monokai",
    "synthwave": "Synthwave '84",
    "everforest": "Everforest",
    "rose_pine": "Rosé Pine",
    "ayu_dark": "Ayu Dark",
    "material_ocean": "Material Ocean",
    "github_dark": "GitHub Dark",
    "kanagawa": "Kanagawa",
}

# Default theme name
DEFAULT_THEME = "whatsapp"


def get_theme_by_name(name: str) -> Theme | None:
    """Get a theme by its name."""
    for theme in ALL_THEMES:
        if theme.name == name:
            return theme
    return None


def get_theme_display_name(name: str) -> str:
    """Get the display name for a theme."""
    return THEME_DISPLAY_NAMES.get(name, name.replace("_", " ").title())


def get_all_theme_names() -> list[str]:
    """Get list of all theme names in display order."""
    return [theme.name for theme in ALL_THEMES]
