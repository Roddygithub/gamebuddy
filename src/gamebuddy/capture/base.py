"""Window listing + screenshot of the selected game window.

Backends are chosen from the session environment. Each backend returns PNG
bytes for a window; ``to_jpeg`` downsizes/compresses and optionally masks the
rectangle where our own overlay sits so the model never sees the widget.
"""

from __future__ import annotations

import io
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gamebuddy.paths import data_dir


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def intersect(self, other: Rect) -> Rect | None:
        x1, y1 = max(self.x, other.x), max(self.y, other.y)
        x2, y2 = min(self.x + self.w, other.x + other.w), min(self.y + self.h, other.y + other.h)
        if x2 <= x1 or y2 <= y1:
            return None
        return Rect(x1, y1, x2 - x1, y2 - y1)


@dataclass(frozen=True)
class WindowInfo:
    id: str  # backend-specific stable identity (Hyprland address, X11 id…)
    title: str
    app_id: str
    rect: Rect
    workspace: str = ""
    fullscreen: bool = False
    capture_id: str = ""  # foreign toplevel identifier for direct window capture

    @property
    def label(self) -> str:
        app = f" ({self.app_id})" if self.app_id and self.app_id.lower() not in self.title.lower() else ""
        return f"{self.title or '(untitled)'}{app}"


def remembered_window_file() -> Path:
    return data_dir() / "window.json"


def remember_window(window: WindowInfo | None, path: Path | None = None) -> None:
    """Persist the chosen window's identity so the next start can re-select it."""
    path = path or remembered_window_file()
    try:
        if window is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"app_id": window.app_id, "title": window.title}, ensure_ascii=False))
    except OSError:
        pass  # window memory is a convenience; never fail a selection over it


def load_remembered_window(path: Path | None = None) -> tuple[str, str]:
    """(app_id, title) of the last selected window, or ("", "")."""
    path = path or remembered_window_file()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("app_id") or ""), str(data.get("title") or "")


def find_same_window(windows: list[WindowInfo], app_id: str, title: str) -> WindowInfo | None:
    """Re-find a remembered window without guessing.

    Prefers an exact title match, falls back to the app's only window (titles
    change with the game's menu), and returns None when several windows share
    the app id and none carries the remembered title.
    """
    if not app_id or app_id.lower() == "gamebuddy":
        return None
    same_app = [w for w in windows if w.app_id == app_id]
    for w in same_app:
        if w.title == title:
            return w
    return same_app[0] if len(same_app) == 1 else None


class CaptureBackend:
    name = "none"

    def list_windows(self) -> list[WindowInfo]:
        return []

    def remembered_window(self) -> WindowInfo | None:
        app_id, title = load_remembered_window()
        return find_same_window(self.list_windows(), app_id, title) if app_id else None

    def find_window(self, window_id: str) -> WindowInfo | None:
        for w in self.list_windows():
            if w.id == window_id:
                return w
        return None

    def capture(self, window: WindowInfo) -> bytes:
        raise CaptureError("capture not supported in this session")

    def own_windows(self, app_class: str = "gamebuddy") -> list[WindowInfo]:
        return [w for w in self.list_windows() if w.app_id.lower() == app_class]

    def available(self) -> bool:
        return True


def run(cmd: list[str], timeout: float = 8.0, binary: bool = False) -> bytes | str:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise CaptureError(f"missing tool: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CaptureError(f"{cmd[0]} timed out") from exc
    if proc.returncode != 0:
        raise CaptureError(f"{cmd[0]} failed: {proc.stderr.decode(errors='replace').strip()[:200]}")
    return proc.stdout if binary else proc.stdout.decode(errors="replace")


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def detect_session() -> str:
    if platform.system() == "Darwin":
        return "macos"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and have("hyprctl"):
        return "hyprland"
    if os.environ.get("SWAYSOCK") and have("swaymsg"):
        return "sway"
    if os.environ.get("WAYLAND_DISPLAY"):
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        if any(d in desktop for d in ("GNOME", "KDE", "COSMIC", "UBUNTU", "PANTHEON", "DEEPIN")):
            return "portal"
        return "wlroots" if have("grim") else "portal"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "none"


def get_backend(preferred: str = "auto") -> CaptureBackend:
    kind = detect_session() if preferred in ("", "auto") else preferred
    if kind == "hyprland":
        from gamebuddy.capture.hyprland import HyprlandBackend

        return HyprlandBackend()
    if kind == "sway":
        from gamebuddy.capture.sway import SwayBackend

        return SwayBackend()
    if kind == "wlroots":
        from gamebuddy.capture.sway import GrimOutputBackend

        return GrimOutputBackend()
    if kind == "portal":
        from gamebuddy.capture.portal import PortalBackend

        return PortalBackend()
    if kind == "x11":
        from gamebuddy.capture.x11 import X11Backend

        return X11Backend()
    if kind == "macos":
        from gamebuddy.capture.macos import MacOSBackend

        return MacOSBackend()
    return CaptureBackend()


def to_jpeg(png: bytes, max_width: int = 1280, quality: int = 72, mask: Rect | None = None) -> bytes:
    """Downscale + compress a PNG screenshot; optionally black out ``mask`` (window-relative coords)."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(png)).convert("RGB")
    if mask and mask.w > 0 and mask.h > 0:
        ImageDraw.Draw(img).rectangle([mask.x, mask.y, mask.x + mask.w, mask.y + mask.h], fill=(16, 16, 16))
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(1, int(img.height * ratio))), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def overlay_mask(window: WindowInfo, overlay: Rect | None) -> Rect | None:
    """Overlay rect in window-relative coordinates, if they overlap."""
    if overlay is None:
        return None
    if window.rect.w == 0 and window.rect.h == 0:  # whole-screen backends: absolute == relative
        return overlay
    inter = window.rect.intersect(overlay)
    if inter is None:
        return None
    return Rect(inter.x - window.rect.x, inter.y - window.rect.y, inter.w, inter.h)
