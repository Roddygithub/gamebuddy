"""Annotated eval cases for the coach.

A case is a directory holding one JPEG frame (``frame.jpg``) and a ``case.toml``
annotation describing what the coach should see and decide. Loading is
fail-closed: a case that cannot be fully read raises :class:`CaseError`, so a
broken dataset never silently shrinks the measurement.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DECISIONS = ("ADVISE", "ABSTAIN", "NEED_MORE_EVIDENCE")


class CaseError(ValueError):
    """A case or dataset could not be loaded; the eval refuses to run."""


@dataclass
class Resource:
    type: str
    value: str


@dataclass
class CoachCase:
    name: str
    directory: Path
    frame: bytes
    game: str = ""
    description: str = ""
    synthetic: bool = False
    decision: str = "ABSTAIN"
    entities: list[str] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    mention: list[str] = field(default_factory=list)
    latency_budget_s: float = 20.0

    @property
    def expects_advice(self) -> bool:
        return self.decision == "ADVISE"

    @property
    def has_perception_annotations(self) -> bool:
        return bool(self.entities or self.resources or self.options)


def load_case(directory: Path) -> CoachCase:
    directory = Path(directory)
    meta = directory / "case.toml"
    image = directory / "frame.jpg"
    if not meta.is_file():
        raise CaseError(f"{directory}: missing case.toml")
    if not image.is_file():
        raise CaseError(f"{directory}: missing frame.jpg")
    try:
        raw = tomllib.loads(meta.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise CaseError(f"{directory}: unreadable case.toml: {exc}") from exc

    expected = raw.get("expected") or {}
    decision = str(expected.get("decision", "ABSTAIN")).upper()
    if decision not in DECISIONS:
        raise CaseError(f"{directory}: expected.decision must be one of {', '.join(DECISIONS)}")

    perception = raw.get("perception") or {}
    resources: list[Resource] = []
    for item in perception.get("resources") or []:
        if not isinstance(item, dict) or "value" not in item:
            raise CaseError(f"{directory}: each perception.resources entry needs type and value")
        resources.append(Resource(type=str(item.get("type", "")), value=str(item["value"])))

    case_info = raw.get("case") or {}
    try:
        budget = float(expected.get("latency_budget_s", 20.0))
    except (TypeError, ValueError) as exc:
        raise CaseError(f"{directory}: latency_budget_s must be a number") from exc

    return CoachCase(
        name=directory.name,
        directory=directory,
        frame=image.read_bytes(),
        game=str(case_info.get("game", "")),
        description=str(case_info.get("description", "")),
        synthetic=bool(case_info.get("synthetic", False)),
        decision=decision,
        entities=[str(e) for e in perception.get("entities") or []],
        resources=resources,
        options=[str(o) for o in perception.get("options") or []],
        mention=[str(m) for m in expected.get("mention") or []],
        latency_budget_s=budget,
    )


def load_cases(dataset: Path) -> list[CoachCase]:
    """Load every case directory. Dot/underscore names and ``results/`` are ignored."""
    dataset = Path(dataset)
    if not dataset.is_dir():
        raise CaseError(f"dataset directory not found: {dataset}")
    cases: list[CoachCase] = []
    for child in sorted(dataset.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith((".", "_")) or child.name == "results":
            continue
        cases.append(load_case(child))
    if not cases:
        raise CaseError(
            f"{dataset}: no cases found (each case is a sub-directory with case.toml + frame.jpg)"
        )
    return cases
