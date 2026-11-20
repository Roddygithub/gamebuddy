import threading
from types import SimpleNamespace

from gamebuddy.ui.app import GameBuddyApp


def test_coach_voice_uses_queued_speech_lifecycle():
    app = GameBuddyApp.__new__(GameBuddyApp)
    spoken = []
    app.bridge = SimpleNamespace(coach_advice=SimpleNamespace(emit=lambda *_args: None))
    app.ipc = None
    app.cfg = SimpleNamespace(coach=SimpleNamespace(speak=True))
    app._queue_speech = spoken.append

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
    app._queue_speech = spoken.append

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
    app.ipc = SimpleNamespace(broadcast=lambda *args, **kwargs: sent.append((args, kwargs)))
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
