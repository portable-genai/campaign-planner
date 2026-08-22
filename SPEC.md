# SPEC - Mkt2 Campaign Planning and Budget Allocation

## Purpose

Turn a campaign objective, a budget and a flight window into a **cited, auditable campaign
plan**: which audience to target, how to split the budget across channels, the reach and
frequency that buys, and the pacing calendar. Generic across banking and online retail and
the JP / AU / SG markets.

## Inputs (PlanRequest)

| Field | Meaning |
| --- | --- |
| `objective` | Campaign objective / topic |
| `market` | JP / AU / SG (residency region + locales resolved from the market profile) |
| `vertical` | banking / online_retail |
| `total_budget` | Total spend in the market currency |
| `start_date`, `end_date` | The flight window (inclusive) |
| `flight_legs` | Number of pacing legs |
| `pacing` | even / front_loaded / back_loaded |
| `max_segments` | Cap on targeted audience segments |
| `channels` | Optional channel allow-list |
| `effective_frequency` | The effective ("N+") frequency threshold |

## Output (Plan) - always `requires_human_review=True`

- `segments` - ranked, cited `SelectedSegment`s (deterministic score).
- `channel_mix` - cited `BudgetLine`s + computed rollups (allocated, expected conversions,
  blended CAC). Allocation reconciles to the budget exactly.
- `reach_frequency` - impressions, unique reach, average frequency, effective reach.
- `flight_schedule` - paced legs that reconcile to the budget exactly.
- `creative_brief`, `summary` - LLM-drafted over the deterministic plan, grounded and cited.
- `citations` - the union of every figure's provenance.

## Determinism contract

Each engine is pure: same inputs -> same output, no clock / randomness / network / I/O. The
budget allocation and pacing reconcile to the requested total within a currency-rounding
tolerance. These properties are pinned by unit tests and the Hrz4 eval gate
(`budget_accuracy >= 0.99`).

## Quality gate (Hrz4)

| Metric | Threshold | Meaning |
| --- | --- | --- |
| `plan_groundedness` | 0.80 | Segments and budget lines carry citations |
| `citation_accuracy` | 0.90 | Cited ids are within the derived evidence set |
| `budget_accuracy` | 0.99 | Allocation + pacing reconcile to the budget |
| `review_safety` | 0.99 | Every plan requires human review |

The `local` profile scores these thresholds offline via `eval/run_eval.py`. The `platform`
profile is a real HTTP client to the Hrz4 AI-quality service (not a stub): it calls
`POST /v1/evaluations` (returning `results[]`) and `POST /v1/gate` (the promotion decision),
with the metric set selected server-side by the registered `mkt2-campaign` bundle, so the
client never sends a metric-name list.

## Non-goals

- The LLM never decides a number (audience, budget, reach, pacing) - only drafts prose.
- No spend is committed; the plan is a maker proposal pending a human checker.
