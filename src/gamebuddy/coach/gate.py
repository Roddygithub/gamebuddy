"""Grounding gates around the coach reasoner.

Pure functions so they are unit-testable without any model. They encode the
Phase 0B.2 lessons: abstain before reasoning when critical facts are missing,
and reject advice that is not supported by the structured state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

DECISIONS = ("ADVISE", "ABSTAIN", "NEED_MORE_EVIDENCE")
FAST_WINDOWS = {"combat", "fight", "teamfight", "dodge", "aim", "reaction"}


@dataclass
class Observation:
    decision: str = "ABSTAIN"
    advice: str = ""
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    ownership_confidence: float = 0.0
    window_type: str = ""
    window_open: bool = False
    window_confidence: float = 0.0
    available_options: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    game: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def parse_observation(text: str) -> Observation:
    """Parse the reasoner's JSON (tolerating code fences and prose around it)."""
    cleaned = text.strip()
    m = re.search(r"\{.*\}", cleaned, re.S)
    if not m:
        raise ValueError("no JSON object in reasoner output")
    data = json.loads(m.group(0))
    state = data.get("state") or {}
    window = data.get("decision_window") or {}
    obs = Observation(
        decision=str(data.get("decision", "ABSTAIN")).upper(),
        advice=(data.get("advice") or "").strip(),
        rationale=(data.get("rationale") or "").strip(),
        evidence=[str(e) for e in data.get("evidence") or []],
        confidence=_num(data.get("confidence")),
        ownership_confidence=_num(data.get("ownership_confidence")),
        window_type=str(window.get("type") or "").lower(),
        window_open=bool(window.get("open", False)),
        window_confidence=_num(window.get("confidence")),
        available_options=[str(o) for o in state.get("available_options") or []],
        unknown_fields=[str(u) for u in state.get("unknown_fields") or []],
        game=str(data.get("game") or ""),
        raw=data,
    )
    if obs.decision not in DECISIONS:
        obs.decision = "ABSTAIN"
    return obs


def _num(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def validate(obs: Observation, min_confidence: float = 0.7) -> tuple[bool, str]:
    """Final gate. Returns (accept, reason). Only ADVISE can be accepted."""
    if obs.decision != "ADVISE":
        return False, obs.decision.lower()
    if not obs.advice:
        return False, "empty_advice"
    if len(obs.advice) > 400:
        return False, "advice_too_long"
    if obs.confidence < min_confidence:
        return False, "low_confidence"
    if obs.ownership_confidence < min_confidence:
        return False, "ownership_uncertain"
    if not obs.window_open or obs.window_confidence < min_confidence:
        return False, "window_not_open"
    if obs.window_type in FAST_WINDOWS:
        return False, "fast_window"
    if not obs.evidence:
        return False, "no_evidence"
    critical = [u for u in obs.unknown_fields if _is_critical(u)]
    if critical:
        return False, "critical_unknown:" + ",".join(critical[:3])
    if obs.available_options and not _mentions_option(obs.advice, obs.available_options):
        return False, "advice_not_grounded_in_options"
    return True, "ok"


_CRITICAL = ("owner", "ownership", "hp", "health", "gold", "cost", "cooldown", "timer", "mana", "resource")


def _is_critical(field_name: str) -> bool:
    low = field_name.lower()
    return any(k in low for k in _CRITICAL)


_GENERIC = {
    "buy",
    "use",
    "take",
    "pick",
    "sell",
    "save",
    "keep",
    "hold",
    "play",
    "now",
    "this",
    "that",
    "with",
    "your",
    "the",
    "and",
    "for",
    "from",
    "into",
    "option",
    "choose",
    "select",
    "skip",
}


def _mentions_option(advice: str, options: list[str]) -> bool:
    """True when the advice names a specific option (not just a generic verb like 'buy')."""
    low = advice.lower()
    for opt in options:
        words = [w for w in re.split(r"\W+", opt.lower()) if len(w) > 2 and w not in _GENERIC]
        if words and any(w in low for w in words):
            return True
    return False


def similar(a: str, b: str) -> float:
    """Cheap Jaccard similarity on words — used to suppress repeated advice."""
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
