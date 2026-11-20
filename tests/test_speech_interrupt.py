import threading
from types import SimpleNamespace

import pytest

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

    app._speech_cancelled = threading.Event()
    app._speak("First sentence. Second sentence.", 0, app._speech_cancelled)

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
    cancelled = threading.Event()
    app._speech_cancelled = cancelled
    worker = threading.Thread(target=app._speak, args=("A reply.", 0, cancelled))
    worker.start()
    assert entered_play.wait(2)
    app._cancel_speech()
    continue_play.set()
    worker.join(2)

    assert not worker.is_alive()
    assert played == []


def test_cancelled_queued_reply_never_begins_synthesis(monkeypatch):
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
    queued = []
    synthesized = []
    app.pool = SimpleNamespace(start=queued.append)
    monkeypatch.setattr(player, "stop", lambda: None)
    monkeypatch.setattr(tts, "synthesize", lambda *_args: synthesized.append(True) or (b"audio", "wav"))
    monkeypatch.setattr(player, "play", lambda *_args, **_kwargs: pytest.fail("stale reply played"))

    app._queue_speech("Reply still waiting in the pool.")
    app._cancel_speech()
    queued.pop()()

    assert synthesized == []
