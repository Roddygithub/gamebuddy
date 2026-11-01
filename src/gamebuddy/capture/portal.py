"""GNOME / KDE Wayland: whole-screen capture without wlr-screencopy.

Order of preference:
  1. ``spectacle`` (KDE)            — silent background capture, no prompt
  2. ``gnome-screenshot`` (GNOME)   — allow-listed by the Shell, no prompt
  3. org.freedesktop.portal.Screenshot over D-Bus (jeepney) — works everywhere a
     portal runs; GNOME/KDE ask once and can remember the permission.

No window list is available on these desktops, so the whole screen is sent and the
overlay is masked by its absolute geometry.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from gamebuddy.capture.base import CaptureBackend, CaptureError, Rect, WindowInfo, have, run

SCREEN = WindowInfo(id="output", title="Whole screen", app_id="", rect=Rect(0, 0, 0, 0))


def desktop_name() -> str:
    return os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


class PortalBackend(CaptureBackend):
    name = "portal"

    def __init__(self) -> None:
        self._counter = 0

    def available(self) -> bool:
        return have("spectacle") or have("gnome-screenshot") or _jeepney_ok()

    def list_windows(self) -> list[WindowInfo]:
        return [SCREEN]

    def capture(self, window: WindowInfo) -> bytes:
        with tempfile.TemporaryDirectory(prefix="gamebuddy-shot-") as tmp:
            out = Path(tmp) / "screen.png"
            if have("spectacle") and "KDE" in desktop_name():
                run(["spectacle", "-b", "-n", "-f", "-o", str(out)], timeout=15)
            elif have("gnome-screenshot") and "GNOME" in desktop_name():
                run(["gnome-screenshot", "-f", str(out)], timeout=15)
            else:
                return self._portal_screenshot()
            if not out.is_file() or out.stat().st_size == 0:
                raise CaptureError("screenshot tool produced no file")
            return out.read_bytes()

    # ---- xdg-desktop-portal ----------------------------------------------------
    def _portal_screenshot(self, timeout: float = 30.0) -> bytes:
        try:
            from jeepney import DBusAddress, MatchRule, new_method_call
            from jeepney.bus_messages import message_bus
            from jeepney.io.blocking import open_dbus_connection
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise CaptureError("pip install jeepney for portal screenshots") from exc

        self._counter += 1
        token = f"gamebuddy{os.getpid()}_{self._counter}"
        conn = open_dbus_connection(bus="SESSION")
        try:
            sender = conn.unique_name[1:].replace(".", "_")
            request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
            rule = MatchRule(
                type="signal",
                interface="org.freedesktop.portal.Request",
                member="Response",
                path=request_path,
            )
            conn.send_and_get_reply(message_bus.AddMatch(rule))
            portal = DBusAddress(
                "/org/freedesktop/portal/desktop",
                bus_name="org.freedesktop.portal.Desktop",
                interface="org.freedesktop.portal.Screenshot",
            )
            options = {"handle_token": ("s", token), "interactive": ("b", False), "modal": ("b", False)}
            with conn.filter(rule) as queue:
                conn.send_and_get_reply(new_method_call(portal, "Screenshot", "sa{sv}", ("", options)))
                deadline = time.monotonic() + timeout
                msg = conn.recv_until_filtered(queue, timeout=max(1.0, deadline - time.monotonic()))
            code, results = msg.body
            return read_portal_result(code, results)
        finally:
            conn.close()


def read_portal_result(code: int, results: dict) -> bytes:
    """Decode a portal Response body: 0 = ok with results['uri'] = ('s', 'file:///…png')."""
    if code != 0:
        raise CaptureError("portal_denied" if code == 1 else "portal_failed")
    uri = results.get("uri")
    uri = uri[1] if isinstance(uri, tuple) else uri
    if not uri or not str(uri).startswith("file://"):
        raise CaptureError("portal returned no file")
    from urllib.parse import unquote, urlparse

    path = Path(unquote(urlparse(str(uri)).path))
    try:
        return path.read_bytes()
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _jeepney_ok() -> bool:
    try:
        import jeepney  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS") or os.environ.get("XDG_RUNTIME_DIR"))
