
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    accent: str
    accent2: str
    bg: str
    bg2: str
    text: str
    muted: str
    danger: str
    success: str


THEMES: dict[str, Theme] = {
    "stark": Theme(
        name="Stark",
        accent="#3B9EFF",   accent2="#0080FF",
        bg="#050d12",       bg2="#0a1520",
        text="#C8E8F0",     muted="#4A6880",
        danger="#FF2244",   success="#00FF88",
    ),
    "matrix": Theme(
        name="Matrix",
        accent="#00FF41",   accent2="#008F11",
        bg="#0D0208",       bg2="#0f1a0f",
        text="#C0FFC0",     muted="#3A6B3A",
        danger="#FF4444",   success="#00FF41",
    ),
    "midnight": Theme(
        name="Midnight",
        accent="#3B82F6",   accent2="#1E6FE0",
        bg="#0C0A1E",       bg2="#13102B",
        text="#CFE4FF",     muted="#0E2A5E",
        danger="#F87171",   success="#2DE8B0",
    ),
    "amber": Theme(
        name="Amber",
        accent="#F59E0B",   accent2="#D97706",
        bg="#0C0A00",       bg2="#1C1600",
        text="#FEF3C7",     muted="#78350F",
        danger="#EF4444",   success="#10B981",
    ),
    "rose": Theme(
        name="Rose",
        accent="#FF5C7A",   accent2="#E11D48",
        bg="#0D0509",       bg2="#1a0a10",
        text="#FFE4E6",     muted="#881337",
        danger="#EF4444",   success="#2DE8B0",
    ),
}

_active: str = "stark"


def get_theme(name: str | None = None) -> Theme:
    return THEMES.get(name or _active, THEMES["stark"])


def set_theme(name: str) -> Theme:
    global _active
    if name not in THEMES:
        raise ValueError(f"Unknown theme {name!r}. Available: {list(THEMES)}")
    _active = name
    return THEMES[name]


def list_themes() -> list[str]:
    return list(THEMES.keys())


def build_stylesheet(theme: str | Theme | None = None) -> str:
    if isinstance(theme, str):
        t = THEMES.get(theme, THEMES["stark"])
    else:
        t = theme or get_theme()
    a  = t.accent
    b2 = t.bg2
    bg = t.bg
    tx = t.text
    mu = t.muted
    return f"""
QMainWindow, QDialog {{ background: {bg}; }}
QWidget {{
    background: transparent;
    color: {tx};
    font-family: Consolas, 'Courier New', monospace;
}}
#headerPanel {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(0,0,0,210), stop:1 rgba(0,0,0,160));
    border-bottom: 1px solid {a}33;
    border-radius: 14px;
}}
#title   {{ color: {a};  font-size: 22px; font-weight: 800; letter-spacing: 6px; }}
#subtitle {{ color: {mu}; font-size: 9px;  letter-spacing: 3px; }}
#panel, #hudIntelFeed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {b2}EE, stop:1 {bg}EE);
    border: 1px solid {a}22;
    border-radius: 14px;
}}
#panelTitle, QLabel#panelTitle {{
    color: {mu};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    padding: 0px 0px 2px 0px;
}}
QSplitter::handle {{
    background: {a}18;
    border-radius: 2px;
}}
QSplitter::handle:hover {{
    background: {a}44;
}}
#activityLog {{
    background: transparent;
    border: none;
}}
#chatPanel {{
    background: rgba(0,0,0,140);
    border: 1px solid {a}18;
    border-radius: 14px;
}}
#chatDisplay {{
    background: transparent;
    border: none;
    color: {tx};
    font-size: 13px;
    selection-background-color: {a}55;
}}
#msgInput {{
    background: rgba(0,0,0,115);
    border: 1px solid {a}40;
    border-radius: 8px;
    color: {tx};
    font-size: 13px;
    padding: 6px 10px;
}}
#msgInput:focus    {{ border-color: {a}99; }}
#msgInput:disabled {{ background: rgba(0,0,0,50); color: {mu}; border-color: {mu}40; }}
QPushButton {{
    background: {a}18;
    border: 1px solid {a}55;
    border-radius: 7px;
    color: {a};
    font-family: Consolas;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 4px 12px;
}}
QPushButton:hover   {{ background: {a}35; border-color: {a}AA; }}
QPushButton:pressed {{ background: {a}55; }}
QScrollBar:vertical           {{ background: transparent; width: 4px; }}
QScrollBar::handle:vertical   {{ background: {a}44; border-radius: 2px; min-height: 24px; }}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel#muted     {{ color: {mu}; font-size: 10px; }}
QLabel#statusBar {{
    background: rgba(0,0,0,215);
    border-top: 1px solid {a}18;
    color: {mu};
    font-size: 10px;
    padding: 3px 6px;
}}
"""
