"""Deterministic graders mapping annotated cases to the four coach measures.

1. perception — the annotated facts (entities, resources, options) are readable
   in the structured state the reasoner returned. Not applicable when a case
   declares no perception annotations.
2. grounding  — what would reach the player matches the frame: for ADVISE cases
   the gate must accept and the delivered advice must reference an annotated
   option and may not name options that are not on the frame (hallucination
   check); when the case expects silence, nothing may be delivered.
3. latency    — time from frame to decision within the case budget.
4. decision   — the model's own judgement matches the annotation: silent
   (ABSTAIN or NEED_MORE_EVIDENCE) on ambiguous frames, ADVISE only on a real
   decision window.

All checks are pure functions of the annotation and the parsed observation, so
they run identically on live calls and on replayed answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gamebuddy.coach.gate import _GENERIC, Observation
from gamebuddy.eval.cases import CoachCase

MEASURES = ("perception", "grounding", "latency", "decision")


def significant_words(text: str, min_len: int = 3) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) >= min_len and w not in _GENERIC]


def state_text(obs: Observation) -> str:
    """Everything the reasoner claims to have read, as one lowercase string."""
    state = (obs.raw or {}).get("state") or {}
    chunks: list[str] = []
    for key in ("player_entities", "opponent_entities", "available_options", "unknown_fields"):
        chunks += [str(v) for v in state.get(key) or []]
    for res in state.get("resources") or []:
        if isinstance(res, dict):
            chunks += [str(res.get("type", "")), str(res.get("value", ""))]
        else:
            chunks.append(str(res))
    chunks += [str(e) for e in obs.evidence]
    return " ".join(chunks).lower()


def check_perception(case: CoachCase, obs: Observation) -> list[str]:
    notes: list[str] = []
    text = state_text(obs)
    for entity in case.entities:
        if entity.lower() not in text:
            notes.append(f"entity not read: {entity}")
    for res in case.resources:
        if res.type.lower() not in text:
            notes.append(f"resource type not read: {res.type}")
        if res.value.lower() not in text:
            notes.append(f"resource value not read: {res.type}={res.value}")
    observed = " ".join(obs.available_options).lower()
    for option in case.options:
        words = significant_words(option, min_len=2)
        if words and not all(w in observed for w in words):
            notes.append(f"option not offered: {option}")
    return notes


def check_grounding(
    case: CoachCase, obs: Observation, accepted: bool, reject_reason: str
) -> list[str]:
    if not accepted:
        # Silence on a withheld case is exactly right; rejecting advice the case
        # says should be delivered means the gate (or the model) got it wrong.
        return [] if not case.expects_advice else [f"gate rejected the advice: {reject_reason}"]
    if not case.expects_advice:
        return [f"advice delivered although {case.decision} was expected"]
    notes: list[str] = []
    advice = obs.advice.lower()
    if case.mention and not any(m.lower() in advice for m in case.mention):
        notes.append(f"advice references none of: {', '.join(case.mention)}")
    annotated = " ".join(case.options).lower()
    if case.options:
        for option in obs.available_options:
            words = significant_words(option)
            if words and not any(w in annotated for w in words):
                notes.append(f"option not on the frame: {option}")
    return notes


def check_decision(case: CoachCase, obs: Observation) -> list[str]:
    if case.expects_advice:
        return [] if obs.decision == "ADVISE" else [f"expected ADVISE, model said {obs.decision}"]
    if obs.decision == "ADVISE":
        return [f"expected {case.decision}, model said ADVISE"]
    return []


@dataclass
class RunRecord:
    decision: str = "ABSTAIN"
    advice: str = ""
    accepted: bool = False
    reject_reason: str = ""
    latency_s: float = 0.0
    raw: str = ""
    measures: dict[str, bool | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(value is not False for value in self.measures.values())

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "advice": self.advice,
            "accepted": self.accepted,
            "reject_reason": self.reject_reason,
            "latency_s": round(self.latency_s, 2),
            "measures": self.measures,
            "notes": self.notes,
            "passed": self.passed,
            "raw": self.raw,
        }


def grade_observation(
    case: CoachCase,
    obs: Observation,
    *,
    accepted: bool,
    reject_reason: str,
    latency_s: float,
    raw: str = "",
) -> RunRecord:
    perception_fail = check_perception(case, obs)
    grounding_fail = check_grounding(case, obs, accepted, reject_reason)
    decision_fail = check_decision(case, obs)
    latency_fail = (
        [] if latency_s <= case.latency_budget_s else [f"latency {latency_s:.1f}s > {case.latency_budget_s:g}s budget"]
    )
    return RunRecord(
        decision=obs.decision,
        advice=obs.advice,
        accepted=accepted,
        reject_reason=reject_reason,
        latency_s=latency_s,
        raw=raw,
        measures={
            "perception": (not perception_fail) if case.has_perception_annotations else None,
            "grounding": not grounding_fail,
            "latency": not latency_fail,
            "decision": not decision_fail,
        },
        notes=perception_fail + grounding_fail + decision_fail + latency_fail,
    )
