"""Hyprland backend: `hyprctl -j clients` for the window list, `grim -g` for pixels."""

from __future__ import annotations

import json

from gamebro.capture.base import CaptureBackend, CaptureError, Rect, WindowInfo, have, run


class HyprlandBackend(CaptureBackend):
    name = "hyprland"

    def available(self) -> bool:
        return have("hyprctl") and have("grim")

    def list_windows(self) -> list[WindowInfo]:
        raw = run(["hyprctl", "-j", "clients"])
        try:
            clients = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CaptureError("hyprctl returned invalid JSON") from exc
        out: list[WindowInfo] = []
        for c in clients:
            if not c.get("mapped", True) or c.get("hidden"):
                continue
            at, size = c.get("at", [0, 0]), c.get("size", [0, 0])
            if size[0] <= 1 or size[1] <= 1:
                continue
            ws = c.get("workspace") or {}
            fs = c.get("fullscreen")
            out.append(
                WindowInfo(
                    id=str(c.get("address", "")),
                    title=c.get("title", "") or "",
                    app_id=c.get("class", "") or c.get("initialClass", "") or "",
                    rect=Rect(int(at[0]), int(at[1]), int(size[0]), int(size[1])),
                    workspace=str(ws.get("name", ws.get("id", ""))),
                    fullscreen=bool(fs) if isinstance(fs, bool) else int(fs or 0) > 0,
                )
            )
        return out

    def capture(self, window: WindowInfo) -> bytes:
        current = self.find_window(window.id)
        if current is None:
            raise CaptureError("window_lost")
        r = current.rect
        geometry = f"{r.x},{r.y} {r.w}x{r.h}"
        return run(["grim", "-g", geometry, "-t", "png", "-"], binary=True, timeout=6.0)  # type: ignore[return-value]
