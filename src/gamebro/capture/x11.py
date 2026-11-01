"""X11 backend: wmctrl/xdotool for the list, ImageMagick `import`, maim or Pillow for pixels."""

from __future__ import annotations

import io
import re

from gamebro.capture.base import CaptureBackend, CaptureError, Rect, WindowInfo, have, run

_WMCTRL_RE = re.compile(
    r"^(0x[0-9a-f]+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*(.*)$"
)


class X11Backend(CaptureBackend):
    name = "x11"

    def available(self) -> bool:
        return have("wmctrl") or have("xdotool")

    def list_windows(self) -> list[WindowInfo]:
        if have("wmctrl"):
            out: list[WindowInfo] = []
            for line in run(["wmctrl", "-lGx"]).splitlines():
                m = _WMCTRL_RE.match(line.strip())
                if not m:
                    continue
                wid, desk, x, y, w, h, cls, _host, title = m.groups()
                if int(desk) == -1 or int(w) < 2:
                    continue
                out.append(
                    WindowInfo(
                        id=wid,
                        title=title,
                        app_id=cls.split(".")[-1],
                        rect=Rect(int(x), int(y), int(w), int(h)),
                        workspace=desk,
                    )
                )
            return out
        ids = run(["xdotool", "search", "--onlyvisible", "--name", "."]).split()
        out = []
        for wid in ids:
            try:
                info = run(["xwininfo", "-id", wid])
            except CaptureError:
                continue
            fields = dict(re.findall(r"\s*([A-Za-z -]+?):\s+(.+)", info))
            title_m = re.search(r'xwininfo: Window id: \S+ "(.*)"', info)
            try:
                rect = Rect(
                    int(fields.get("Absolute upper-left X", 0)),
                    int(fields.get("Absolute upper-left Y", 0)),
                    int(fields.get("Width", 0)),
                    int(fields.get("Height", 0)),
                )
            except ValueError:
                continue
            out.append(WindowInfo(id=wid, title=title_m.group(1) if title_m else wid, app_id="", rect=rect))
        return out

    def capture(self, window: WindowInfo) -> bytes:
        current = self.find_window(window.id) or window
        if have("import"):
            return run(["import", "-window", current.id, "png:-"], binary=True)  # type: ignore[return-value]
        if have("maim"):
            return run(["maim", "-i", current.id], binary=True)  # type: ignore[return-value]
        from PIL import ImageGrab

        r = current.rect
        img = ImageGrab.grab(bbox=(r.x, r.y, r.x + r.w, r.y + r.h))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
