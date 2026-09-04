# COMPLIANCE: `campaign-planner` Campaign Planning and Budget-Allocation Assistant

This maps every General Principle (P-01..P-13) and dependency rule (R1..R8) to a concrete
control in **this** repo. Where a principle does not apply to `campaign-planner`, it is marked **n/a** with
the reason. `campaign-planner` plans over aggregate audience benchmarks and no per-customer PII, so its
load-bearing controls are deterministic maths, provenance, maker-checker and audit.

> The audience, benchmark and objective data in `tests/`, `eval/` and the local seed is
> **fictional**. This build is a reference piece and is **not** intended for live use without
> your own legal, security and model-risk sign-off.

---

## General Principles

| # | Principle | How `campaign-planner` implements it | Evidence |
|---|-----------|----------------------|----------|
| **P-01** | Managed-first, minimal surface | Only the managed services the pinned stack uses are enabled; the agent is hosted on Agent Runtime | `infra/terraform/apis.tf`, `agent/root_agent.py` |
| **P-02** | No vendor lock-in (ports and adapters) | Domain depends only on `Protocol` ports; a profile switch rebinds adapters with no domain change. The `local` family proves the same domain runs entirely off-cloud (deterministic optimiser and LLM, no Google Cloud SDK) | `ports/`, `config.py`, `adapters/local/*`, `adapters/onprem/*` |
| **P-03** | Data residency (in-country) | Region selected at deploy from a residency allowlist, with per-market overrides (JP / AU / SG), validated to fail fast; regional endpoints; `gcp.resourceLocations` Org Policy; VPC-SC perimeter | `config/settings.yaml` (`markets`), `infra/terraform/variables.tf`, `org_policy.tf`, `vpc_sc.tf` |
| **P-04** | Minimise data to the model | `campaign-planner` sends aggregate audience benchmarks and no per-customer PII; the model-boundary callback still guardrail-screens every prompt and response, and spans capture no content | `agent/callbacks.py`, `domain/plan_service.py` |
| **P-05** | Grounding over fine-tuning | The creative brief and calendar are narrated over the deterministically-computed plan; no training on data | `domain/plan_service.py`, `ports/generation.py` |
| **P-06** | Human-in-the-loop / maker-checker | Every `Plan` is `requires_human_review=True`; a human signs off before any spend is committed. The escalation is not left as a per-repo boolean: it is routed to the `human-review-console` maker-checker console via `review-kit` (rule R8) | `domain/plan_service.py`, `domain/models.py`, `ports/review_router.py` |
| **P-07** | Auditable and explainable by design | Every plan writes a WORM `AuditEvent` with the decision and citations; the ADK after-agent callback audits again at the model boundary | `domain/plan_service.py`, `adapters/gcp/cloud_logging_audit.py`, `agent/callbacks.py` |
| **P-08** | Eval-gated promotion | Offline eval gate scores plan quality (allocation sanity, brief groundedness, review safety); `model-quality-gate` at promotion | `eval/run_eval.py`, `ports/observability.py` (`EvaluationGatePort.gate`) |
| **P-09** | Defense in depth / zero trust | CMEK, least-privilege IAM, private endpoints, a distinct agent identity; the guardrail screens twice (domain pipeline and model-boundary callback) | `infra/terraform/kms.tf`, `iam.tf`, `agent/callbacks.py` |
| **P-10** | Provenance on every claim | Every consequential figure (budget split, channel mix, reach) carries a source-and-page `Citation`; the model only narrates computed numbers | `domain/models.py` (`Citation`), `domain/plan_service.py` |
| **P-11** | Cost and latency control | A small triage-tier model handles routing / pre-checks; the reasoning model only narrates the already-computed allocation | `config.py` (`ModelSettings.triage`) |
| **P-12** | Reversibility / documented exit | The `local` adapters run the whole pipeline off-cloud today (the working proof), and the `onprem` placeholders satisfy the same Protocols as the fail-fast sovereign target; the contract test proves parity for both | `adapters/local/*`, `adapters/onprem/*`, `tests/contract/test_port_parity.py`, `docs/onprem-migration.md` |
| **P-13** | Fair, consented marketing (advertising compliance) | `campaign-planner` produces an internal plan (audience, allocation, brief), not published advertising; any output that becomes customer-facing must pass `marketing-compliance-gate` (rule R7). The agent instruction forbids drafting final customer-facing ad copy here | `agent/root_agent.py` instruction, R7 below |

---

## Dependency rules

`campaign-planner`'s mandatory dependencies are **`agent-guardrail-gateway`, `enterprise-knowledge-base`, `agent-registry`, `model-quality-gate` (gate), `agent-observability` and `market-intelligence`** (see
`systems/`). Each platform rule is satisfied by consuming the sibling service through a
`platform` adapter (with an on-prem stub), never by re-implementing the concern.

