"""A cached frame must remain bound to the selected window identity."""

import io
import threading
import time
from types import SimpleNamespace

from PIL import Image

from gamebuddy.capture import Rect, WindowInfo
from gamebuddy.capture.base import CaptureError
from gamebuddy.config import CaptureConfig
from gamebuddy.ui.app import GameBuddyApp


def _png(color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(out, "PNG")
    return out.getvalue()


class _Backend:
    name = "hyprland"

    def __init__(self, current: WindowInfo):
        self.current = current
        self.captures = 0
        self.on_capture = None

    def find_window(self, _window_id: str) -> WindowInfo | None:
        return self.current

    def capture(self, window: WindowInfo) -> bytes:
        self.captures += 1
        if self.on_capture:
            self.on_capture()
        return _png((20, 30, 40))


def _app(window: WindowInfo) -> GameBuddyApp:
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._shot_lock = threading.Lock()
    app._shot = None
    app.window = window
    app.cfg = SimpleNamespace(capture=CaptureConfig(reuse_ms=250))
    app.backend = _Backend(window)
    app._overlay_rect = lambda: None
    return app


def test_reused_hyprland_address_fails_closed_when_toplevel_changes():
    selected = WindowInfo("0x123", "Game", "game", Rect(0, 0, 32, 32), capture_id="old")
    replacement = WindowInfo("0x123", "Game", "game", Rect(0, 0, 32, 32), capture_id="new")
    app = _app(selected)
    app._shot = (time.monotonic(), selected.id, selected.capture_id, selected.app_id, b"old frame")
    app.backend.current = replacement

    frame = app.capture_game()

    assert frame is None
    assert app.backend.captures == 0
    assert app._shot is None


def test_replaced_window_fails_closed_without_a_usable_cache():
    selected = WindowInfo("0x123", "Game", "game", Rect(0, 0, 32, 32), capture_id="old")
    replacement = WindowInfo("0x123", "Game", "game", Rect(0, 0, 32, 32), capture_id="new")
    for fresh, expired in ((True, False), (False, True)):
        app = _app(selected)
        app.backend.current = replacement
        if expired:
            app._shot = (time.monotonic() - 1, selected.id, selected.capture_id, selected.app_id, b"old")

        assert app.capture_game(fresh=fresh) is None
        assert app.backend.captures == 0
        assert app._shot is None


def test_recent_frame_is_reused_for_the_same_window_identity():
    selected = WindowInfo("1", "Game", "game", Rect(0, 0, 32, 32), capture_id="same")
    app = _app(selected)
    app._shot = (time.monotonic(), selected.id, selected.capture_id, selected.app_id, b"cached frame")

    assert app.capture_game() == b"cached frame"
    assert app.backend.captures == 0


def test_frame_is_discarded_if_selection_changes_during_capture():
    selected = WindowInfo("1", "Game A", "a", Rect(0, 0, 32, 32), capture_id="a")
    other = WindowInfo("2", "Game B", "b", Rect(0, 0, 32, 32), capture_id="b")
    app = _app(selected)
    app.backend.on_capture = lambda: setattr(app, "window", other)

    assert app.capture_game(fresh=True) is None
    assert app._shot is None


def test_old_window_lost_notification_does_not_clear_new_selection():
    selected = WindowInfo("1", "New game", "new", Rect(0, 0, 32, 32), capture_id="new")
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._shot_lock = threading.Lock()
    app.window = selected
    app._shot = (time.monotonic(), selected.id, selected.capture_id, selected.app_id, b"new frame")

    app._on_window_lost("old", "old-capture", "old-app")

    assert app.window is selected
    assert app._shot[4] == b"new frame"


def test_window_lost_during_old_capture_does_not_emit_for_new_selection():
    selected = WindowInfo("1", "Old game", "old", Rect(0, 0, 32, 32), capture_id="old")
    other = WindowInfo("2", "New game", "new", Rect(0, 0, 32, 32), capture_id="new")
    app = _app(selected)
    emitted = []
    app.bridge = SimpleNamespace(window_lost=SimpleNamespace(emit=emitted.append))

    def lost(_window):
        app.window = other
        raise CaptureError("window_lost")

    app.backend.capture = lost

    assert app.capture_game(fresh=True) is None
    assert app.window is other
    assert emitted == []
