# Coach mode

Coach mode is **off by default** and experimental. It follows the conclusions of the
Phase 0 research that preceded this project: a coach that comments on everything it sees is
wrong often enough to be harmful, so the pipeline is built to stay silent unless a slow,
clearly visible decision window justifies a sentence.

## Pipeline

```
capture (JPEG of the game window)
  → dhash change filter          (skip frames that did not change, coach.min_change)
  → cooldown                     (coach.cooldown_s since the last advice)
  → cheap reasoner (JSON)        (coach.model: claude-haiku-5-5 / gpt-4o-mini / same model on Ollama)
      structured state: entities, ownership, typed resources with provenance, options, unknowns
      decision: ADVISE | ABSTAIN | NEED_MORE_EVIDENCE
  → hard gate (coach/gate.py)
      ADVISE only; non-empty advice ≤ 400 chars
      confidence ≥ min_confidence and ownership_confidence ≥ min_confidence
      decision window open with confidence ≥ min_confidence, not a fast window (combat, aim…)
      at least one evidence item; no critical unknown field (owner, hp, gold, cost, cooldown, timer…)
      advice must name a specific option from the structured state (not just "buy")
      not ≥ 60 % similar to the previous advice
  → stability confirmation       (one re-capture at coach.confirm_poll_s: the advice goes out
                                  if the perceptual hash remains within its threshold; otherwise
                                  it is dropped. This approximate filter reduces transient advice
                                  but cannot guarantee that a HUD flash is rejected)
  → one line in the widget (optionally spoken)
```

The loop is **fixed-rate**: the next look is scheduled at `interval_s` after the
previous one, not after the previous turn finished, so a slow model call cannot
push every later observation back. A turn that falls behind is skipped, never
caught up in a burst. Each turn logs one line — outcome, `capture_ms`, `eval_ms`,
`confirm_ms`, `frame_kib` — and the same figures are kept in
`CoachPipeline.metrics["last_turn"]`: without a per-turn number, latency is
improved blind.

Every stage writes to the `coach_log` table (`gamebuddy.db`): `pre_gate:cooldown`,
`pre_gate:await_stability`, `pre_gate:delivered`, `parse:error`, `gate:accepted`,
`gate:<reason>`. `Store.coach_stats()` aggregates them, so the
ratio of reasoner calls to accepted advice can be audited per game.

## Intended first use cases

Shop and item choices, hero/unit/card picks, upgrades and talents, rerolls, economy decisions,
preparation phases, between-round decisions, post-event micro-debriefs. Not fast combat.

## Perception: image-first, OCR deferred

The current coach sends the full frame to a vision model; there is no OCR or crop pass. This
is a current implementation choice, not a conclusion that OCR cannot help. A health bar,
cooldown, range or minimap needs visual context; OCR may still help anchor shop names and
resource numbers, but misread values must not become confident advice.

Tesseract is installed on the development machine but is not a GameBuddy dependency. Before
adding it, compare screenshot-only and OCR-assisted readings on annotated real captures,
including stylised fonts and ambiguous values. The Coach gate currently cannot independently
prove that a value returned by either source is correct.

`CoachPipeline.can_see()` requires the selected model to accept images. A text-only model is
refused with `coach_needs_vision`; this guard is independent of the OCR decision. Chat remains
available with text-only models.

## Known gaps

- Perception is one model call on one frame, confirmed by one cheap re-capture before the
  advice is spoken. Every pixel is read at once, with no region refinement (HUD, shop, map).
- The gate validates structure and grounding, not game correctness. Treat advice as a prompt
  for your own judgement.
- Player-learning / adaptive suppression is limited to the long-term notes Buddy keeps
  (`remember`). Tracking mastery per mechanic is future work.

## Evaluating the coach

`gamebuddy eval evals/coach` runs the annotated eval dataset: each case is one
frame plus a `case.toml` annotation, graded on four measures — perception,
grounding, latency, and the decision to stay silent — with pass@k / pass^k
reliability metrics. `--replay` re-grades a previous report without calling the
model, so prompt or gate changes can be regression-checked for free. The case
format and the dataset workflow live in
[evals/coach/README.md](../evals/coach/README.md).

Set `coach.save_frames = true` to keep every candidate frame under
`~/.local/share/gamebuddy/coach_frames/<game>/` (last 200 per game), then
annotate the interesting ones to grow the dataset from real sessions. Run the
evals before and after every change to the coach prompt or the gate: a green
unit-test suite alone says nothing about whether Buddy reads your bench
correctly.
