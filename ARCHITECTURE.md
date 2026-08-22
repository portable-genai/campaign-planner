# Architecture - Mkt2 Campaign Planning and Budget Allocation

Hexagonal ports-and-adapters. The domain core is pure standard-library Python; everything
external is reached through a typed `Protocol` port with swappable adapter profiles.

## The hexagon

```
                +-------------------- driving adapters --------------------+
                |   CLI (mkt-campaign)        FastAPI (:8101)   agent/      |
                +---------------------------+------------------------------+
                                            |
                                  CampaignPlanService (orchestrator)
                                            |
        +------------------ deterministic engines (pure stdlib) ------------------+
        |  AudienceSelectionService   BudgetAllocationService                     |
        |  ReachFrequencyService      PacingService                              |
        +------------------------------------------------------------------------+
                                            |
                                    ports (typing.Protocol)
   AudienceDataPort  LlmPort  GuardrailPort  AuditSinkPort  ObservabilityTracerPort
   EvaluationGatePort  AgentRegistryPort  ToolCatalogPort  IdentityPort
                                            |
        +----------- driven adapters (one family per profile) -------------+
        |  gcp/      BigQuery, Gemini, Model Armor, Cloud Logging WORM,     |
        |            Cloud Trace, Gen AI eval, A2A registry, MCP catalog    |
        |  local/    seeded store, deterministic LLM, heuristic guardrail,  |
        |            append-only audit, no-op tracer, offline eval gate     |
        |  onprem/   fail-fast NotImplementedError placeholders             |
        |  platform/ thin HTTP clients to the shared platform siblings      |
        +------------------------------------------------------------------+
```

## The deterministic engines are the heart

The consequential decisions are pure, replayable code (same inputs -> same output), not LLM
calls. The LLM only drafts the creative brief and narrates the plan summary.

1. **AudienceSelectionService** - ranks candidate segments by a transparent
   `propensity x normalised_value x consent` score and drops segments with no consented,
   reachable audience (respects PDPA / APP / consent rules generically).
2. **BudgetAllocationService** - efficiency-greedy allocation: fills the most
   cost-per-conversion-efficient channels to their reach-saturation spend first, then
   distributes any remainder by reach capacity so the full budget always reconciles exactly.
   Per-channel unique reach stays capped; minimum-spend floors are honoured.
3. **ReachFrequencyService** - de-duplicated unique reach via the standard independence
   combination, average frequency, and effective ("3+") reach over the addressable audience.
4. **PacingService** - splits the flight into legs and distributes the budget by an explicit
   weight curve (even / front-loaded / back-loaded); the legs reconcile to the budget exactly.

## Provenance, review and audit

- Every figure carries a `Citation` (audience-data row or channel benchmark).
- Every `Plan` and `ChannelMix` sets `requires_human_review=True` (maker-checker): nothing
  spend-affecting auto-executes.
- Every interaction is written to an immutable (WORM) audit record.

## Identity (server-verified)

