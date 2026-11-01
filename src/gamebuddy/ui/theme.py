"""Dark, translucent look. Colors can follow the current Omarchy theme when available."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT = {
    "bg": "#15171c",
    "panel": "#1d2027",
    "panel2": "#262a33",
    "text": "#e8e9ed",
    "muted": "#9aa0ad",
    "accent": "#8b5cf6",
    "accent2": "#22c55e",
    "danger": "#ef4444",
    "user": "#2b2f3a",
    "bro": "#2a2340",
}


def omarchy_colors() -> dict[str, str]:
    """Best-effort read of ~/.config/omarchy/current/theme/colors.toml (or alacritty.toml)."""
    base = Path.home() / ".config" / "omarchy" / "current" / "theme"
    colors = dict(DEFAULT)
    for name in ("colors.toml", "alacritty.toml"):
        path = base / name
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        found = {k: v for k, v in re.findall(r'^\s*(\w+)\s*=\s*"(#[0-9a-fA-F]{6})"', text, re.M)}
        if "background" in found:
            colors["bg"] = found["background"]
            colors["panel"] = found.get("background", colors["panel"])
        if "foreground" in found:
            colors["text"] = found["foreground"]
        for key in ("magenta", "blue", "cyan"):
            if key in found:
                colors["accent"] = found[key]
                break
        if "green" in found:
            colors["accent2"] = found["green"]
        if "red" in found:
            colors["danger"] = found["red"]
        break
    return colors


def stylesheet(c: dict[str, str], font_size: int = 13, opacity: float = 0.94) -> str:
    alpha = int(max(0.3, min(1.0, opacity)) * 255)
    bg = c["bg"].lstrip("#")
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    return f"""
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
    QToolButton#mic {{ background: {c["accent"]}; color: white; border-radius: 18px; padding: 6px; font-size: {font_size + 3}px; }}
    QToolButton#mic:pressed, QToolButton#mic:checked {{ background: {c["danger"]}; }}
    QPushButton {{ background: {c["accent"]}; color: white; border: none; border-radius: 8px; padding: 6px 12px; }}
    QPushButton:hover {{ background: {c["accent"]}; }}
    QPushButton#secondary {{ background: {c["panel2"]}; color: {c["text"]}; }}
    QProgressBar {{ background: {c["panel2"]}; border: none; border-radius: 2px; height: 4px; }}
    QProgressBar::chunk {{ background: {c["accent2"]}; border-radius: 2px; }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c["panel2"]}; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 4px 8px; }}
    QListWidget {{ background: {c["panel"]}; border-radius: 8px; }}
    QListWidget::item {{ padding: 6px; }}
    QListWidget::item:selected {{ background: {c["accent"]}; color: white; }}
    QDialog, QWizard {{ background: {c["bg"]}; }}
    QMenu {{ background: {c["panel"]}; border: 1px solid rgba(255,255,255,0.08); }}
    QMenu::item:selected {{ background: {c["accent"]}; }}
    """
