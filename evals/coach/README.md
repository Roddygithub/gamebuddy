# Coach evals

Measure what the coach actually does on annotated captures instead of trusting
a green unit-test suite. The harness is `gamebuddy eval` (see
`docs/COACH-MODE.md` for the pipeline it exercises); the method follows
eval-driven development: define expected behaviour first, grade every change
against it, track reliability over time.

## The four measures

Every case is graded on four independent measures:

| Measure | Question | Fails when |
|---|---|---|
| `perception` | Does the coach read what is on the frame? | an annotated entity, resource or option is missing from the structured state |
| `grounding` | Is the advice about the options really on the frame? | the delivered advice names an option that is not annotated, or misses the annotated subject |
| `latency` | Does the answer arrive in time? | the call took longer than `latency_budget_s` |
| `decision` | Does the coach stay silent when the frame is ambiguous? | the model says ADVISE on a silence case, or withholds on an ADVISE case |

A case passes when every applicable measure passes. Silence cases never deliver
advice (the gate rejects), so their `grounding` check is "nothing was
delivered".

## Case format

A case is a directory with one frame and one annotation:

```
evals/coach/
  my-game-shop/
    frame.jpg    # the capture exactly as the coach would see it
    case.toml    # the annotation below
```

```toml
[case]
game = "Dota Underlords"          # optional, sent with the perception prompt
description = "Shop with an affordable carry"  # optional, human notes
synthetic = true                   # optional, marks drawn (not captured) frames

[perception]                       # optional: facts that must be readable
entities = ["Slark"]
resources = [{ type = "gold", value = "52" }]
options = ["Buy Slark", "Reroll"]  # what the frame really offers

[expected]
decision = "ADVISE"                # ADVISE | ABSTAIN | NEED_MORE_EVIDENCE
mention = ["Slark"]                # optional: words the advice must reference
latency_budget_s = 20.0            # optional, default 20
```

`NEED_MORE_EVIDENCE` and `ABSTAIN` annotations accept either withheld decision:
both must keep the gate closed.

## Running

```sh
gamebuddy eval evals/coach                     # live, once per case
gamebuddy eval evals/coach --repeat 3          # pass@3 / pass^3 reliability
gamebuddy eval evals/coach --replay <report>   # re-grade recorded answers, no model call
```

Exit code: `0` every case passed every run, `1` at least one run failed, `2`
the dataset itself is broken (missing frame, bad TOML, replay source missing a
case — the harness fails closed rather than measuring less than you asked).

Reports land in `evals/coach/results/` (git-ignored) and keep the raw reasoner
answers, which is what makes `--replay` possible: after changing the prompt or
the gate, replay the last live report to see what the same answers would do
under the new rules.

## Workflow for real captures

1. Play with coach mode on and `coach.save_frames = true` in `config.toml`.
   Every candidate frame lands in `~/.local/share/gamebuddy/coach_frames/<game>/`
   (last 200 kept per game, directory is `700` like the rest of the data dir).
2. Pick 20–30 frames showing decision windows you remember; copy each into a
   case directory and write the annotation from memory of what was actually
   true (heroes, stars, gold, options).
3. Run `gamebuddy eval evals/coach --repeat 3` and read the failures: they
   name what to fix next (perception → capture/OCR work, grounding → prompt or
   gate, decision → gate thresholds).
4. Re-run after every coach change; keep an eye on `pass^k`, which is the
   reliability number, not the best-of-k one.

Anti-goals: do not tune the prompt until it passes these exact frames
(overfitting), and do not grade only happy-path frames — ambiguous frames
expecting silence are the ones that keep the coach welcome at your desk.
