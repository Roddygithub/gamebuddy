"""The coach eval harness: fail-closed datasets, deterministic graders, pass@k metrics."""

import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from gamebuddy.cli import main
from gamebuddy.coach.gate import parse_observation
from gamebuddy.coach.pipeline import MAX_SAVED_FRAMES, CoachPipeline
from gamebuddy.config import Config
from gamebuddy.eval.cases import CaseError, load_case, load_cases
from gamebuddy.eval.grade import grade_observation, state_text
from gamebuddy.eval.run import run_dataset, run_replay
from gamebuddy.memory import Store

SHOP = {
    "game": "Dota Underlords",
    "decision_window": {"type": "shop", "open": True, "confidence": 0.9},
    "state": {
        "player_entities": ["Slark"],
        "available_options": ["Buy Slark (3 gold)", "Reroll (2)", "Buy XP (5)"],
        "resources": [
            {"type": "gold", "value": "52", "owner": "player", "provenance": "VISUAL", "confidence": 0.9}
        ],
        "unknown_fields": [],
    },
    "ownership_confidence": 0.95,
    "decision": "ADVISE",
    "advice": "Buy Slark to start your board.",
    "rationale": "shop open, affordable",
    "evidence": ["gold 52 visible"],
    "confidence": 0.85,
}
SILENT = {
    "decision": "ABSTAIN",
    "advice": None,
    "rationale": "nothing readable",
    "evidence": [],
    "confidence": 0.8,
    "ownership_confidence": 0.5,
    "state": {"available_options": [], "unknown_fields": ["everything"]},
    "decision_window": {"type": "", "open": False, "confidence": 0.2},
}

TOML_ADVISE = """\
[case]
game = "Dota Underlords"
[perception]
entities = ["Slark"]
resources = [{ type = "gold", value = "52" }]
options = ["Buy Slark", "Reroll", "Buy XP"]
[expected]
decision = "ADVISE"
mention = ["Slark"]
"""

TOML_SILENT = """\
[case]
[expected]
decision = "ABSTAIN"
"""


def _jpg(colour: int = 60) -> bytes:
    # Stripe and circle patterns are far enough apart for the dhash change
    # filter to always see them as different screens (mirrors test_coach_stability).
    img = Image.new("L", (64, 64), colour)
    draw = ImageDraw.Draw(img)
    if colour >= 50:
        for y in range(0, 64, 10):
            draw.rectangle([0, y, 64, y + 5], fill=230)
    else:
        draw.ellipse([4, 4, 60, 60], fill=250)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _write_case(dataset, name: str, toml: str, frame: bytes | None = None):
    d = dataset / name
    d.mkdir(parents=True)
    (d / "case.toml").write_text(toml)
    (d / "frame.jpg").write_bytes(frame or _jpg())
    return d


class _FrameProvider:
    """Returns a payload chosen by the frame it receives, ABSTAIN otherwise."""

    name, model = "fake", "fake-1"

    def __init__(self, by_frame: dict[bytes, dict] | None = None, sequence: list[dict] | None = None):
        self.by_frame = by_frame or {}
        self.sequence = sequence or []
        self.calls = 0

    def chat(self, system, messages, **kwargs):
        self.calls += 1
        if self.sequence:
            return SimpleNamespace(text=json.dumps(self.sequence[min(self.calls, len(self.sequence)) - 1]))
        frame = base64.standard_b64decode(messages[0].images[0]["data"])
        payload = self.by_frame.get(frame, SILENT)
        return SimpleNamespace(text=json.dumps(payload))


def _obs(payload: dict):
    return parse_observation(json.dumps(payload))


# ---- dataset loading --------------------------------------------------------
def test_load_case_parses_annotation(tmp_path):
    d = _write_case(tmp_path, "case-a", TOML_ADVISE, frame=_jpg(90))
    case = load_case(d)
    assert case.name == "case-a"
    assert case.game == "Dota Underlords"
    assert case.expects_advice
    assert case.has_perception_annotations
    assert [r.type for r in case.resources] == ["gold"]
    assert case.mention == ["Slark"]


def test_load_case_fails_closed(tmp_path):
    d = _write_case(tmp_path, "no-frame", TOML_ADVISE)
    (d / "frame.jpg").unlink()
    with pytest.raises(CaseError):
        load_case(d)
    d2 = tmp_path / "no-toml"
    d2.mkdir()
    (d2 / "frame.jpg").write_bytes(_jpg())
    with pytest.raises(CaseError):
        load_case(d2)
    bad = _write_case(tmp_path, "bad-decision", TOML_ADVISE.replace("ADVISE", "MAYBE"))
    with pytest.raises(CaseError):
        load_case(bad)
    broken = _write_case(tmp_path, "broken-toml", "[case\nfoo =")
    with pytest.raises(CaseError):
        load_case(broken)


