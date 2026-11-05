"""Offscreen smoke test of the full app with a scripted provider."""

import os

import pytest

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_tray_exposes_window_picker(qapp, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    from gamebuddy.config import Config
    from gamebuddy.ui.app import GameBuddyApp

    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    cfg = Config()
    cfg.capture.backend = "none"
    gb = GameBuddyApp(cfg)
    opened = []
    monkeypatch.setattr(gb, "pick_window", lambda: opened.append(True))
    try:
        gb._setup_tray()
        action = next(a for a in gb.tray.contextMenu().actions() if a.text() == gb.tr("pick_window"))
        action.trigger()
        assert opened == [True]
    finally:
        gb.tray.hide()
        gb.widget.close()
        gb.store.close()


def test_app_text_roundtrip(qapp, tmp_path, fake_provider, monkeypatch):
    from PySide6.QtCore import QEventLoop, QTimer

    from gamebuddy.config import Config
    from gamebuddy.ui.app import GameBuddyApp

    cfg = Config()
    cfg.general.onboarding_done = True
    cfg.general.language = "fr"
    cfg.speech.tts = "none"
    cfg.llm.web_search = False
    cfg.capture.backend = "none"
    gb = GameBuddyApp(cfg)
    provider = fake_provider(
        [
            {
                "text": "",
                "calls": [
                    (
                        "c1",
                        "pin_content",
                        {
                            "title": "Checklist",
                            "markdown": "- [ ] potions\n- [ ] repair",
                            "kind": "checklist",
                        },
                    )
                ],
            },
            {"text": "Voilà ta **checklist**, elle reste épinglée."},
        ]
    )
    gb.kin._provider = provider
    gb.start()
    try:
        assert gb.widget.isVisible()
        gb.ask_text("épingle une checklist")
        loop = QEventLoop()
        QTimer.singleShot(3000, loop.quit)
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(
            lambda: loop.quit() if not gb.kin.busy and gb.widget._streaming_label is None else None
        )
        timer.start()
        loop.exec()
        assert gb.widget.pin_frame.isVisible()
        assert "Checklist" in gb.widget.pin_title.text()
        assert gb.widget.status.text() == "Prêt quand tu veux"
        # IPC path (thread-safe handler) → queued to GUI thread
        resp = gb._handle_command_threadsafe({"cmd": "status"})
        assert resp["window"] == "" and resp["visible"] is True
        gb._handle_command_gui({"cmd": "hide"})
        assert not gb.widget.isVisible()
        shot = tmp_path / "widget.png"
        gb.widget.show()
        qapp.processEvents()
        gb.widget.grab().save(str(shot))
        assert shot.stat().st_size > 1000
    finally:
        gb.ipc.stop()
        gb.store.close()


def test_voice_stream_begins_on_gui_thread(qapp, monkeypatch, fake_provider):
    import threading

    from PySide6.QtCore import QThread

    from gamebuddy.config import Config
    from gamebuddy.speech import stt
    from gamebuddy.ui.app import GameBuddyApp
    from gamebuddy.ui.widget import BuddyWidget

    threads = []
    original = BuddyWidget.begin_stream

    def begin_stream(widget):
        threads.append(QThread.currentThread())
        original(widget)

    monkeypatch.setattr(BuddyWidget, "begin_stream", begin_stream)
    monkeypatch.setattr(stt, "transcribe", lambda wav, cfg: "hello")
    cfg = Config()
    cfg.capture.backend = "none"
    cfg.speech.tts = "none"
    gb = GameBuddyApp(cfg)
    gb.kin._provider = fake_provider([{"text": "hello back"}])
    try:
        worker = threading.Thread(target=gb._transcribe_and_ask, args=(b"wav",))
        worker.start()
        worker.join(timeout=3)
        assert not worker.is_alive()
        qapp.processEvents()
        assert threads == [qapp.thread()]
        assert gb.widget._streaming_label is None
    finally:
        gb.widget.close()
        gb.store.close()


def test_settings_release_microphones_before_recreating_listener(qapp, monkeypatch):
    from types import SimpleNamespace

    from gamebuddy.config import Config
    from gamebuddy.ui import settings
    from gamebuddy.ui.app import GameBuddyApp

    events = []
    monkeypatch.setattr(settings, "SettingsDialog", lambda *a: SimpleNamespace(exec=lambda: True))
    cfg = Config()
    cfg.capture.backend = "none"
    gb = GameBuddyApp(cfg)
    gb.listener = SimpleNamespace(active=True, stop=lambda: events.append("listener stopped"))
    gb.recorder = SimpleNamespace(recording=True, stop=lambda: events.append("recorder stopped"))
    monkeypatch.setattr(gb, "set_hands_free", lambda on: events.append(("listen", on)))
    try:
        gb.open_settings()
        assert events == ["listener stopped", "recorder stopped", ("listen", True)]
        assert gb.listener is None and gb.recorder is None
    finally:
        gb.widget.close()
        gb.store.close()


def test_tray_ai_choice_persists_and_does_not_change_busy_provider(qapp, tmp_path, monkeypatch):
    import json

    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    from gamebuddy.config import Config, load_config
    from gamebuddy.ui.app import GameBuddyApp

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "test-model",
                        "visibility": "list",
                        "supported_reasoning_levels": [{"effort": "low"}, {"effort": "max"}],
                    }
                ]
            }
        )
    )
    cfg = Config()
    cfg.capture.backend = "none"
    cfg.llm.provider = "codex"
    gb = GameBuddyApp(cfg)
    gb.tray = QSystemTrayIcon(gb)
    gb._ai_menu = QMenu()
    try:
        gb._refresh_ai_menu()
        gb.kin._provider = object()
        gb._choose_ai(model="test-model")
        gb._choose_ai(effort="max")
        assert load_config().llm.model == "test-model"
        assert load_config().llm.effort == "max"
        assert gb.kin._provider is None
        assert "max" in gb.tray.toolTip()
        gb.kin.busy = True
        gb._choose_ai(effort="low")
        assert cfg.llm.effort == "max"
        gb._refresh_ai_menu()
        assert not gb._ai_menu.isEnabled()
    finally:
        gb.widget.close()
        gb._ai_menu.close()
        gb.store.close()


def test_settings_capture_shortcut_and_recording_mode(qapp, monkeypatch):
    from gamebuddy import hotkeys
    from gamebuddy.config import Config, load_config
    from gamebuddy.i18n import Translator
    from gamebuddy.ui.settings import SettingsDialog

    applied = []
    monkeypatch.setattr(hotkeys, "apply_hypr_bindings", lambda cfg, old: applied.append(cfg) or True)
    cfg = Config()
    dlg = SettingsDialog(cfg, Translator("fr"))
    dlg.ptt.setKeySequence("Ctrl+Alt+P")
    dlg.ptt_mode.setCurrentIndex(dlg.ptt_mode.findData("toggle"))
    dlg._save()
    assert load_config().hotkeys.push_to_talk == "CTRL ALT, P"
    assert load_config().hotkeys.mode == "toggle"
    assert applied[0].mode == "toggle"
    dlg.close()
