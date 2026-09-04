# Compliance FAQ

For compliance, marketing-governance, and model-risk teams assessing the repo's regulatory
posture. Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md) (the full principle to
control map and the regulator crosswalk appendix), [`SPEC.md`](../../SPEC.md),
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) §7.

### Is this making spend decisions autonomously?

No. It is a **decision-support** agent: every plan sets `requires_human_review=True`
(maker-checker), and the channel mix always requires review. The deterministic engines produce
a documented, replayable plan; a qualified human disposes. The escalation is routed to the
`human-review-console` via the shared `review-kit` client
(dependency rule R8), not resolved as a local boolean. **No budget is committed until an
approver signs off.**

### How is customer PII handled?

There is no customer PII in the request path, by design. Campaign planning runs over
**aggregate, consent-gated audience segment counts** and **per-channel benchmarks**, not raw
customer records or per-customer identifiers. So this repo has no redaction step (C3), no
jurisdiction PII pack (C4), and no per-tenant customer store or ACL-scoped retrieval layer
(C2). These are declared **omitted-by-design** in `ARCHITECTURE.md` §7 (SC-1, SC-4, SC-9),
not silently skipped. The runtime guardrail / DLP itself is the sibling `agent-guardrail-gateway`,
which this repo consumes at the model boundary. If a fork adds a per-customer surface, it must
add those controls back.

### How is the work auditable / reproducible?

Every plan writes an immutable, already-screened WORM `AuditEvent` with the decision and the
citation set. Every figure in the plan (audience selection, budget line, reach / frequency,
pacing) carries a `Citation` back to the warehouse row or benchmark it came from. The
consequential math is deterministic, so an auditor can recompute any allocation or reach
figure from the same inputs. The enterprise WORM audit system is `agent-observability`; the in-repo
hash-chained store (via `hex_service_kit.audit.HashChainedAuditLog`) is the offline / local
stand-in (see [security-faq.md](security-faq.md) for its exact tamper-evidence limits).

### What is the model-risk story?

An offline eval gate (`eval/run_eval.py`) scores groundedness and budget accuracy against a
golden set of plans, failing the build below threshold. The `--mode smoke|gate` split runs on
the shared `agent-eval-kit` scaffold: smoke guards every merge offline, and gate mode
(promotion) refuses to run outside `MKT_CAMPAIGN_PROFILE=platform|gcp`. The enterprise
promotion gate and model documentation are the sibling `model-quality-gate` system; this repo's gate
mirrors its thresholds and registers the bundle name `mkt2-campaign` (pinned by a respx
contract test). A fork must rebuild the golden set for its own vertical / market, or the gate
measures the wrong thing.

### Who owns the marketing-claim / financial-promotions check?

Not this repo. The LLM here only drafts a creative brief and narrates the plan summary; any
customer-facing claim, financial-promotion wording, or brand-safety review is the job of the
sibling `marketing-compliance-gate` Marketing Compliance & Brand Governance system (`marketing-compliance-gate`).
`campaign-planner` produces the internal plan; `marketing-compliance-gate` is where a promotion's claims are checked before they go
live. Do not rebuild that gate here.

### Which regulators does this map to?

`COMPLIANCE.md` maps the internal P-01..P-13 controls and dependency rules R1..R8 to concrete
code with an Evidence column naming real files, plus an **adopter-owned regulator crosswalk
appendix**. To add a specific marketing / advertising-conduct regulator for JP, AU or SG,
copy the appendix table, swap the regulator-reference column, and re-review with local
counsel; the `campaign-planner`-control column is stable across regulators. At scale, the sibling control
mapping and compliance-advisory toolkits generate and maintain these crosswalks rather than
hand-maintaining the table.

### Is data residency enforced across markets?

Yes, at deploy time. The region is selected from a reviewed allowlist with per-market
overrides (JP `asia-northeast1`, AU `australia-southeast1`, SG `asia-southeast1`, the
default), validated to fail fast off-list, with a `gcp.resourceLocations` Org Policy
allowlist, CMEK, and a dry-run-first VPC-SC perimeter (`infra/terraform/`). A second market or
tenant is a `tfvars` change, not a fork. The residency-violation CI gate and the
exit / concentration-risk plan are sibling Rsk systems; this repo enforces residency in its
own infra and app (`adapters/gcp/_region.py`).

### Can we run it against real data today?

Not without your own legal, security, and model-risk sign-off. Every fixture and the bundled
audience seed are obviously fictional (names suffixed FICTIONAL, URLs on `example.test`), and
the docs state throughout that this is a reference build. The adoption checklist
(`docs/ADOPTING.md` §6) lists the steps (replace the seed data, own the optimiser numbers,
wire your IdP, rebuild the eval golden set, set your residency region) that must precede any
live use.

### Which parts of the marketing lifecycle does it cover, and which not?

It covers the plan-build step: audience selection, channel-mix budget allocation, reach /
frequency, and pacing. Market intelligence (`market-intelligence`), creative production (`creative-studio`),
performance measurement / attribution (`performance-marketing-optimisation`), next-best-action (`next-best-action`), and the
financial-promotions compliance gate (`marketing-compliance-gate`) are adjacent catalog systems, not this repo's
job. See [features-faq.md](features-faq.md) for the boundary.
