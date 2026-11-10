"""Coach advice only reaches the player once the screen it describes has persisted."""

import io
import json
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


class _Provider:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls = 0

    def chat(self, **kwargs) -> SimpleNamespace:
        payload = self.payloads[self.calls]
        self.calls += 1
        return SimpleNamespace(text=json.dumps(payload))


class _Capture:
    def __init__(self, frames: list[bytes]):
        self.frames = list(frames)

    def __call__(self) -> bytes | None:
        return self.frames.pop(0) if self.frames else None


def _build(tmp_path, payloads, frames):
    store = Store(tmp_path / "coach.db")
    advice = []
    pipeline = CoachPipeline(
        cfg=Config(),
        store=store,
        provider_factory=lambda: _Provider(payloads),
        capture=_Capture(frames),
        on_advice=advice.append,
    )
    return pipeline, advice, store


def test_frames_are_far_enough_apart_to_work_as_change():
    assert hash_distance(dhash(SHOP_FRAME), dhash(OTHER_FRAME)) > Config().coach.min_change


def test_advice_waits_for_the_screen_to_persist(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP], [SHOP_FRAME, SHOP_FRAME, SHOP_FRAME])
    pipeline.tick()
    assert advice == []  # a single sighting is only a candidate
    pipeline.tick()
    assert [a.advice for a in advice] == [SHOP["advice"]]
    pipeline.tick()  # nothing pending any more: no repeat
    assert len(advice) == 1


def test_a_flash_that_vanishes_is_never_spoken(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP, ABSTAIN], [SHOP_FRAME, OTHER_FRAME, OTHER_FRAME])
    pipeline.tick()  # candidate on a transient screen
    pipeline.tick()  # the screen moved on, the model abstains
    pipeline.tick()  # the new screen is stable, but no candidate survived
    assert advice == []


def test_a_stale_candidate_is_dropped(tmp_path):
    pipeline, advice, _ = _build(tmp_path, [SHOP], [SHOP_FRAME, SHOP_FRAME])
    pipeline.tick()
    pipeline._pending_at -= pipeline._pending_ttl_s + 1
    pipeline.tick()
    assert advice == []


def test_pending_and_delivery_are_audited(tmp_path):
    pipeline, advice, store = _build(tmp_path, [SHOP], [SHOP_FRAME, SHOP_FRAME])
    pipeline.tick()
    pipeline.tick()
    stats = store.coach_stats()
    assert stats["gate:accepted"] == 1
    assert stats["pre_gate:await_stability"] == 1
    assert stats["pre_gate:delivered"] == 1
    assert len(advice) == 1