def test_load_cases_skips_helpers_but_fails_on_broken_cases(tmp_path):
    dataset = tmp_path / "ds"
    _write_case(dataset, "case-a", TOML_ADVISE)
    (dataset / "results").mkdir()
    (dataset / "_helper").mkdir()
    (dataset / "README.md").write_text("x")
    assert [c.name for c in load_cases(dataset)] == ["case-a"]
    (dataset / "case-b").mkdir()  # a directory without annotation is an error, not a skip
    with pytest.raises(CaseError):
        load_cases(dataset)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(CaseError):
        load_cases(empty)


# ---- graders ----------------------------------------------------------------
def test_state_text_covers_structured_state():
    text = state_text(_obs(SHOP))
    assert "slark" in text and "gold" in text and "52" in text


def test_perception_reports_missing_facts(tmp_path):
    case = load_case(_write_case(tmp_path, "c", TOML_ADVISE.replace('"Slark"]', '"Slark", "Tidehunter"]')))
    notes = grade_observation(case, _obs(SHOP), accepted=True, reject_reason="ok", latency_s=1.0)
    assert any("entity not read: Tidehunter" in n for n in notes.notes)
    assert notes.measures["perception"] is False


def test_grounding_flags_unavailable_options(tmp_path):
    case = load_case(_write_case(tmp_path, "c", TOML_ADVISE))
    payload = json.loads(json.dumps(SHOP))
    payload["state"]["available_options"].append("Buy Anti-Mage (4)")
    record = grade_observation(case, _obs(payload), accepted=True, reject_reason="ok", latency_s=1.0)
    assert any("option not on the frame: Buy Anti-Mage" in n for n in record.notes)
    assert record.measures["grounding"] is False


def test_grounding_requires_the_annotated_subject(tmp_path):
    case = load_case(_write_case(tmp_path, "c", TOML_ADVISE))
    payload = json.loads(json.dumps(SHOP))
    payload["advice"] = "Reroll the shop, the board is fine."
    record = grade_observation(case, _obs(payload), accepted=True, reject_reason="ok", latency_s=1.0)
    assert any("references none of" in n for n in record.notes)


def test_silence_case_fails_when_advice_is_delivered(tmp_path):
    case = load_case(_write_case(tmp_path, "c", TOML_SILENT))
    record = grade_observation(case, _obs(SHOP), accepted=True, reject_reason="ok", latency_s=1.0)
    assert record.measures["decision"] is False
    assert record.measures["grounding"] is False
    assert not record.passed


def test_latency_and_perception_na(tmp_path):
    silent_case = load_case(_write_case(tmp_path, "silent", TOML_SILENT))
    record = grade_observation(
        case=silent_case, obs=_obs(SILENT), accepted=False, reject_reason="abstain", latency_s=99.0
    )
    assert record.measures["latency"] is False
    assert record.measures["perception"] is None  # no annotations: not applicable
    assert not record.passed


# ---- full runs --------------------------------------------------------------
def test_live_run_passes_and_writes_a_replayable_report(tmp_path):
    dataset = tmp_path / "ds"
    shop_frame = _jpg(90)
    _write_case(dataset, "shop", TOML_ADVISE, frame=shop_frame)
    _write_case(dataset, "ambiguous", TOML_SILENT, frame=_jpg(20))
    provider = _FrameProvider({shop_frame: SHOP})
    report, code = run_dataset(
        dataset,
        Config(),
        provider_factory=lambda: provider,
        out=tmp_path / "report.json",
        log=lambda *a: None,
    )
    assert code == 0
    assert provider.calls == 2
    assert report["summary"]["cases"] == 2
    assert report["summary"]["pass_1"] == 1.0
    assert report["summary"]["measures"]["perception"]["applicable_cases"] == 1
    assert (tmp_path / "report.json").is_file()
    replayed, code = run_replay(
        dataset, tmp_path / "report.json", Config(), out=tmp_path / "replay.json", log=lambda *a: None
    )
    assert code == 0
    assert replayed["mode"] == "replay"
    assert all("replayed" in r["notes"] for c in replayed["cases"] for r in c["runs"])


def test_live_run_reports_failures_with_exit_code_1(tmp_path):
    dataset = tmp_path / "ds"
    _write_case(dataset, "shop", TOML_ADVISE)
    report, code = run_dataset(
        dataset, Config(), provider_factory=_FrameProvider, out=tmp_path / "r.json", log=lambda *a: None
    )
    assert code == 1
    assert report["summary"]["pass_1"] == 0.0
    assert report["cases"][0]["pass_at_k"] is False


def test_repeat_metrics_distinguish_pass_at_k_from_pass_hat_k(tmp_path):
    dataset = tmp_path / "ds"
    _write_case(dataset, "shop", TOML_ADVISE)
    provider = _FrameProvider(sequence=[SILENT, SHOP, SHOP])
    report, code = run_dataset(
        dataset,
        Config(),
        repeat=3,
        provider_factory=lambda: provider,
        out=tmp_path / "r.json",
        log=lambda *a: None,
    )
    assert provider.calls == 3
    case = report["cases"][0]
    assert case["pass_1"] is False
    assert case["pass_at_k"] is True
    assert case["pass_hat_k"] is False
    assert code == 1
    assert report["summary"]["pass_at_3"] == 1.0
    assert report["summary"]["pass_hat_3"] == 0.0


