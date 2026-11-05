import json

import pytest

from gamebuddy.capture import CaptureError, Rect, WindowInfo, hyprland


@pytest.mark.parametrize("stable_id", ["game-stable-id", ""])
def test_capture_targets_window_not_the_visible_desktop(monkeypatch, stable_id):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "hyprctl":
            return json.dumps(
                [
                    {
                        "address": "0x123",
                        "title": "Game",
                        "class": "game",
                        "stableId": stable_id,
                        "at": [12, 38],
                        "size": [1200, 900],
                        "workspace": {"id": 3, "name": "3"},
                    }
                ]
            )
        assert command == ["grim", "-T", stable_id, "-t", "png", "-"]
        return b"window-pixels"

    monkeypatch.setattr(hyprland, "run", run)
    backend = hyprland.HyprlandBackend()
    window = WindowInfo("0x123", "Game", "game", Rect(0, 0, 10, 10))
    if stable_id:
        assert backend.capture(window) == b"window-pixels"
    else:
        with pytest.raises(CaptureError, match="window_capture_unavailable"):
            backend.capture(window)
        assert len(commands) == 1


def test_failed_window_capture_never_falls_back_to_screen(monkeypatch):
    backend = hyprland.HyprlandBackend()
    window = WindowInfo("0x123", "Game", "game", Rect(0, 0, 10, 10), capture_id="game-id")
    monkeypatch.setattr(backend, "find_window", lambda _: window)
    commands = []

    def fail(command, **kwargs):
        commands.append(command)
        raise CaptureError("grim: direct capture unavailable")

    monkeypatch.setattr(hyprland, "run", fail)
    with pytest.raises(CaptureError):
        backend.capture(window)
    assert commands == [["grim", "-T", "game-id", "-t", "png", "-"]]
