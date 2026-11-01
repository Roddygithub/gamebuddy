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
