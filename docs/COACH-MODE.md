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
  → stability confirmation       (the advice is held for one interval and delivered only when the
                                  next capture shows the same screen, so a HUD flash never lands)
  → one line in the widget (optionally spoken)
```

Every stage writes to the `coach_log` table (`gamebuddy.db`): `pre_gate:cooldown`,
`pre_gate:await_stability`, `pre_gate:delivered`, `parse:error`, `gate:accepted`,
`gate:<reason>`. `Store.coach_stats()` aggregates them, so the
ratio of reasoner calls to accepted advice can be audited per game.

## Intended first use cases

Shop and item choices, hero/unit/card picks, upgrades and talents, rerolls, economy decisions,
preparation phases, between-round decisions, post-event micro-debriefs. Not fast combat.

## Known gaps

- Perception is one model call on one frame, confirmed by an unchanged frame before the advice
  is spoken (a candidate that expires is dropped). OCR is not implemented, so typed numbers are
  read from pixels like everything else.
- The gate validates structure and grounding, not game correctness. Treat advice as a prompt
  for your own judgement.
- Player-learning / adaptive suppression is limited to the long-term notes Buddy keeps
  (`remember`). Tracking mastery per mechanic is future work.
