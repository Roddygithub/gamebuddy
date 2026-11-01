"""Generate compositor bindings and update only GameBuddy-owned marked blocks."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from gamebuddy.config import HotkeyConfig

BEGIN = "GameBuddy shortcuts begin"
END = "GameBuddy shortcuts end"


def sequence_to_binding(sequence: str) -> str:
    parts = sequence.split("+")
    key = parts.pop().strip()
    mods = [
        {"Ctrl": "CTRL", "Alt": "ALT", "Shift": "SHIFT", "Meta": "SUPER"}.get(p, p.upper()) for p in parts
    ]
    if not re.fullmatch(r"[A-Za-z0-9_]+", key) or any(
        m not in ("CTRL", "ALT", "SHIFT", "SUPER") for m in mods
    ):
        raise ValueError("Choose a letter, number, function key or named key with optional modifiers.")
    return f"{' '.join(mods)}, {key.upper()}"


def binding_to_sequence(binding: str) -> str:
    mods, _, key = binding.partition(",")
    return "+".join(
        [{"CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "SUPER": "Meta"}.get(m, m) for m in mods.split()]
        + [key.strip()]
    )


def hypr_bindings(cfg: HotkeyConfig, lua: bool) -> str:
    prefix = "--" if lua else "#"
    lines = [f"{prefix} {BEGIN}"]

    def bind(key, command, release=False):
        if lua:
            combo = (
                binding_to_sequence(key)
                .replace("Meta", "SUPER")
                .replace("Ctrl", "CTRL")
                .replace("Alt", "ALT")
                .replace("Shift", "SHIFT")
            )
            options = ", { release = true }" if release else ""
            lines.append(f"hl.bind({json.dumps(combo)}, hl.dsp.exec_cmd({json.dumps(command)}){options})")
        else:
            lines.append(f"{'bindr' if release else 'bind'} = {key}, exec, {command}")

    bind(cfg.push_to_talk, "gamebuddy ptt toggle" if cfg.mode == "toggle" else "gamebuddy ptt start")
    if cfg.mode != "toggle":
        bind(cfg.push_to_talk, "gamebuddy ptt stop", release=True)
    bind(cfg.toggle_widget, "gamebuddy toggle")
    lines.append(f"{prefix} {END}")
    return "\n".join(lines) + "\n"


def apply_hypr_bindings(cfg: HotkeyConfig, previous: HotkeyConfig | None = None) -> bool:
    """False means the compositor snippet is managed outside the app."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return False
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hypr"
    paths = [
        p for p in (root / "gamebuddy.lua", root / "gamebuddy.conf") if p.is_file() and BEGIN in p.read_text()
    ]
    if not paths:
        return False
    old_keys = {previous.push_to_talk, previous.toggle_widget} if previous else set()
    current = subprocess.run(
        ["hyprctl", "-j", "binds"], capture_output=True, text=True, check=True, timeout=5
    )
    for binding in (cfg.push_to_talk, cfg.toggle_widget):
        if binding in old_keys:
            continue
        mods, _, key = binding.partition(",")
        mask = sum({"SUPER": 64, "ALT": 8, "CTRL": 4, "SHIFT": 1}[m] for m in mods.split())
        for item in json.loads(current.stdout):
            if item.get("modmask") == mask and str(item.get("key", "")).upper() == key.strip().upper():
                raise ValueError(f"Raccourci déjà utilisé : {binding} ({item.get('description', '')})")
    originals = {p: p.read_text() for p in paths}
    try:
        for path, text in originals.items():
            prefix = "--" if path.suffix == ".lua" else "#"
            pattern = rf"{re.escape(prefix)} {BEGIN}.*?{re.escape(prefix)} {END}\n?"
            replacement = hypr_bindings(cfg, path.suffix == ".lua")
            if not re.search(pattern, text, re.S):
                raise ValueError(f"Incomplete shortcut block in {path}")
            Path(str(path) + ".bak").write_text(text)
            path.write_text(re.sub(pattern, lambda _m, value=replacement: value, text, flags=re.S))
        subprocess.run(["hyprctl", "reload"], capture_output=True, check=True, timeout=5)
        errors = subprocess.run(
            ["hyprctl", "configerrors"], capture_output=True, text=True, check=True, timeout=5
        )
        if errors.stdout.strip():
            raise ValueError(errors.stdout.strip())
    except Exception:
        for path, text in originals.items():
            path.write_text(text)
        subprocess.run(["hyprctl", "reload"], capture_output=True, check=False, timeout=5)
        raise
    return True
