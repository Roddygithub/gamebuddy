import json

import pytest

from gamebro.coach.gate import parse_observation, similar, validate

GOOD = {
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


def test_accepts_grounded_advice():
    obs = parse_observation(json.dumps(GOOD))
    assert validate(obs) == (True, "ok")


def test_parses_inside_code_fence():
    obs = parse_observation("```json\n" + json.dumps(GOOD) + "\n```")
    assert obs.decision == "ADVISE"


@pytest.mark.parametrize(
    "patch,reason",
    [
        ({"decision": "ABSTAIN"}, "abstain"),
        ({"decision": "NEED_MORE_EVIDENCE"}, "need_more_evidence"),
        ({"advice": ""}, "empty_advice"),
        ({"confidence": 0.5}, "low_confidence"),
        ({"ownership_confidence": 0.4}, "ownership_uncertain"),
        ({"decision_window": {"type": "shop", "open": False, "confidence": 0.9}}, "window_not_open"),
        ({"decision_window": {"type": "combat", "open": True, "confidence": 0.9}}, "fast_window"),
        ({"evidence": []}, "no_evidence"),
        ({"advice": "Buy the dragon lance now."}, "advice_not_grounded_in_options"),
    ],
)
def test_rejections(patch, reason):
    data = {**GOOD, **patch}
    obs = parse_observation(json.dumps(data))
    ok, why = validate(obs)
    assert not ok and why == reason


def test_critical_unknown_blocks():
    data = json.loads(json.dumps(GOOD))
    data["state"]["unknown_fields"] = ["player gold"]
    ok, why = validate(parse_observation(json.dumps(data)))
    assert not ok and why.startswith("critical_unknown")


def test_unknown_decision_becomes_abstain():
    obs = parse_observation(json.dumps({**GOOD, "decision": "MAYBE"}))
    assert obs.decision == "ABSTAIN"


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_observation("no json here")


def test_similar():
    assert similar("save gold this round", "save your gold this round") > 0.5
    assert similar("buy slark", "reroll now") == 0.0
