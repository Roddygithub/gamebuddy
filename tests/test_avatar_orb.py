"""Avatar states and orb/panel switching (offscreen)."""

import pytest
from PySide6.QtWidgets import QApplication

from gamebuddy.i18n import Translator
from gamebuddy.ui.avatar import Avatar, state_for_status
from gamebuddy.ui.widget import ORB_H, ORB_W, BuddyWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_status_to_state():
    assert state_for_status("listening") == "listening"
    assert state_for_status("searching") == "thinking"
    assert state_for_status("speaking") == "speaking"
    assert state_for_status("ready") == "idle"


def test_avatar_paints_every_state(qapp, tmp_path):
    a = Avatar(64, animate=False)
    a.set_colors({"accent": "#ff8800", "accent2": "#00ff88"})
    for state in ("idle", "listening", "thinking", "speaking"):
        a.set_state(state)
        a.set_level(0.1)
        img = a.grab().toImage()
        assert img.width() == 64
        assert any(img.pixelColor(x, 32).alpha() > 0 for x in range(10, 54)), state
    a._tick()  # animation step must not raise


def test_orb_mode_switch_and_captions(qapp):
    w = BuddyWidget(Translator("fr"), "Buddy", "ALT, V", 420, 640, mode="orb")
    w.show()
    assert w.mode == "orb" and w.width() == ORB_W and w.height() == ORB_H
    assert not w.root.isVisible() and w.orb_root.isVisible()
    w.add_bubble("**Salut** — soigne-toi d'abord", "bro")
    assert w.caption.text() == "Salut — soigne-toi d'abord"
    w.set_status("listening")
    assert w.avatar.state == "listening" and w.orb_avatar.state == "listening"
    w.begin_stream()
    w.stream_delta("Va à gauche")
    w.end_stream("Va à gauche, puis monte.")
    assert w.caption.text().startswith("Va à gauche")
    # pinned content opens the panel
    w.show_pin("Checklist", "- item")
    assert w.mode == "panel" and w.root.isVisible() and not w.orb_root.isVisible()
    assert w.width() == 420 and w.height() == 640
    w.set_mode("orb")
    assert w.mode == "orb"
    long = "x" * 500
    w.set_caption(long)
    assert len(w.caption.text()) <= 140 and w.caption.text().endswith("…")
    w.close()


def test_panel_default_when_configured(qapp):
    w = BuddyWidget(Translator("en"), "Buddy", "ALT, V", 400, 500, mode="panel")
    assert w.mode == "panel" and w.orb_root.isHidden()
    w.close()
