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

    from gamebro.config import Config
    from gamebro.ui.app import GameBroApp

    cfg = Config()
    cfg.general.onboarding_done = True
    cfg.general.language = "fr"
    cfg.speech.tts = "none"
    cfg.llm.web_search = False
    cfg.capture.backend = "none"
    gb = GameBroApp(cfg)
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
