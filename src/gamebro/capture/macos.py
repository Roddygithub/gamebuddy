"""macOS backend — development convenience only (the product targets Linux)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from gamebro.capture.base import CaptureBackend, CaptureError, Rect, WindowInfo, run


class MacOSBackend(CaptureBackend):
    name = "macos"

    def list_windows(self) -> list[WindowInfo]:
        try:
            from Quartz import (  # type: ignore[import-not-found]
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListExcludeDesktopElements,
                kCGWindowListOptionOnScreenOnly,
            )
        except ImportError:
            return [WindowInfo(id="screen", title="Whole screen", app_id="", rect=Rect(0, 0, 0, 0))]
        infos = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID
        )
        out: list[WindowInfo] = []
        for info in infos or []:
            if info.get("kCGWindowLayer", 0) != 0:
                continue
            b = info.get("kCGWindowBounds", {})
            if b.get("Width", 0) < 50:
                continue
            out.append(
                WindowInfo(
                    id=str(info.get("kCGWindowNumber")),
                    title=info.get("kCGWindowName") or info.get("kCGWindowOwnerName", ""),
                    app_id=info.get("kCGWindowOwnerName", ""),
                    rect=Rect(
                        int(b.get("X", 0)),
                        int(b.get("Y", 0)),
                        int(b.get("Width", 0)),
                        int(b.get("Height", 0)),
                    ),
                )
            )
        return out

    def capture(self, window: WindowInfo) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot.png"
            cmd = ["screencapture", "-x", "-t", "png"]
            if window.id not in ("screen", ""):
                cmd += ["-l", window.id]
            cmd.append(str(path))
            run(cmd, timeout=10)
            if not path.exists():
                raise CaptureError("screencapture produced no file")
            return path.read_bytes()
