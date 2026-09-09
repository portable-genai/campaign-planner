# How the campaign planner is evaluated

Read this page if you decide what this service is allowed to plan. The metrics, the bars and the
corpora below are generated from the artifacts that actually gate the build, so they cannot drift
from what runs: `make evals-doc-check` fails the build when this page and those artifacts
disagree.

## How to run it

```sh
make eval              # offline, no credentials
make evals-doc-check   # this page is still true
```

`make gate` runs both on every change.

## Arithmetic closure is not allocation correctness

`budget_accuracy` reconciles totals: it asks whether the allocation and the pacing add up to the
budget. They add up to the budget **however the money is split**, so a plan that put the whole
budget on one channel, or on a channel nobody published a cost for, scores a perfect 1.000 there.
The claim a media planner cares about is not "the numbers add up".

`allocation_correctness` asks the other question, against the SHIPPED demo book's channel
benchmarks, per market and vertical. Two halves that fail in opposite directions:

- **on priced channels**: every channel carrying spend has a published benchmark for this market
  and vertical. Spend on an unpriced channel is spend nobody can cost, and it is what an
  allocator produces when a channel list drifts from the benchmark table.
- **diversified**: the mix draws on more than one priced channel. A single-channel plan is not a
  mix, and it is exactly what a cost-minimising allocator produces when nothing stops it, because
  the cheapest CPM takes everything.

The oracle is the book, not a list restated in the eval. The channels the gate measures against
are the channels the demo prices, so a book edit moves both together instead of moving only one.
That is the same render-and-check discipline the fleet uses for golden inputs, applied to an
oracle.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. There is no dict of thresholds in the runner any more: a
metric scored with no reviewed bar fails the build, and so does a bar that names no
metric, which is the direction that rots quietly because it rots toward looking well
governed.

The third column is the denominator rule, and it applies only where a score is a
FRACTION over scored positives: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` of them. `all or nothing` marks a bar that already asks for no
headroom, so a bigger corpus would not change what it means. Each rubric declares which
it is rather than the rule being guessed from the number.

| Metric | Bar | Denominator | What it measures |
|---|---|---|---|
| `allocation_correctness` | 1 | all or nothing | The budget lands on channels the demo book prices for this market and vertical, and on more than one of them. |
| `budget_accuracy` | 1 | a rate; needs 0 positives | Fraction of golden cases where the channel-mix allocation AND the flight pacing reconcile to the requested total budget within tolerance. |
| `citation_accuracy` | 1 | a rate; needs 0 positives | Fraction of cited source ids that appear in the derived evidence set (no fabricated citations). |
| `plan_groundedness` | 0.8 | a rate; needs 5 positives | Fraction of plans whose selected segments and budget lines all carry at least one citation. A plan built on uncited figures fails. |
| `review_safety` | 1 | a rate; needs 0 positives | Fraction of plans that correctly set requires_human_review=True (maker-checker). |

Scored over 6 golden plans.

## What is exercised

- **6 golden plans** in `eval/datasets/golden_plans.jsonl`, across
  AU, JP, SG and both verticals.
- **30 channel benchmarks from the SHIPPED demo book**, across
  6 market and vertical pairs. That is the oracle
  `allocation_correctness` measures against, and it is the book rather than a list
  restated in the eval: the channels the gate measures are the channels the demo prices,
  so a book edit moves both together instead of moving only one.

## What is NOT measured here

- **Whether the split is optimal.** `allocation_correctness` says the money is on channels this
  market prices and on more than one of them. It does not say the shares are right, which needs a
  performance oracle nothing here has.
- **A real model's words.** Every metric scores a deterministic core against a deterministic fake
  LLM adapter.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.
