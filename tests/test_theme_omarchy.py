"""The look follows the selected Omarchy theme, not a built-in palette."""

from __future__ import annotations

from gamebuddy.ui import theme

GRUVBOX = """\
accent = "#7daea3"
foreground = "#d4be98"
background = "#282828"

color0 = "#3c3836"
color1 = "#ea6962"
color2 = "#a9b665"
color8 = "#928374"
"""


def test_palette_follows_the_active_theme(tmp_path, monkeypatch):
    (tmp_path / "colors.toml").write_text(GRUVBOX)
    monkeypatch.setattr(theme, "THEME_DIR", tmp_path)

    colors = theme.omarchy_colors()

    assert theme.theme_file() == tmp_path / "colors.toml"
    assert colors["bg"] == "#282828"
    assert colors["text"] == "#d4be98"
    assert colors["panel"] == "#3c3836"
    assert colors["muted"] == "#928374"
    assert colors["accent"] == "#7daea3"  # accent, not the default violet
    assert colors["accent2"] == "#a9b665"
    assert colors["danger"] == "#ea6962"
    assert colors["bro"] not in ("#282828", "#7daea3")  # tinted, not blended flat


def test_falls_back_to_the_builtin_palette_without_a_theme(tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "THEME_DIR", tmp_path)
    assert theme.omarchy_colors() == theme.DEFAULT
