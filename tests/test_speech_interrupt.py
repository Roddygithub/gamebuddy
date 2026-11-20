import threading
from types import SimpleNamespace

from gamebuddy.audio import player
from gamebuddy.speech import tts
from gamebuddy.ui.app import GameBuddyApp


def test_interrupt_during_playback_prevents_later_sentences(monkeypatch):
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._speech_gen = 0
    app._speech_lock = threading.Lock()
    app._speech_cancelled = None
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

    def play(data, _format, _device, _cancelled=None):
        played.append(data.decode())
        app._cancel_speech()

    monkeypatch.setattr(tts, "synthesize", synthesize)
    monkeypatch.setattr(player, "play", play)
    monkeypatch.setattr(player, "stop", lambda: None)

    app._speak("First sentence. Second sentence.")

    assert synthesized == ["First sentence."]
    assert played == ["First sentence."]
    assert not app._speaking.is_set()


def test_cancel_between_generation_check_and_play_prevents_stale_audio(monkeypatch):
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._speech_gen = 0
    app._speech_lock = threading.Lock()
    app._speech_cancelled = None
    app._speaking = threading.Event()
    app._timings = {}
    app.listener = None
    app.cfg = SimpleNamespace(audio=SimpleNamespace(output_device=""))
    app.tr = SimpleNamespace(language="en")
    app.bridge = SimpleNamespace(status=SimpleNamespace(emit=lambda _status: None))
    entered_play = threading.Event()
    continue_play = threading.Event()
    played = []

    monkeypatch.setattr(tts, "synthesize", lambda *_args: (b"stale", "wav"))
    monkeypatch.setattr(player, "stop", lambda: None)

    def play(data, _format, _device, cancelled=None):
        entered_play.set()
        assert continue_play.wait(2)
        if not cancelled or not cancelled.is_set():
            played.append(data)

    monkeypatch.setattr(player, "play", play)
    worker = threading.Thread(target=app._speak, args=("A reply.",))
    worker.start()
    assert entered_play.wait(2)
    app._cancel_speech()
    continue_play.set()
    worker.join(2)

    assert not worker.is_alive()
    assert played == []
