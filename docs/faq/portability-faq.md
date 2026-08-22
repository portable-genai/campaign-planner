# Portability FAQ

For architecture, cloud, and exit-planning reviewers who want to know how real the
"no lock-in" claim is and how an off-cloud or sovereign exit would work.

## What is the no-lock-in claim, concretely?

The `domain/` package is pure standard library: no Google Cloud SDK, no FastAPI, no httpx,
no pydantic. All infrastructure lives behind `@runtime_checkable` `Protocol` ports in
`ports/`, and adapters are selected by one setting. `grep -rE "google|fastapi|httpx|pydantic"
src/campaign_planner/domain/` returns nothing (audit check A1).

## What are the four profiles?

`MKT_CAMPAIGN_PROFILE` selects the whole adapter stack:

- **`local`** - a real, working, SDK-free offline stack: a deterministic audience-data store
  and a deterministic LLM. This is the dev / test / CI default and the working proof that the
  domain runs entirely off-cloud.
- **`gcp`** - the managed Google Cloud services (BigQuery audience, Gemini, Model Armor,
  Cloud Logging WORM, Cloud Trace, Gen AI eval, A2A registry, MCP catalog), with lazy imports
  so the module tree stays importable without the SDK.
- **`platform`** - thin HTTP clients to the shared platform siblings (guardrail, registry,
  eval, audit, review router).
- **`onprem`** - fail-fast placeholders that satisfy the same Protocols; they raise
  `NotImplementedError` and name the migration target, proving the ports are honest exit
  seams rather than decoration.

## Is the portability claim tested, or just asserted?

Tested. `scripts/portability_demo.py` runs offline and exits non-zero on any failed claim: a
profile swap (local vs onprem), full port parity, a replayable open-format audit, and an
identity swap. The contract tests (`tests/contract/test_port_parity.py`,
`test_behavioral_parity.py`) prove every port satisfies its Protocol, constructs from a
single `Settings` arg, and behaves identically through the local and onprem placeholders.

## How would a sovereign / on-prem exit actually go?

The `onprem` profile is the scaffold. Each fail-fast placeholder marks a seam where a client
supplies their own component (their audience warehouse, their model host, their IdP, their
audit store, their review console). Because the domain never changes, the exit is an adapter
exercise, not a rewrite. See [`../onprem-migration.md`](../onprem-migration.md) for the
migration guide and [`../runbook.md`](../runbook.md) for operations.

## How is data residency handled across markets?

Region is selected at deploy from a residency allowlist, with per-market overrides that are
config plus seed, never a hard-coded branch: JP -> `asia-northeast1`, AU ->
`australia-southeast1`, SG -> `asia-southeast1` (the default). `infra/terraform/` pins and
validates `var.region`, applies a `gcp.resourceLocations` Org Policy allowlist, and stands up
a dry-run-first VPC-SC perimeter. A second market or tenant is a tfvars change, not a fork.

## Can the data be exported in an open format?

Yes. `domain/serialization.py::to_jsonable` converts a plan and every audit event to plain
JSON (dataclasses, enums, datetimes, nested containers, plus the computed `@property`
rollups), so the append-only sink stores an open payload the domain reads back
byte-for-byte. This is the deliberate repo-owned serialization walker (it extends what the
commons provides so the JSON carries the computed figures); see
[adoption-faq.md](adoption-faq.md).

## What is honestly NOT portable?

Tamper-evidence and export-reload are scoped to what the local sink can prove;
`portability_demo.py` says so explicitly rather than overclaiming. Production tamper-evidence
is the managed WORM sink's job (Hrz5 / locked bucket), reached through the `platform` / `gcp`
audit adapter.