| Rule | Requirement | How `campaign-planner` satisfies it | Evidence |
|------|-------------|---------------------|----------|
| **R1** | Customer PII handling: `agent-guardrail-gateway` + DLP redaction | `campaign-planner` consumes the `agent-guardrail-gateway` for prompt-injection and unsafe-output screening (INPUT and OUTPUT, pipeline and model boundary). **PII redaction is n/a**: `campaign-planner` plans over aggregate audience benchmarks with no per-customer record (C2/C3/C4 n/a in the practices audit) | `ports/safety.py`, `domain/plan_service.py`, `agent/callbacks.py` |
| **R2** | Audit to `agent-observability` | Every plan writes an immutable WORM `AuditEvent`; the `platform` adapter posts to `agent-observability` `/v1/audit` | `adapters/gcp/cloud_logging_audit.py`, `adapters/platform/remote_audit.py` |
| **R3** | Governed RAG via `enterprise-knowledge-base` | **n/a in-repo**: `campaign-planner` has no RAG retrieval step; audience benchmarks come from BigQuery. If a brand-corpus grounding step is added it routes through `enterprise-knowledge-base` | audience data via `ports/audience.py` |
| **R4** | Register in `agent-registry` | The A2A AgentCard is published at `/.well-known/agent-card.json` and resolvable via `agent-registry`; the governed MCP tool catalog scopes access least-privilege | `agent/agent_card.py`, `api/app.py`, `adapters/platform/remote_registry.py`, `adapters/gcp/mcp_tool_catalog.py` |
| **R5** | `model-quality-gate` promotion gate | `EvaluationGatePort.gate` checks the `model-quality-gate` thresholds before promotion; the offline gate guards merges | `ports/observability.py`, `adapters/platform/remote_evaluation.py`, `eval/run_eval.py` |
| **R6** | Validated by `architecture-validator` at intake | As a new project, `campaign-planner` is validated by the `architecture-validator` intake validator externally. n/a in-repo | intake handled by `architecture-validator` externally |
| **R7** | Marketing compliance via `marketing-compliance-gate` | `campaign-planner` produces an internal plan, not published advertising. Any output that becomes customer-facing must pass `marketing-compliance-gate` (per-market advertising / consumer-protection claim check, brand guidelines, marketing consent) and screen via `agent-guardrail-gateway`. The agent forbids drafting final customer-facing copy here | `agent/root_agent.py` instruction; `marketing-compliance-gate` governance |
| **R8** | Route escalations to `human-review-console` | A `Plan` sets `requires_human_review`, so it MUST be routed to the `human-review-console` Human-Review & Maker-Checker Console via the shared `review-kit`, not terminate in a per-repo boolean. The producer redacts the descriptor, summary and citation snippets before the wire (defense in depth), threads the verified actor as maker and the tenant from the call, and defaults severity to `medium` (a `Plan` carries no severity signal). `local` enqueues to an in-memory outbox; `platform`/`gcp` submit over S2S; `onprem` is the fail-fast sovereign placeholder | `ports/review_router.py`, `adapters/_review_payload.py`, `adapters/local/review_router.py`, `adapters/platform/review_router.py`, `adapters/onprem/review_router.py` |

---

## Why `campaign-planner` has no per-customer PII surface (R1, C2..C4)

- **Aggregate inputs only.** A plan is built from aggregate audience segments and per-channel
  benchmarks (reach, CPM, CTR bands), not from any individual customer record. There is no
  customer identifier and no tenant-partitioned customer data (contrast `next-best-action`, the
  per-customer next-best-action repo). The practices audit records C2/C3/C4 as **n/a by
  design**.
- **The guardrail still runs, twice.** The `agent-guardrail-gateway` screens INPUT and OUTPUT inside the
  domain pipeline and again at the ADK model boundary, so prompt injection and unsafe output
  are caught even though there is no PII to redact.
- **Determinism where it counts (P-10).** The budget split, channel mix, reach / frequency and
  pacing legs are all computed by pure code; the model only narrates them, so a plan is
  replayable and every figure is traceable.
- **Maker-checker on a consequential output (P-06).** A plan commits spend, so it always
  requires human review before anyone acts on it.

---

## Appendix: regulator crosswalk (adopter-owned)

The `P-*` / `R*` catalog above is this build's internal control language; a regulated adopter
maps it onto its own supervisor's requirements. The rows below are a **reference mapping** for
the home markets (JP / AU / SG); a fork adds a column per additional regulator. This appendix
is *adopter-owned*: a template, not legal advice.

| `campaign-planner` control | Reference regime | What a supervisor looks for |
|---|---|---|
| P-06 maker-checker; P-10 determinism | MAS FEAT (Accountability) | A qualified human disposes of every consequential plan; the maths is replayable |
| P-07 WORM audit; P-10 provenance | MAS TRM (auditability); record-keeping | Immutable, reproducible records; every figure traceable |
| P-13 / R7 marketing compliance | SG ASAS; AU ACCC / ASIC; JP fair-trade advertising | Customer-facing outputs pass an advertising / consumer-protection claim check before publication |
| P-03 residency; P-12 exit | MAS Outsourcing / Cloud guidelines | In-country data residency and a demonstrable exit / portability plan |
| P-08 quality / model-risk gate | MAS FEAT; model-risk expectations | A promotion gate with quality / safety metrics and model documentation |

**To add another regulator**: copy this table, replace the reference column with that
supervisor's instrument and section numbers, and re-review the third column with local
counsel. The `campaign-planner`-control column is stable across regulators; only the mapping changes. The
sibling **the cloud control-mapping toolkit control-mapping toolkit** and **`compliance-advisory`** generate and
maintain these crosswalks at scale.