The API resolves a verified `Principal` per request through `IdentityPort`
(`api/security.py` -> the active profile's adapter) and uses it as the audit actor; a
client-supplied `actor` is never accepted. `local` binds seeded dev personas (selected via
`X-Dev-Persona`, no IdP), `gcp`/`platform` verify the Cloud IAP-injected assertion (lazy
Google imports), `onprem` is the fail-fast client-IdP placeholder. Embedding-surface
controls (env-driven CORS allowlist, CSP `frame-ancestors`) live in `api/app.py`; see
[docs/embedding-and-identity.md](docs/embedding-and-identity.md).

## Generic, multi-vertical, APAC

- `Vertical` (banking | online_retail) and `Market` (JP | AU | SG) are settings + seed.
- Per-market residency regions and locales come from `MARKET_PROFILES` / `config/settings.yaml`,
  validated by the GCP region resolver. Adding a market or vertical is a config + seed change.

## Profiles and the DI container

`config.py` reads `config/settings.yaml` and binds each port to an adapter by dotted path
for the active `profile`. `MKT_CAMPAIGN_PROFILE` selects `gcp` / `local` / `onprem` /
`platform`. GCP SDK imports are lazy (in-method), so the local / onprem / test profile never
needs `google-cloud-*` installed.

---

## 6. Portability principles (a reusable catalogue)

Portability here means lock-in converted from an open-ended exposure into a priced,
controlled risk. It has to hold at three layers: compute (where the decision logic runs),
data (records, audit trails), and experience/identity (where users reach the system and how
they sign in). Each principle below is stated generically (steal it), then grounded in this
repo (mechanism plus proof). This catalogue keeps the PT numbering of the sibling
[`cdd-sow-research/ARCHITECTURE.md`](../cdd-sow-research/ARCHITECTURE.md) section 6 so the
two cross-reference cleanly. The one-command version of this whole section is the offline
portability tour:

```bash
PYTHONPATH=src MKT_CAMPAIGN_PROFILE=local python scripts/portability_demo.py   # exit 0 only if every claim holds
```

Not applicable to this repo (omitted, no fabricated proof): **PT-9** (no knowledge-base /
search-index port, so there is no derived index to rebuild), **PT-10** (the local audit sink
is append-only WORM-stand-in with no per-record hash chain and no JSONL export/reload, so the
tamper-evidence + round-trip claim does not hold here; managed immutability is SC-11),
**PT-14** (this repo's [`infra/terraform/outputs.tf`](infra/terraform/outputs.tf) descriptions
do not name the `MKT_*` environment variables the app reads, and there is no `docs/runbook.md`
export block, so the "outputs are the app's env contract" claim is not yet true).

### 6.1 Compute layer

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| PT-1 | **Pure decision core.** The domain imports nothing from any vendor: no cloud SDK, no web framework, not even the config parser. Everything external is a narrow interface. | [`domain/`](src/campaign_planner/domain/) is stdlib-only; the 9 interfaces live in [`ports/`](src/campaign_planner/ports/) as `@runtime_checkable typing.Protocol`s. | `grep -rnE "^\s*(import\|from)\s+(google\|fastapi\|httpx\|pydantic\|yaml\|uvicorn\|typer)" src/campaign_planner/domain/` returns nothing. |
| PT-2 | **One construction convention, config-driven binding.** Every adapter is built the same way from one settings object, and the port-to-adapter wiring is data (a config file), not code. Swapping vendors is an edit to config, reviewable in a diff. | `Adapter(settings: Settings)` for all adapters; dotted-path bindings under `adapters:` in [`config/settings.yaml`](config/settings.yaml); the `Container` in [`config.py`](src/campaign_planner/config.py) resolves them lazily, one `cached_property` per port. | `pytest tests/contract/test_port_parity.py::test_adapter_constructs_with_single_settings_arg` |
| PT-3 | **A profile swaps the whole stack.** One environment variable selects a coherent adapter family for every port at once, so an offline or sovereign run is a config change, not a code change. | `MKT_CAMPAIGN_PROFILE` = `local` (SDK-free default) \| `gcp` \| `platform` \| `onprem`; `Container._bind` picks the active profile's binding for every port (falling back to the `gcp` entry only under `platform`, the reviewed alias, for the three ports the shared plane does not front). | Act 1 of the tour; `MKT_CAMPAIGN_PROFILE=onprem mkt-campaign 'savings acquisition' --market SG` exits 2 while `MKT_CAMPAIGN_PROFILE=local` exits 0. |
| PT-4 | **Vendor imports are lazy.** SDK imports live inside methods or `TYPE_CHECKING`, never at module top level, so every module imports on a machine with no vendor packages installed. | All `adapters/gcp/*` Google imports are in-method; the GCP SDKs live in the optional `[gcp]` extra (see [`pyproject.toml`](pyproject.toml)). | `pytest tests/unit/test_gcp_adapters_import_safe.py::test_importing_gcp_family_does_not_pull_in_google` (the whole gate also runs in a venv with only `[dev]` installed). |
| PT-5 | **The offline profile WORKS: it is not a mock.** Ship a real, deterministic, in-process implementation of every port (seeded audience store, schema-driven LLM stand-in, heuristic guardrail, append-only audit) and make it the default for dev, tests and CI so it can never rot. | The `local` family: [`local/audience.py`](src/campaign_planner/adapters/local/audience.py) (seeded warehouse), [`local/llm.py`](src/campaign_planner/adapters/local/llm.py) (deterministic drafter), [`local/guardrail.py`](src/campaign_planner/adapters/local/guardrail.py) (heuristic), [`local/audit.py`](src/campaign_planner/adapters/local/audit.py) (append-only SQLite). `local` must be chosen deliberately: an unset `MKT_CAMPAIGN_PROFILE` still binds the SDK-free adapters (nothing else is installed) but is NOT read as consent to the `local` relaxations, so the seeded no-auth personas and the localhost CORS origins are refused. | `MKT_CAMPAIGN_PROFILE=local mkt-campaign 'savings acquisition' --market SG --vertical banking` prints a cited plan and exits 0, no cloud. |
| PT-6 | **The exit target exists on day one, as a fail-fast placeholder.** Stubs that construct cleanly, satisfy every interface and raise on use keep the migration honest: interface drift breaks CI, and nothing can silently return a wrong answer. | `adapters/onprem/*` construct with no dependency and raise `NotImplementedError` (e.g. [`onprem/audience.py`](src/campaign_planner/adapters/onprem/audience.py)); the CLI maps it to exit 2 with the migration note ([`cli/main.py`](src/campaign_planner/cli/main.py)). | `pytest tests/contract -q` |
| PT-7 | **Parity is tested behaviorally, not just structurally.** "Implements the interface" is weak; put the same request through the real implementations and require identical behavior at the boundary (same domain objects, same verdicts, byte-identical audit payloads), and require the placeholders to fail fast where documented. | [`tests/contract/test_behavioral_parity.py`](tests/contract/test_behavioral_parity.py): the same request through the `local` audience / guardrail / audit adapter twice yields byte-identical domain objects and payloads, the full pipeline is deterministic, and the `onprem` placeholders plus the still-scaffolded `platform` placeholders (audience / guardrail / audit / registry) raise `NotImplementedError`. The `platform` evaluation adapter is the exception: it is now a real Hrz4 HTTP client (`POST /v1/evaluations` + `/v1/gate`, metrics selected by the `mkt2-campaign` bundle), covered by [`tests/contract/test_remote_evaluation.py`](tests/contract/test_remote_evaluation.py). | `pytest tests/contract/test_behavioral_parity.py -q` |

### 6.2 Data layer (where switching cost compounds)

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| PT-8 | **Logical records are separated from physical stores.** The domain owns plain, framework-free record types; serialization to/from an open format is a documented, deliberate function, not an ORM side effect. | Frozen stdlib dataclasses in [`domain/models.py`](src/campaign_planner/domain/models.py); `to_jsonable` in [`domain/serialization.py`](src/campaign_planner/domain/serialization.py) converts a plan (and every audit event) to plain JSON, so the append-only sink stores an open payload the domain can read back. | `pytest tests/unit/test_serialization.py -q`; Act 3 of the tour reads an audit record back byte-identical to the domain serialization. |

### 6.3 Experience / identity layer

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| PT-11 | **Identity is verified on the system's own side**, from a signed credential, never trusted from the host application, and the verification regime is itself an adapter: dev personas offline, platform-injected assertion in managed mode, client IdP placeholder for sovereign. | `IdentityPort` with three bindings: seeded personas (`local`, no IdP), IAP-assertion verification (`gcp`/`platform`, [`gcp/iap_identity.py`](src/campaign_planner/adapters/gcp/iap_identity.py)), client-IdP placeholder (`onprem`, [`onprem/identity.py`](src/campaign_planner/adapters/onprem/identity.py)). | Act 4 of the tour; `pytest tests/unit/test_identity.py tests/unit/test_api_identity.py -q`. |
| PT-12 | **Every UI integration tier stays open**: native API integration, sandboxed embed, and a standalone link, so the capability is not welded to one host application. | REST API plus the A2A AgentCard, the embeddable console, and the standalone CLI / server; CSP `frame-ancestors` and an env-driven CORS allowlist live in [`api/app.py`](src/campaign_planner/api/app.py). | [`docs/embedding-and-identity.md`](docs/embedding-and-identity.md) |

### 6.4 Infrastructure as a replaceable input

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| PT-13 | **Infra names and postures are variables, not literals.** A second enterprise (or a second instance) must be a `tfvars` file, not a fork: the residency region is validated against an allowlist, and the org-level and irreversible pieces are explicit toggles. | [`infra/terraform/variables.tf`](infra/terraform/variables.tf): `project_id`, `region` (validated to `asia-southeast1`), `retention_days`, `enable_vpc_sc`, `vpc_sc_dry_run`, `org_id`, `access_policy_id`, `image`; a worked example in [`terraform.tfvars.example`](infra/terraform/terraform.tfvars.example). | `terraform -chdir=infra/terraform validate` (with `terraform fmt -check`) both pass. |

---

## 7. Security principles (a reusable catalogue)

Same format: the rule, the mechanism here, the proof. The theme is by construction, not by
convention: every control is enforced in code or infra and has a test or a fail-fast error,
so a regression is a red build rather than a policy violation discovered later. This
catalogue keeps the SC numbering of the sibling
[`cdd-sow-research/ARCHITECTURE.md`](../cdd-sow-research/ARCHITECTURE.md) section 7.

Not applicable to this repo (omitted, no fabricated proof): **SC-1** (no PII-redaction port:
campaign planning runs over aggregate, consent-gated audience segments and channel
benchmarks, not raw customer identifiers, so there is no redact-before-everything step to
prove), **SC-4** (no retrieval / knowledge-base port, so there is no ACL-scoped query layer),
**SC-9** (the IAP adapter delegates JWT verification to Google's `id_token.verify_token`
rather than a repo-owned JWKS + algorithm-pinning routine, so there is no in-repo token
verifier to prove here).

### 7.1 Data protection in the request path

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| SC-2 | **Screen both directions.** Guardrail the INPUT before any planning work and the OUTPUT before returning it; a block is audited and raised, never swallowed. | `guardrail.screen(INPUT)` at the top of `CampaignPlanService.build_plan` and `screen(OUTPUT)` before returning; a blocked verdict audits `BLOCKED` and raises `GuardrailBlockedError` ([`domain/plan_service.py`](src/campaign_planner/domain/plan_service.py), [`domain/errors.py`](src/campaign_planner/domain/errors.py)). | `pytest tests/unit/test_plan_pipeline.py::test_guardrail_blocks_injection` |
| SC-3 | **Never answer ungrounded.** An empty consented audience is a hard error, not a degraded plan; every figure the system emits carries a `Citation` a reviewer can trace. | `NoAudienceError` when selection yields nothing; every `SelectedSegment` / `BudgetLine` carries citations, collected onto the `Plan`; the eval gate scores `plan_groundedness` and `citation_accuracy`. | `pytest tests/unit/test_plan_pipeline.py::test_plan_is_grounded_and_review_gated tests/unit/test_plan_pipeline.py::test_no_audience_for_unseeded_combo_raises` |

### 7.2 Decision integrity

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| SC-5 | **Deterministic decisions the model cannot soften.** The consequential numbers (segment ranking, budget split, reach, pacing) are pure, replayable code applied by the deterministic engines, never by the LLM, so no prompt or model change can move a figure. | [`audience_service.py`](src/campaign_planner/domain/audience_service.py), [`allocation_service.py`](src/campaign_planner/domain/allocation_service.py), [`reach_service.py`](src/campaign_planner/domain/reach_service.py), [`pacing_service.py`](src/campaign_planner/domain/pacing_service.py) are pure functions; the LLM only drafts the brief / summary. | `pytest tests/unit/test_allocation_service.py tests/unit/test_audience_service.py -q` (includes `::test_allocation_is_deterministic`, `::test_select_is_deterministic`). |
| SC-6 | **Maker-checker on every consequential output.** The system never auto-actions: the plan and its budget allocation always require human review, and the audit decision is ESCALATED, so four-eyes is structural. | `Plan.requires_human_review` and `ChannelMix.requires_human_review` return `True` unconditionally; `_record` audits ESCALATED ([`domain/plan_service.py`](src/campaign_planner/domain/plan_service.py)). | `pytest tests/unit/test_plan_pipeline.py::test_audit_records_the_plan tests/unit/test_allocation_service.py::test_requires_human_review_is_true` |
| SC-7 | **Quality is a promotion gate, not a dashboard.** Groundedness, citation accuracy, budget-reconciliation accuracy and review safety are scored against thresholds and a failing score blocks the build. | [`eval/run_eval.py`](eval/run_eval.py) (offline gate, thresholds in [`eval/rubrics/`](eval/rubrics/)); the `local` evaluation adapter delegates to it and CI runs it. | `python eval/run_eval.py` exits non-zero on any miss (exits 0 on the golden set). |

### 7.3 Identity and secrets

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| SC-8 | **Resolve identity server-side; ignore client-asserted actors.** Any actor / ACL in the request body is discarded; the audit actor and entitlements come only from a verified credential, and failure to verify is a 401 (fail closed). | [`api/security.py`](src/campaign_planner/api/security.py) `get_principal` builds the `RequestContext` from headers and asks the active `IdentityPort` to resolve a verified `Principal`; the resolved subject becomes the audit actor. | `pytest tests/unit/test_identity.py tests/unit/test_api_identity.py -q` (includes `::test_default_persona_becomes_audit_actor`, `::test_unknown_dev_persona_is_401`). |
| SC-10 | **Config holds the names of inputs, never secret values.** Settings reference the environment variable that supplies each deployment value; nothing sensitive is a literal in the config, and env-supplied values (e.g. the IAP audience) are read at adapter construction, never logged or serialized. | [`config/settings.yaml`](config/settings.yaml) uses `${VAR:-default}` tokens only (project id, profile, agent-engine id, local store paths); the IAP audience is read from `MKT_CAMPAIGN_IAP_AUDIENCE` inside [`gcp/iap_identity.py`](src/campaign_planner/adapters/gcp/iap_identity.py) and the verified assertion is never logged. | `grep -nE "secret\|password\|token\|key:" config/settings.yaml` returns nothing (only `${VAR}` references remain). |

### 7.4 Auditability and detection

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| SC-11 | **WORM audit at rest.** Immutability is enforced by the store, not by convention: the managed audit trail is a locked Cloud Logging bucket (retention a variable, the lock a deliberate irreversible toggle); the offline stand-in is an append-only store (record + read-back only). | [`infra/terraform/logging_worm.tf`](infra/terraform/logging_worm.tf) locks a CMEK-encrypted, `asia-southeast1` log bucket at ~7-year retention with a sink routing the audit log to it; [`adapters/gcp/cloud_logging_audit.py`](src/campaign_planner/adapters/gcp/cloud_logging_audit.py) writes already-screened events; [`adapters/local/audit.py`](src/campaign_planner/adapters/local/audit.py) is the append-only offline sink. | `terraform -chdir=infra/terraform validate` (the locked bucket resource is present with `locked = true`). |
| SC-12 | **Record AND detect.** Audit logs nobody reads are not a control: log-based metrics and alert policies surface guardrail blocks, service-account key creation and VPC-SC denials to an operator. | [`infra/terraform/monitoring.tf`](infra/terraform/monitoring.tf): three log-based metrics plus alert policies (notification channels left as an operator input). | `terraform -chdir=infra/terraform validate` (three `google_monitoring_alert_policy` resources exist even with no channel wired). |
| SC-13 | **Traces carry telemetry, not content.** Spans and token metrics support debugging and FinOps; message-content capture stays OFF because customer data must never reach the tracing backend. | `ObservabilityTracerPort` exposes only `span(name, **attributes)` and `record_token_usage` (counts only); [`adapters/gcp/cloud_trace_tracer.py`](src/campaign_planner/adapters/gcp/cloud_trace_tracer.py) documents content capture OFF. | Port contract: `grep -n "def " src/campaign_planner/ports/observability.py` shows the tracer port has no content-bearing method. |

### 7.5 Residency and platform hardening

| # | Principle (generic) | Mechanism in this repo | Proof |
|---|---------------------|------------------------|-------|
| SC-14 | **Residency by construction.** The region is selected from a reviewed allowlist (an off-list region fails fast) in both the app and the infra; an Org Policy makes out-of-region resource creation impossible rather than merely avoided. | [`adapters/gcp/_region.py`](src/campaign_planner/adapters/gcp/_region.py) `resolve_region` validates against the per-market allowlist and raises `UnsupportedMarketError` off-list; [`infra/terraform/variables.tf`](infra/terraform/variables.tf) validates `region`; [`infra/terraform/org_policy.tf`](infra/terraform/org_policy.tf) sets `gcp.resourceLocations`. | `pytest tests/unit/test_gcp_adapters_import_safe.py::test_region_validation_rejects_out_of_residency_region tests/unit/test_gcp_adapters_import_safe.py::test_region_validation_accepts_each_apac_market` |
| SC-15 | **CMEK does not cascade: bind it everywhere, explicitly.** Each service that touches the data gets its own key binding and its own service-agent grant; assume nothing inherits encryption. | [`infra/terraform/kms.tf`](infra/terraform/kms.tf): one regional ring/key with explicit `cryptoKeyEncrypterDecrypter` bindings for Logging, Vertex AI, BigQuery, Cloud Run and Cloud Storage service agents, `prevent_destroy` on the key; the two workload SAs are bound in [`iam.tf`](infra/terraform/iam.tf). | `terraform -chdir=infra/terraform validate` (every CMEK-capable service in the stack names the key). |
| SC-16 | **Blast-radius controls default on, with an explicit dry run.** A VPC-SC perimeter around the AI / data APIs (dry-run first, then enforce), least-privilege per-workload service accounts, no exportable SA keys, uniform bucket access. | [`infra/terraform/vpc_sc.tf`](infra/terraform/vpc_sc.tf) (`vpc_sc_dry_run` defaults true), [`infra/terraform/iam.tf`](infra/terraform/iam.tf) (two scoped SAs), [`infra/terraform/org_policy.tf`](infra/terraform/org_policy.tf) (no SA keys, no external IP, uniform bucket access). | `terraform -chdir=infra/terraform validate`; dry-run violations surface via the SC-12 alerts before enforcement flips. |
| SC-17 | **Graceful degradation is a design decision, listed per step.** Best-effort steps (tracing) degrade with no impact on the answer; safety-critical steps (guardrail, grounding, audit) hard-fail. Write the split down so nobody "fixes" a hard failure into a silent skip. | `CampaignPlanService._span` swallows a tracer failure into a `nullcontext` (tracing never breaks the pipeline), while a blocked input, an empty audience and audit are hard paths ([`domain/plan_service.py`](src/campaign_planner/domain/plan_service.py)). | `pytest tests/unit/test_plan_pipeline.py::test_guardrail_blocks_injection tests/unit/test_plan_pipeline.py::test_no_audience_for_unseeded_combo_raises tests/unit/test_plan_pipeline.py::test_audit_records_the_plan` |

### 7.6 Why this shape (summary)

- **No vendor lock-in:** the domain depends on Protocols, not SDKs (PT-1); the exit path is
  concrete (PT-6) and rehearsed offline (`scripts/portability_demo.py`).
- **Testable without the cloud:** the SDK-free profiles run the entire suite and the full
  pipeline with no Google Cloud packages installed (PT-4, PT-5).
- **Residency and auditability by construction:** controls are code and infra with tests and
  fail-fast errors (SC-2 through SC-17), not conventions in a policy document.
