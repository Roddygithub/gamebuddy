import threading
from types import SimpleNamespace

from gamebuddy.audio import player
from gamebuddy.speech import tts
from gamebuddy.ui.app import GameBuddyApp


def test_interrupt_during_playback_prevents_later_sentences(monkeypatch):
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._speech_gen = 0
    app._speaking = threading.Event()
    app._timings = {}
    app.listener = None
    app.cfg = SimpleNamespace(audio=SimpleNamespace(output_device=""))
    app.tr = SimpleNamespace(language="en")
    app.bridge = SimpleNamespace(status=SimpleNamespace(emit=lambda _status: None))
    synthesized = []
    played = []

    def synthesize(text, _cfg, _language):
        synthesized.append(text)
        return text.encode(), "wav"

    def play(data, _format, _device):
        played.append(data.decode())
        app._cancel_speech()

    monkeypatch.setattr(tts, "synthesize", synthesize)
    monkeypatch.setattr(player, "play", play)
    monkeypatch.setattr(player, "stop", lambda: None)

    app._speak("First sentence. Second sentence.")

    assert synthesized == ["First sentence."]
    assert played == ["First sentence."]
    assert not app._speaking.is_set()