def test_replay_regrades_under_the_current_gate_without_a_model_call(tmp_path):
    dataset = tmp_path / "ds"
    frame = _jpg(60)
    _write_case(dataset, "shop", TOML_ADVISE, frame=frame)
    _, _ = run_dataset(
        dataset,
        Config(),
        provider_factory=lambda: _FrameProvider({frame: SHOP}),
        out=tmp_path / "live.json",
        log=lambda *a: None,
    )
    strict = Config()
    strict.coach.min_confidence = 0.9  # SHOP has confidence 0.85: the gate now rejects it
    report, code = run_replay(
        dataset, tmp_path / "live.json", strict, out=tmp_path / "replay.json", log=lambda *a: None
    )
    assert code == 1
    run = report["cases"][0]["runs"][0]
    assert run["reject_reason"] == "low_confidence"
    assert run["accepted"] is False


def test_replay_fails_closed_when_a_case_is_gone(tmp_path):
    dataset = tmp_path / "ds"
    frame = _jpg(60)
    _write_case(dataset, "shop", TOML_ADVISE, frame=frame)
    _, _ = run_dataset(
        dataset,
        Config(),
        provider_factory=lambda: _FrameProvider({frame: SHOP}),
        out=tmp_path / "live.json",
        log=lambda *a: None,
    )
    (dataset / "shop" / "case.toml").unlink()
    with pytest.raises(CaseError):
        run_replay(dataset, tmp_path / "live.json", Config(), log=lambda *a: None)


def test_provider_errors_become_failed_runs_not_crashes(tmp_path):
    dataset = tmp_path / "ds"
    _write_case(dataset, "shop", TOML_ADVISE)

    class _DeadProvider:
        name, model = "fake", "fake-1"

        def chat(self, **kwargs):
            raise RuntimeError("quota exhausted")

    report, code = run_dataset(
        dataset,
        Config(),
        provider_factory=lambda: _DeadProvider(),
        out=tmp_path / "r.json",
        log=lambda *a: None,
    )
    assert code == 1
    run = report["cases"][0]["runs"][0]
    assert run["reject_reason"] == "provider_error"
    assert all(value is False for value in run["measures"].values())
    assert any("provider error" in n for n in run["notes"])


# ---- CLI wiring -------------------------------------------------------------
def test_eval_cli_replay_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setattr("gamebuddy.config.load_config", lambda *a, **k: Config())
    dataset = tmp_path / "ds"
    frame = _jpg(60)
    _write_case(dataset, "shop", TOML_ADVISE, frame=frame)
    run_dataset(
        dataset,
        Config(),
        provider_factory=lambda: _FrameProvider({frame: SHOP}),
        out=tmp_path / "live.json",
        log=lambda *a: None,
    )
    assert (
        main(
            [
                "eval",
                str(dataset),
                "--replay",
                str(tmp_path / "live.json"),
                "--out",
                str(tmp_path / "re.json"),
            ]
        )
        == 0
    )
    assert main(["eval", str(tmp_path / "nowhere")]) == 2


# ---- candidate frames feed the dataset --------------------------------------
def _pipeline(
    tmp_path, monkeypatch, cfg: Config, frames: list[bytes], by_frame: dict[bytes, dict] | None = None
):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    advice: list = []
    pipeline = CoachPipeline(
        cfg=cfg,
        store=Store(tmp_path / "coach.db"),
        provider_factory=lambda: _FrameProvider(by_frame or {}),
        capture=lambda: frames.pop(0) if frames else None,
        on_advice=advice.append,
    )
    return pipeline, advice


def test_save_frames_keeps_one_file_per_candidate(tmp_path, monkeypatch):
    shop_frame, other_frame = _jpg(90), _jpg(20)
    cfg = Config()
    cfg.coach.save_frames = True
    pipeline, advice = _pipeline(
        tmp_path, monkeypatch, cfg, [shop_frame, shop_frame, other_frame], {shop_frame: SHOP}
    )
    pipeline.tick()
    directory = tmp_path / "xdg" / "gamebuddy" / "coach_frames" / "unknown"
    assert len(list(directory.glob("*.jpg"))) == 1  # first candidate saved
    pipeline.tick()  # unchanged frame: stability delivery, not a new candidate
    assert len(advice) == 1
    assert len(list(directory.glob("*.jpg"))) == 1
    pipeline.tick()  # a new frame becomes a new candidate
    assert len(list(directory.glob("*.jpg"))) == 2


def test_save_frames_stays_bounded(tmp_path, monkeypatch):
    cfg = Config()
    cfg.coach.save_frames = True
    pipeline, _ = _pipeline(tmp_path, monkeypatch, cfg, [])
    for i in range(MAX_SAVED_FRAMES + 5):
        pipeline._save_frame(f"frame-{i}".encode())
    directory = tmp_path / "xdg" / "gamebuddy" / "coach_frames" / "unknown"
    files = sorted(directory.glob("*.jpg"))
    assert len(files) == MAX_SAVED_FRAMES
    assert files[-1].read_bytes() == f"frame-{MAX_SAVED_FRAMES + 4}".encode()
