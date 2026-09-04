# campaign-planner

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

Catalog id `campaign-planner`. Campaign planning and budget allocation: deterministic segment selection,
channel split, reach and frequency, and the pacing calendar, with the model drafting only the
creative brief and the plan narrative.

## Concrete bindings

| | |
|---|---|
| Catalog id | `campaign-planner` |
| Package | `src/campaign_planner/` |
| Profile variable | `MKT_CAMPAIGN_PROFILE` |
| Adapter families | `gcp`, `local`, `onprem`, `platform` |
| Gate | `make gate` (`lint format typecheck test eval demo-selftest portability`) |

`config.resolve_profile` is the only reader of that variable, and it resolves three states.
Unset is NO CHOICE: the SDK-free adapters bind so the process can still boot, but every
relaxation sees `UNCONSENTED_PROFILE` (`unconfigured`) instead of `local`, and the seeded
dev personas refuse to be served. Set-and-empty raises `ConfiguredEmptyError` rather than
inheriting the unset case. An unknown or mis-capitalised value raises, because the comparison
against `RUNTIME_PROFILES` is exact. `tests/unit/test_profile_single_source.py` fails the build
if any other module re-derives the profile from the environment.

## What this repository still owes

The `Capability gaps` cell on this repository's row in the maintainer's system tracker
is the authoritative list. Its verdict against the shared checks, including the ones it
does not pass, is in [`docs/practices-audit.md`](docs/practices-audit.md).
