"""`gamebuddy ask` answers on the same connection, so scripts can use it."""

import os

import pytest

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def app(qapp, fake_provider):
    from gamebuddy.config import Config
    from gamebuddy.ui.app import GameBuddyApp

    cfg = Config()
    cfg.capture.backend = "none"
    cfg.speech.tts = "none"
    cfg.general.onboarding_done = True
    cfg.general.language = "fr"
    gb = GameBuddyApp(cfg)
    gb.kin._provider = fake_provider([{"text": "Prends le chemin de gauche."}])
    gb.start()
    try:
        yield gb
    finally:
        gb.ipc.stop()
        gb.widget.close()
        gb.store.close()


def test_ask_prints_the_answer(app, capsys):
    from gamebuddy import cli

    assert cli.main(["ask", "où", "aller ?"]) == 0
    assert "Prends le chemin de gauche." in capsys.readouterr().out


def test_ask_reports_the_engine_error_in_the_ui_language(app, capsys):
    from gamebuddy import cli

    class Boom:
        name = "boom"
        model = "boom"

        def supports_vision(self):
            return False

        def chat(self, **kwargs):
            raise RuntimeError("codex_not_logged_in: no session")

    app.kin._provider = Boom()
    assert cli.main(["ask", "et maintenant ?"]) == 1
    err = capsys.readouterr().err
    assert "Codex n'est pas connecté" in err
    assert "codex_not_logged_in" not in err


def test_friendly_errors_follow_the_language():
    from gamebuddy.i18n import Translator
    from gamebuddy.ui.app import friendly_error

    assert friendly_error("missing_api_key", Translator("de")).startswith("Kein API-Schlüssel")
    assert friendly_error("missing_api_key", Translator("en")).startswith("No API key")
    assert friendly_error("something else", Translator("fr")) == "something else"
