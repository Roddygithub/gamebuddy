"""Run the coach eval dataset, live or replayed, and report pass@k reliability.

Live mode calls the configured coach provider once per case and repeat
(``--repeat k``), grades every answer against the annotation, and writes a JSON
report. Replay mode (``--replay report.json``) re-grades the recorded answers
of a previous report with the current parsing, gate and graders — no provider
call — so prompt or gate changes can be regression-checked for free. Replay
fails closed when the dataset no longer contains a recorded case.

Exit codes: 0 every case passed every run, 1 at least one run failed,
2 the dataset or replay source is unusable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from gamebuddy.coach.gate import Observation, parse_observation, validate
from gamebuddy.coach.pipeline import observe_message
from gamebuddy.config import Config
from gamebuddy.eval.cases import CaseError, CoachCase, load_cases
from gamebuddy.eval.grade import MEASURES, RunRecord, grade_observation
from gamebuddy.llm.router import coach_model, make_provider
from gamebuddy.prompts import COACH_SYSTEM

REPORT_SCHEMA = "gamebuddy-eval/1"


# ---- observation ------------------------------------------------------------
def _observe(provider, case: CoachCase, cfg: Config, language: str) -> RunRecord:
    system = COACH_SYSTEM.replace("{language}", language)
    msg = observe_message(case.frame, case.game)
    start = time.monotonic()
    try:
        turn = provider.chat(system=system, messages=[msg], max_tokens=900, json_mode=True)
    except Exception as exc:  # noqa: BLE001 — a dead provider is a failed run, not a crash
        return RunRecord(
            decision="ABSTAIN",
            advice="",
            accepted=False,
            reject_reason="provider_error",
            latency_s=time.monotonic() - start,
            measures={measure: False for measure in MEASURES},
            notes=[f"provider error: {str(exc)[:200]}"],
        )
    latency = time.monotonic() - start
    try:
        obs = parse_observation(turn.text)
    except (ValueError, TypeError):
        obs = Observation(decision="ABSTAIN", rationale="unparseable")
        accepted, reason = False, "parse_error"
    else:
        accepted, reason = validate(obs, cfg.coach.min_confidence)
    return grade_observation(
        case, obs, accepted=accepted, reject_reason=reason, latency_s=latency, raw=turn.text
    )


def _reobserve(case: CoachCase, recorded: dict, cfg: Config) -> RunRecord:
    """Re-grade one recorded answer with the current code (no provider call)."""
    raw = str(recorded.get("raw", ""))
    latency = float(recorded.get("latency_s", 0.0) or 0.0)
    try:
        obs = parse_observation(raw)
    except (ValueError, TypeError):
        obs = Observation(decision="ABSTAIN", rationale="unparseable")
        accepted, reason = False, "parse_error"
    else:
        accepted, reason = validate(obs, cfg.coach.min_confidence)
    record = grade_observation(case, obs, accepted=accepted, reject_reason=reason, latency_s=latency, raw=raw)
    record.notes.append("replayed")
    return record


# ---- metrics ----------------------------------------------------------------
def _case_metrics(runs: list[RunRecord]) -> dict[str, bool]:
    return {
        "pass_1": runs[0].passed,
        "pass_at_k": any(r.passed for r in runs),
        "pass_hat_k": all(r.passed for r in runs),
    }


def _build_report(
    dataset: Path, cases: list[CoachCase], runs: dict[str, list[RunRecord]], meta: dict
) -> dict:
    k = max(1, int(meta.get("repeat", 1)))
    case_rows = []
    for case in cases:
        case_runs = runs[case.name]
        case_rows.append(
            {
                "name": case.name,
                "file": str(case.directory),
                "game": case.game,
                "expected_decision": case.decision,
                "runs": [r.to_dict() for r in case_runs],
                **_case_metrics(case_runs),
            }
        )

    def _measure_aggregate(measure: str) -> dict:
        """Per-case pass@k for one measure; cases where it is n/a are excluded."""
        per_case = []
        for row in case_rows:
            values = [r["measures"].get(measure) for r in row["runs"]]
            applicable = [v for v in values if v is not None]
            if applicable:
                per_case.append((applicable[0], any(applicable), all(applicable), len(applicable)))
        if not per_case:
            return {
                "applicable_cases": 0,
                "applicable_runs": 0,
                "pass_1": 0.0,
                "pass_at_k": 0.0,
                "pass_hat_k": 0.0,
            }
        n = len(per_case)
        return {
            "applicable_cases": n,
            "applicable_runs": sum(c[3] for c in per_case),
            "pass_1": round(sum(c[0] for c in per_case) / n, 3),
            "pass_at_k": round(sum(c[1] for c in per_case) / n, 3),
            "pass_hat_k": round(sum(c[2] for c in per_case) / n, 3),
        }

    summary = {
        "cases": len(cases),
        "runs": sum(len(r) for r in runs.values()),
        "pass_1": round(sum(c["pass_1"] for c in case_rows) / len(case_rows), 3),
        f"pass_at_{k}": round(sum(c["pass_at_k"] for c in case_rows) / len(case_rows), 3),
        f"pass_hat_{k}": round(sum(c["pass_hat_k"] for c in case_rows) / len(case_rows), 3),
        "measures": {measure: _measure_aggregate(measure) for measure in MEASURES},
    }
    return {
        "schema": REPORT_SCHEMA,
        "dataset": str(dataset),
        **meta,
        "cases": case_rows,
        "summary": summary,
    }


# ---- entry points -----------------------------------------------------------
def run_dataset(
    dataset: Path,
    cfg: Config,
    *,
    repeat: int = 1,
    model: str = "",
    language: str = "en",
    out: Path | None = None,
    provider_factory=None,
    log=print,
) -> tuple[dict, int]:
    cases = load_cases(dataset)
    repeat = max(1, repeat)
    chosen = model or coach_model(cfg)
    if provider_factory is None:
        provider_factory = lambda: make_provider(cfg, chosen)  # noqa: E731
    provider = provider_factory()
    runs: dict[str, list[RunRecord]] = {}
    for case in cases:
        runs[case.name] = [_observe(provider, case, cfg, language) for _ in range(repeat)]
    report = _build_report(
        dataset,
        cases,
        runs,
        meta={
            "mode": "live",
            "provider": getattr(provider, "name", ""),
            "model": getattr(provider, "model", "") or chosen,
            "repeat": repeat,
            "min_confidence": cfg.coach.min_confidence,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    return _finish(dataset, report, out, log)


def run_replay(
    dataset: Path, source: Path, cfg: Config, *, out: Path | None = None, log=print
) -> tuple[dict, int]:
    cases = {case.name: case for case in load_cases(dataset)}
    source_report = json.loads(Path(source).read_text(encoding="utf-8"))
    recorded = source_report.get("cases") or []
    if not recorded:
        raise CaseError(f"{source}: no recorded cases to replay")
    missing = [row.get("name", "?") for row in recorded if row.get("name") not in cases]
    if missing:
        raise CaseError(f"replay: dataset lacks recorded case(s): {', '.join(missing)}")
    runs: dict[str, list[RunRecord]] = {}
    replayed: list[CoachCase] = []
    repeat = 1
    for row in recorded:
        case = cases[row["name"]]
        case_runs = [_reobserve(case, r, cfg) for r in row.get("runs") or []]
        if not case_runs:
            raise CaseError(f"replay: case '{case.name}' has no recorded runs")
        replayed.append(case)
        runs[case.name] = case_runs
        repeat = max(repeat, len(case_runs))
    report = _build_report(
        dataset,
        replayed,
        runs,
        meta={
            "mode": "replay",
            "replayed_from": str(source),
            "repeat": repeat,
            "min_confidence": cfg.coach.min_confidence,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    return _finish(dataset, report, out, log)


def _finish(dataset: Path, report: dict, out: Path | None, log) -> tuple[dict, int]:
    out = out or Path(dataset) / "results" / f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(report, out, log)
    failed = sum(1 for case in report["cases"] if not case["pass_hat_k"])
    return report, (0 if failed == 0 else 1)


def _print_summary(report: dict, out: Path, log) -> None:
    summary = report["summary"]
    per_case = summary["runs"] // max(1, summary["cases"])
    meta = f"{report.get('mode', 'live')} · {report.get('provider', '')} {report.get('model', '')}".strip(
        " ·"
    )
    log(f"Coach eval: {report['dataset']} — {summary['cases']} case(s) × {per_case} run(s) ({meta})")
    for case in report["cases"]:
        last = case["runs"][-1]
        state = "PASS" if case["pass_hat_k"] else "FAIL"
        outcome = (
            f"delivered: {last['advice'][:60]}" if last["accepted"] else f"gate: {last['reject_reason']}"
        )
        notes = f" — {'; '.join(last['notes'])}" if last["notes"] else ""
        log(
            f"  {case['name']:<32} {state}  {last['latency_s']:5.1f}s  {last['decision']:<6} {outcome}{notes}"
        )
    parts = [f"pass@1 {_pct(summary['pass_1'])}"]
    for key, value in summary.items():
        if key.startswith("pass_at_") and key != "pass_at_1":
            parts.append(f"pass@{key[len('pass_at_') :]} {_pct(value)}")
        elif key.startswith("pass_hat_") and key != "pass_hat_1":
            parts.append(f"pass^{key[len('pass_hat_') :]} {_pct(value)}")
    measures = " · ".join(
        f"{name} {_pct(m['pass_1'])} of {m['applicable_runs']} runs"
        for name, m in summary["measures"].items()
        if m["applicable_runs"]
    )
    log(f"  overall: {' · '.join(parts)}")
    if measures:
        log(f"  measures: {measures}")
    log(f"  report: {out}")


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def run_eval_cli(args: argparse.Namespace) -> int:
    from gamebuddy.config import load_config
    from gamebuddy.llm.router import ProviderError

    cfg = load_config()
    dataset = Path(args.dataset)
    out = Path(args.out) if args.out else None
    try:
        if args.replay:
            _, code = run_replay(dataset, Path(args.replay), cfg, out=out)
        else:
            _, code = run_dataset(
                dataset,
                cfg,
                repeat=max(1, args.repeat),
                model=args.model,
                language=args.language,
                out=out,
            )
    except CaseError as exc:
        print(f"gamebuddy: {exc}", file=sys.stderr)
        return 2
    except ProviderError as exc:
        print(f"gamebuddy: provider unavailable: {exc}", file=sys.stderr)
        return 2
    return code
