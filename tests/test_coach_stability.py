"""Coach advice only reaches the player once the screen it describes has persisted."""

import io
import json
import threading
from types import SimpleNamespace

from PIL import Image, ImageDraw

from gamebuddy.coach.observer import dhash, hash_distance
from gamebuddy.coach.pipeline import CoachPipeline
from gamebuddy.config import Config
from gamebuddy.memory import Store

SHOP = {
    "game": "Dota Underlords",
    "decision_window": {"type": "shop", "open": True, "confidence": 0.9},
    "state": {"available_options": ["Buy Slark", "Reroll", "Save gold"], "unknown_fields": []},
    "ownership_confidence": 0.95,
    "decision": "ADVISE",
    "advice": "Save gold this round: you are above the interest threshold.",
    "rationale": "Economy phase, no threat visible.",
    "evidence": ["gold 52 visible", "shop open"],
    "confidence": 0.85,
}
ABSTAIN = {**SHOP, "decision": "ABSTAIN"}


def _frame(kind: str) -> bytes:
    img = Image.new("L", (128, 128), 60)
    draw = ImageDraw.Draw(img)
    if kind == "shop":
        for y in range(0, 128, 10):
            draw.rectangle([0, y, 128, y + 5], fill=230)
    else:
        draw.ellipse([8, 8, 120, 120], fill=250)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


SHOP_FRAME = _frame("shop")
OTHER_FRAME = _frame("other")


def _blank_frame() -> bytes:
    buf = io.BytesIO()
    Image.new("L", (128, 128), 8).save(buf, "JPEG", quality=95)
    return buf.getvalue()


class _Provider:
    name = "fake"
    model = "fake-vision-1"

    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls = 0

    def supports_vision(self) -> bool:
        return True

    def chat(self, **kwargs) -> SimpleNamespace:
        payload = self.payloads[self.calls]
        self.calls += 1
        return SimpleNamespace(text=json.dumps(payload))


class _Capture:
    def __init__(self, frames: list[bytes]):
        self.frames = list(frames)

    def __call__(self) -> bytes | None:
        return self.frames.pop(0) if self.frames else None


class BlindProvider(_Provider):
    name = "blind"
    model = "llama-3"

    def __init__(self):
        super().__init__([])

    def supports_vision(self) -> bool:
        return False


def _build(tmp_path, payloads, frames):
    store = Store(tmp_path / "coach.db")
    advice = []
    cfg = Config()
    cfg.coach.confirm_poll_s = 0.0  # the confirmation is a capture, not a wait
    pipeline = CoachPipeline(
        cfg=cfg,
        store=store,
        provider_factory=lambda: _Provider(payloads),
        capture=_Capture(frames),
        on_advice=advice.append,
    )
    return pipeline, advice, store


def test_frames_are_far_enough_apart_to_work_as_change():
    assert hash_distance(dhash(SHOP_FRAME), dhash(OTHER_FRAME)) > Config().coach.min_change


def test_a_persisting_window_is_advised_without_waiting_an_interval(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP], [SHOP_FRAME, SHOP_FRAME, SHOP_FRAME])
    pipeline.tick()
    # The same look re-captured the screen: it persisted, so it is spoken at once.
    assert [a.advice for a in advice] == [SHOP["advice"]]
    pipeline.tick()  # the screen did not move: it was already judged
    assert len(advice) == 1


def test_a_flash_that_vanishes_is_never_spoken(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP, ABSTAIN], [SHOP_FRAME, OTHER_FRAME, OTHER_FRAME])
    pipeline.tick()  # candidate on a transient screen: the confirmation sees it gone
    pipeline.tick()  # the new screen is stable, but no candidate survived
    assert advice == []


def test_delivery_and_turn_timing_are_audited(tmp_path):
    pipeline, advice, store = _build(tmp_path, [SHOP], [SHOP_FRAME, SHOP_FRAME])
    pipeline.tick()
    stats = store.coach_stats()
    assert stats["gate:accepted"] == 1
    assert stats["pre_gate:await_stability"] == 1
    assert stats["pre_gate:delivered"] == 1
    assert len(advice) == 1
    turn = pipeline.metrics["last_turn"]
    assert turn["outcome"] == "delivered"
    assert turn["frame_kib"] > 0  # the payload actually sent is measured every turn


def test_cooldown_uses_monotonic_clock_and_retries_new_candidate(tmp_path, monkeypatch):
    import gamebuddy.coach.pipeline as module

    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    second = {**SHOP, "advice": "Buy Slark now; the shop is about to refresh."}
    pipeline, advice, _ = _build(
        tmp_path,
        [SHOP, second],
        [SHOP_FRAME, SHOP_FRAME, OTHER_FRAME, OTHER_FRAME, OTHER_FRAME, OTHER_FRAME],
    )
    pipeline.cfg.coach.cooldown_s = 10

    pipeline.tick()
    assert pipeline._last_advice_at == 100.0
    clock[0] = 105.0
    pipeline.tick()  # new decision window during cooldown: defer, do not mark judged
    assert pipeline.metrics["reasoner_calls"] == 1
    clock[0] = 111.0
    pipeline.tick()  # unchanged candidate is evaluated after cooldown expires

    assert pipeline.metrics["reasoner_calls"] == 2
    assert [item.advice for item in advice] == [SHOP["advice"], second["advice"]]


def test_changed_confirmation_frame_is_evaluated_on_next_tick(tmp_path):
    pipeline, advice, _ = _build(
        tmp_path,
        [SHOP, SHOP],
        [SHOP_FRAME, OTHER_FRAME, OTHER_FRAME, OTHER_FRAME],
    )

    pipeline.tick()  # first decision vanished before confirmation
    assert advice == []
    pipeline.tick()  # the now-stable new decision is evaluated

    assert pipeline.metrics["reasoner_calls"] == 2
    assert len(advice) == 1


