import threading
from types import SimpleNamespace

from gamebuddy.ui.app import GameBuddyApp


def test_coach_voice_uses_queued_speech_lifecycle():
    app = GameBuddyApp.__new__(GameBuddyApp)
    spoken = []
    app.bridge = SimpleNamespace(coach_advice=SimpleNamespace(emit=lambda *_args: None))
    app.ipc = None
    app.cfg = SimpleNamespace(coach=SimpleNamespace(speak=True))
    app._coach_enabled = True
    app._coach_generation = 1
    app._coach_lock = threading.Lock()
    app._queue_speech = lambda text, **_kwargs: spoken.append(text)

    app._on_coach_advice(SimpleNamespace(advice="Buy Slark", rationale="shop open"))

    assert spoken == ["Buy Slark"]


def test_coach_toggle_uses_requested_state_while_old_thread_stops():
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._coach_enabled = False
    app._coach_lock = threading.Lock()
    app.coach = SimpleNamespace(running=True)  # old stopped cycle is still unwinding
    requests = []
    app.set_coach = requests.append

    app.toggle_coach()
    app._coach_enabled = True
    app.toggle_coach()

    assert requests == [True, False]


def test_status_reports_requested_coach_state_not_unwinding_thread():
    app = GameBuddyApp.__new__(GameBuddyApp)
    app._coach_enabled = False
    app._coach_lock = threading.Lock()
    app.widget = SimpleNamespace(isVisible=lambda: False)
    app.kin = SimpleNamespace(game_title="", busy=False)
    app.window = None
    app.recorder = None
    app.listener = None
    app.coach = SimpleNamespace(running=True, metrics={"last_turn": {}})
    app.backend = SimpleNamespace(name="test")
    app.cfg = SimpleNamespace(
        llm=SimpleNamespace(provider="test", model="", effort="low"),
        hotkeys=SimpleNamespace(push_to_talk="Alt+V", mode="hold"),
    )
    app._timings = {}
    app.tr = SimpleNamespace(language="fr")

    assert app.status_snapshot()["coach"] is False


def test_slow_ipc_broadcast_is_queued_outside_coach_delivery():
    app = GameBuddyApp.__new__(GameBuddyApp)
    entered = threading.Event()
    release = threading.Event()
    tasks = []
    spoken = []
    app.bridge = SimpleNamespace(coach_advice=SimpleNamespace(emit=lambda *_args: None))
    app.ipc = SimpleNamespace(broadcast=lambda *_args, **_kwargs: (entered.set(), release.wait(2)))
    app.pool = SimpleNamespace(start=tasks.append)
    app.cfg = SimpleNamespace(coach=SimpleNamespace(speak=True))
    app._coach_enabled = True
    app._coach_generation = 1
    app._coach_lock = threading.Lock()
    app._queue_speech = lambda text, **_kwargs: spoken.append(text)

    app._on_coach_advice(SimpleNamespace(advice="Buy Slark", rationale="shop open"))
    assert len(tasks) == 1
    assert spoken == ["Buy Slark"]
    worker = threading.Thread(target=tasks.pop())
    worker.start()
    assert entered.wait(2)
    release.set()
    worker.join(2)

    assert not worker.is_alive()


def test_queued_ipc_advice_is_discarded_after_coach_stops():
    app = GameBuddyApp.__new__(GameBuddyApp)
    tasks = []
    sent = []
    app.bridge = SimpleNamespace(coach_advice=SimpleNamespace(emit=lambda *_args: None))
    app.ipc = SimpleNamespace(
        broadcast=lambda *args, should_send=None, **kwargs: (
            sent.append((args, kwargs)) if should_send() else None
        )
    )
    app.pool = SimpleNamespace(start=tasks.append)
    app.cfg = SimpleNamespace(coach=SimpleNamespace(speak=False))
    app._coach_enabled = True
    app._coach_generation = 1
    app._coach_lock = threading.Lock()
    app._on_coach_advice(SimpleNamespace(advice="Buy Slark", rationale="shop open"))

    with app._coach_lock:
        app._coach_generation += 1
        app._coach_enabled = False
    tasks.pop()()

    assert sent == []


def test_queued_coach_speech_is_cancelled_when_coach_stops(monkeypatch):
    from gamebuddy.audio import player
    from gamebuddy.speech import tts

    app = GameBuddyApp.__new__(GameBuddyApp)
    tasks = []
    synthesized = []
    app._coach_enabled = True
    app._coach_generation = 1
    app._coach_lock = threading.Lock()
    app._speech_gen = 0
    app._speech_lock = threading.Lock()
    app._speech_cancelled = None
    app._speech_source = ""
    app._speaking = threading.Event()
    app.listener = None
    app.pool = SimpleNamespace(start=tasks.append)
    app.cfg = SimpleNamespace(audio=SimpleNamespace(output_device=""))
    app.tr = SimpleNamespace(language="fr")
    app._timings = {}
    app.bridge = SimpleNamespace(status=SimpleNamespace(emit=lambda _status: None))
    monkeypatch.setattr(player, "stop", lambda: None)
    monkeypatch.setattr(tts, "synthesize", lambda *_args: synthesized.append(True) or (b"audio", "wav"))

    app._queue_speech("Coach advice", coach_generation=1)
    with app._coach_lock:
        app._coach_enabled = False
        app._coach_generation = 2
    app._cancel_coach_speech()
    tasks.pop()()

    assert synthesized == []


def test_stopping_coach_does_not_cancel_an_ask_voice_during_queue_race(monkeypatch):
    from gamebuddy.audio import player

    app = GameBuddyApp.__new__(GameBuddyApp)
    app._coach_enabled = True
    app._coach_generation = 1
    app._coach_lock = threading.Lock()
    app._speech_gen = 4
    app._speech_lock = threading.Lock()
    app._speech_cancelled = threading.Event()
    app._speech_source = "reply"
    app._speaking = threading.Event()
    app.listener = None
    app.pool = SimpleNamespace(start=lambda _work: None)
    stopped = []
    monkeypatch.setattr(player, "stop", lambda: stopped.append(True))

    app._speech_lock.acquire()
    worker = threading.Thread(target=lambda: app._queue_speech("Coach", coach_generation=1))
    worker.start()
    with app._coach_lock:
        app._coach_enabled = False
        app._coach_generation = 2
    off = threading.Thread(target=app._cancel_coach_speech)
    off.start()
    app._speech_lock.release()
    worker.join(2)
    off.join(2)

    assert not worker.is_alive() and not off.is_alive()
    assert app._speech_source == "reply"
    assert app._speech_gen == 4
    assert stopped == []


def test_queued_ui_advice_is_dropped_after_coach_stops():
    app = GameBuddyApp.__new__(GameBuddyApp)
    displayed = []
    app._coach_enabled = False
    app._coach_generation = 2
    app._coach_lock = threading.Lock()
    app.widget = SimpleNamespace(add_coach=lambda *args: displayed.append(args))

    app._show_coach_advice("stale", "old", 1)

    assert displayed == []
