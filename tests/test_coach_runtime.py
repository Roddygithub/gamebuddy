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
    app.coach = SimpleNamespace(running=True)  # old stopped cycle is still unwinding
    requests = []
    app.set_coach = requests.append

    app.toggle_coach()
    app._coach_enabled = True
    app.toggle_coach()

    assert requests == [True, False]


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
