# Security FAQ

For an AppSec reviewer sizing up this repo. It explains what the attack surface is, what is
deliberately out of scope (and why that is honest, not a gap), and where the evidence lives.

## What does this system actually process?

Aggregate, consent-gated audience segments and per-channel performance benchmarks, plus a
campaign objective, budget and flight window. It produces an internal campaign plan
(which segments, how to split the budget, reach / frequency, a pacing calendar). It does
**not** ingest, store, or reason over raw customer records or per-customer identifiers.

## Why are several PII controls marked N-A instead of implemented?

Because the domain has no per-customer identifier stream. There is no redaction step (C3),
no jurisdiction PII pack (C4), and no per-tenant customer store or ACL-scoped retrieval
layer (C2), because campaign planning runs over aggregate benchmarks and consented segment
counts. These are declared as omitted-by-design in `ARCHITECTURE.md` §7 (SC-1, SC-4, SC-9),
not silently skipped. If a fork adds a per-customer surface (for example a brand-corpus
retrieval step), it must add those controls back; they are N-A only for the shipped vertical.

## How is identity handled? Can a caller spoof the actor?

No. Identity is resolved server-side on every route. `api/schemas.py::PlanRequestModel`
carries no `actor` field, and `api/security.py::get_principal` builds a `RequestContext`
from headers and resolves a verified `Principal` through the active `IdentityPort`; a
verification failure is a 401. The verified principal (never a client-supplied value) is the
audit actor on the plan. Under `local` the personas are seeded dev identities via
`X-Dev-Persona` (offline demo / test only); `gcp` / `platform` verify the Cloud IAP-injected
assertion; `onprem` is a client-IdP placeholder.

## What about outbound service-to-service calls?

The one real outbound call today (the `model-quality-gate` promotion-gate client) is built on the shared
`agent-eval-kit` `PromotionGateClient`, hardened through `adapters/platform/_s2s.py`, which
delegates to `hex_service_kit.s2s`: it attaches an S2S bearer (`S2S_TOKEN`) and enforces
an https-only base-URL guard. The other platform delegates are marshalling-phase stubs that
raise `NotImplementedError` and inherit the same hardening when wired.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` uses only `${VAR:-default}` interpolation
tokens (project id, profile, agent-engine id, local paths); the IAP audience is read from
`MKT_CAMPAIGN_IAP_AUDIENCE` at adapter construction and is never logged. Verified by C10 in
the practices audit.

## What is the supply-chain posture?

Committed lockfiles (`requirements-dev.lock`, `requirements-gcp.lock`; py3.12), `ruff`
pinned exactly, a multi-stage digest-pinned non-root Dockerfile that installs from the lock,
SHA-pinned GitHub Actions, `dependabot.yml`, and `pip-audit` plus `npm audit` as hard CI
gates. The three commons packages (`hex-service-kit`, `agent-eval-kit`, `review-kit`)
are public, pinned by git tag, and install with zero credentials. See D1 / D2 in the audit.

## Is the audit trail tamper-evident?

Yes, within honest limits. `LocalAppendOnlyAuditAdapter` wraps
`hex_service_kit.audit.HashChainedAuditLog`: a SHA-256 hash chain, `UPDATE` / `DELETE`
triggers, JSONL export / restore, and `verify_chain()`. It is append-only and detects
in-place edits and truncation; it is not a substitute for the managed WORM sink (`agent-observability` /
locked Cloud Logging bucket) in production. Proven by `tests/unit/test_audit_chain.py`.

## What is explicitly out of scope for this repo?

The guardrail / prompt-injection screening engine (`agent-guardrail-gateway`), the governed knowledge base
(`enterprise-knowledge-base`), the agent registry (`agent-registry`), the AI-quality / eval gate (`model-quality-gate`), the WORM audit store
(`agent-observability`), the human-review console (`human-review-console`), and the marketing compliance / claim-check gate
(`marketing-compliance-gate`). This repo integrates those through thin `platform` adapters rather than
re-implementing them. See [features-faq.md](features-faq.md) for the full boundary map.
