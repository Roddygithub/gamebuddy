"""Dark, translucent look. Colors can follow the current Omarchy theme when available."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT = {
    "bg": "#1b1f27",
    "panel": "#232833",
    "panel2": "#2b313d",
    "text": "#e9edf2",
    "muted": "#98a0ae",
    "accent": "#c6f24e",
    "accent2": "#ff6b57",
    "danger": "#ef4444",
    "user": "#2b313d",
    "bro": "#3b4433",
}


def ink_on(hex_color: str) -> str:
    """Readable text over that fill: a bright accent needs dark ink, not white."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#101418" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "#ffffff"


# `omarchy theme set` swaps this directory, so watching it follows the theme.
THEME_DIR = Path.home() / ".config" / "omarchy" / "current" / "theme"


def theme_file() -> Path:
    """The palette file GameBuddy reads; also watched for live theme changes."""
    return THEME_DIR / "colors.toml"


def _mix(base: str, toward: str, amount: float) -> str:
    a = [int(base[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(toward[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b, strict=True))


def omarchy_colors() -> dict[str, str]:
    """The active Omarchy palette, or DEFAULT when no theme file is readable.

    Omarchy's colors.toml uses `accent` plus the `color0`-`color15` ANSI slots;
    older palettes used named slots (`magenta`, `green`…), still accepted.
    """
    colors = dict(DEFAULT)
    for name in ("colors.toml", "alacritty.toml"):
        path = THEME_DIR / name
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        found = dict(re.findall(r'^\s*([\w-]+)\s*=\s*"(#[0-9a-fA-F]{6})"', text, re.M))
        if "background" in found:
            colors["bg"] = found["background"]
        if "foreground" in found:
            colors["text"] = found["foreground"]
        if "color0" in found:
            colors["panel"] = colors["panel2"] = colors["user"] = found["color0"]
        if "color8" in found:
            colors["muted"] = found["color8"]
        accent = next((found[k] for k in ("accent", "color4", "blue", "magenta", "cyan") if k in found), "")
        if accent:
            colors["accent"] = accent
            colors["bro"] = _mix(colors["bg"], accent, 0.22)
        green = found.get("color2") or found.get("green")
        if green:
            colors["accent2"] = green
        red = found.get("color1") or found.get("red")
        if red:
            colors["danger"] = red
        break
    return colors


def stylesheet(c: dict[str, str], font_size: int = 13, opacity: float = 0.94) -> str:
    alpha = int(max(0.3, min(1.0, opacity)) * 255)
    ink = ink_on(c["accent"])
    bg = c["bg"].lstrip("#")
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    return f"""
    QWidget#gamebuddy-window, QWidget#buddy-avatar {{ background: transparent; border: none; }}
    QWidget#root {{
        background: rgba({r},{g},{b},{alpha});
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.06);
    }}
    QWidget {{ color: {c["text"]}; font-size: {font_size}px; font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif; }}
    QLabel#title {{ font-weight: 600; font-size: {font_size + 2}px; }}
    QLabel#status {{ color: {c["muted"]}; }}
    QLabel#hint {{ color: {c["muted"]}; font-size: {font_size - 2}px; }}
    QWidget#orb {{ background: rgba({r},{g},{b},{opacity}); border-radius: 48px; border: 1px solid rgba(255,255,255,0.06); }}
    QLabel#caption {{ color: {c["text"]}; font-size: {font_size}px; }}
    QLabel#bubble_user {{ background: {c["user"]}; border-radius: 10px; padding: 8px 10px; }}
    QLabel#bubble_bro {{ background: {c["bro"]}; border-radius: 10px; padding: 8px 10px; }}
    QLabel#bubble_coach {{ background: {c["panel2"]}; border-left: 3px solid {c["accent2"]}; border-radius: 6px; padding: 8px 10px; }}
    QLabel#bubble_error {{ background: {c["panel2"]}; border-left: 3px solid {c["danger"]}; border-radius: 6px; padding: 8px 10px; }}
    QFrame#pin {{ background: {c["panel"]}; border-radius: 10px; border: 1px solid {c["accent"]}; }}
    QTextBrowser {{ background: transparent; border: none; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ width: 6px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18); border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QLineEdit {{ background: {c["panel2"]}; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 8px 10px; }}
    QLineEdit:focus {{ border-color: {c["accent"]}; }}
    QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 4px 6px; color: {c["muted"]}; }}
    QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {c["text"]}; }}
    QToolButton:checked {{ color: {c["accent"]}; background: rgba(255,255,255,0.08); }}
    QToolButton#mic {{ background: {c["accent"]}; color: {ink}; border-radius: 18px; padding: 6px; font-size: {font_size + 3}px; }}
    QToolButton#mic:pressed, QToolButton#mic:checked {{ background: {c["danger"]}; color: white; }}
    QPushButton {{ background: {c["accent"]}; color: {ink}; border: none; border-radius: 8px; padding: 6px 12px; }}
    QPushButton:hover {{ background: {c["accent"]}; }}
    QPushButton#secondary {{ background: {c["panel2"]}; color: {c["text"]}; }}
    QProgressBar {{ background: {c["panel2"]}; border: none; border-radius: 2px; height: 4px; }}
    QProgressBar::chunk {{ background: {c["accent2"]}; border-radius: 2px; }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c["panel2"]}; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 4px 8px; }}
    QListWidget {{ background: {c["panel"]}; border-radius: 8px; }}
    QListWidget::item {{ padding: 6px; }}
    QListWidget::item:selected {{ background: {c["accent"]}; color: {ink}; }}
    QDialog, QWizard {{ background: {c["bg"]}; }}
    QMenu {{ background: {c["panel"]}; border: 1px solid rgba(255,255,255,0.08); }}
    QMenu::item:selected {{ background: {c["accent"]}; color: {ink}; }}
    """
