"""sway / generic wlroots backends (grim)."""

from __future__ import annotations

import json
from typing import Any

from gamebuddy.capture.base import CaptureBackend, CaptureError, Rect, WindowInfo, have, run


class SwayBackend(CaptureBackend):
    name = "sway"

    def available(self) -> bool:
        return have("swaymsg") and have("grim")

    def list_windows(self) -> list[WindowInfo]:
        tree = json.loads(run(["swaymsg", "-t", "get_tree"]))
        out: list[WindowInfo] = []

        def walk(node: dict[str, Any], ws: str) -> None:
            if node.get("type") == "workspace":
                ws = node.get("name", "")
            if node.get("type") in ("con", "floating_con") and (node.get("app_id") or node.get("window")):
                if node.get("visible"):
                    r = node.get("rect", {})
                    out.append(
                        WindowInfo(
                            id=str(node.get("id")),
                            title=node.get("name", "") or "",
                            app_id=node.get("app_id")
                            or (node.get("window_properties") or {}).get("class", "")
                            or "",
                            rect=Rect(r.get("x", 0), r.get("y", 0), r.get("width", 0), r.get("height", 0)),
                            workspace=ws,
                            fullscreen=bool(node.get("fullscreen_mode")),
                        )
                    )
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                walk(child, ws)

        walk(tree, "")
        return out

    def capture(self, window: WindowInfo) -> bytes:
        current = self.find_window(window.id)
        if current is None:
            raise CaptureError("window_lost")
        r = current.rect
        return run(["grim", "-g", f"{r.x},{r.y} {r.w}x{r.h}", "-t", "png", "-"], binary=True)  # type: ignore[return-value]


class GrimOutputBackend(CaptureBackend):
    """Unknown Wayland compositor: no window list, whole output only."""

    name = "wlroots"

    def available(self) -> bool:
        return have("grim")

    def list_windows(self) -> list[WindowInfo]:
        return [WindowInfo(id="output", title="Whole screen", app_id="", rect=Rect(0, 0, 0, 0))]

    def capture(self, window: WindowInfo) -> bytes:
        return run(["grim", "-t", "png", "-"], binary=True)  # type: ignore[return-value]