def test_failed_confirmation_retries_original_candidate_when_it_returns(tmp_path):
    pipeline, advice, _ = _build(
        tmp_path,
        [SHOP, SHOP],
        [SHOP_FRAME, OTHER_FRAME, SHOP_FRAME, SHOP_FRAME],
    )

    pipeline.tick()  # transient frame during confirmation drops the otherwise valid advice
    assert advice == []
    pipeline.tick()  # original decision is still on screen and must be evaluated again

    assert pipeline.metrics["reasoner_calls"] == 2
    assert len(advice) == 1


def test_stop_during_confirmation_prevents_advice_delivery(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP], [SHOP_FRAME])
    entered = threading.Event()
    release = threading.Event()

    def blocked_capture():
        entered.set()
        assert release.wait(2)
        return SHOP_FRAME

    pipeline.capture_fresh = blocked_capture
    worker = threading.Thread(target=pipeline.tick)
    worker.start()
    assert entered.wait(2)
    pipeline.stop()
    release.set()
    worker.join(2)

    assert not worker.is_alive()
    assert advice == []


def test_window_change_during_confirmation_drops_old_context_advice(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP], [SHOP_FRAME])
    selection = [1]
    pipeline.capture_context = lambda: selection[0]
    pipeline.context_is_current = lambda context: context == selection[0]

    def switch_selection_then_capture():
        selection[0] = 2
        return SHOP_FRAME  # similar pixels from another target must not validate old advice

    pipeline.capture_fresh = switch_selection_then_capture

    pipeline.tick()

    assert advice == []
    assert pipeline.metrics["reasoner_calls"] == 1


def test_new_capture_context_is_evaluated_even_when_hash_matches(tmp_path):
    pipeline, advice, _ = _build(
        tmp_path,
        [SHOP, SHOP],
        [SHOP_FRAME, SHOP_FRAME, SHOP_FRAME, SHOP_FRAME],
    )
    pipeline.on_advice = lambda obs, _context: advice.append(obs)
    selection = [1]
    pipeline.capture_context = lambda: selection[0]
    pipeline.context_is_current = lambda context: context == selection[0]
    pipeline.cfg.coach.cooldown_s = 0

    pipeline.tick()
    selection[0] = 2
    pipeline.tick()

    assert pipeline.metrics["reasoner_calls"] == 2
    assert len(advice) == 2
    assert advice[0].advice == advice[1].advice


def test_coach_restarts_while_stopped_capture_finishes(tmp_path):
    pipeline, advice, _store = _build(tmp_path, [SHOP], [])
    pipeline.cfg.coach.interval_s = 0.01
    pipeline.cfg.coach.confirm_poll_s = 0.0
    first_capture = threading.Event()
    release_first = threading.Event()
    restarted = threading.Event()
    advised = threading.Event()
    count = [0]

    def capture():
        count[0] += 1
        if count[0] == 1:
            first_capture.set()
            assert release_first.wait(2)
            return OTHER_FRAME
        if count[0] == 2:
            restarted.set()
        return SHOP_FRAME

    pipeline.capture = capture
    pipeline.capture_fresh = capture
    original_advice = pipeline.on_advice

    def on_advice(obs):
        original_advice(obs)
        advised.set()

    pipeline.on_advice = on_advice
    pipeline.start()
    old_thread = pipeline._thread
    assert first_capture.wait(2)
    pipeline.stop()
    pipeline.start()
    new_thread = pipeline._thread
    assert new_thread is not old_thread
    release_first.set()
    assert restarted.wait(2)
    assert advised.wait(2)
    pipeline.stop()
    old_thread.join(2)
    new_thread.join(2)

    assert not old_thread.is_alive()
    assert not new_thread.is_alive()
    assert pipeline.metrics["reasoner_calls"] == 1
    assert len(advice) == 1


def test_a_text_only_model_never_gets_a_frame(tmp_path):
    # The capture list is empty: taking a frame here would return None and hide it,
    # so the provider records the proof instead.
    store = Store(tmp_path / "coach.db")
    pipeline = CoachPipeline(
        cfg=Config(),
        store=store,
        provider_factory=BlindProvider,
        capture=lambda: (_ for _ in ()).throw(AssertionError("captured a frame")),
        on_advice=lambda obs: None,
    )
    assert pipeline.can_see() == (False, "blind/llama-3")
    assert pipeline.tick() is None
    assert pipeline.metrics["needs_vision"] == 1
    assert store.coach_stats().get("pre_gate:no_vision") == 1


def test_a_blank_frame_never_reaches_the_model(tmp_path):
    # No payload is queued: a model call here would raise IndexError.
    pipeline, advice, store = _build(tmp_path, [], [_blank_frame()])
    assert pipeline.tick() is None
    assert advice == []
    assert pipeline.metrics["blank_frames"] == 1
    assert store.coach_stats().get("pre_gate:blank_frame") == 1


def test_slow_turn_skips_missed_intervals_instead_of_bursting(tmp_path, monkeypatch):
    import gamebuddy.coach.pipeline as module

    pipeline, _advice, _store = _build(tmp_path, [], [])
    pipeline.cfg.coach.interval_s = 4
    pipeline._next_due = 4
    clock = [5.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    class StopAfterOneTick:
        calls = 0

        def wait(self, _timeout):
            self.calls += 1
            return self.calls > 2

        def is_set(self):
            return False

    pipeline._stop = StopAfterOneTick()
    pipeline.tick = lambda _stop_event=None: clock.__setitem__(0, 20.0)

    pipeline._loop()

    assert pipeline._next_due == 24.0
