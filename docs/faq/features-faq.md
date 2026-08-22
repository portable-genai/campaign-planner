# Features FAQ

For product, marketing, and delivery teams: what this agent does, what is deterministic vs
LLM, and, importantly, where its responsibilities **stop** and a sibling catalog system
takes over. Cross-references: [`README.md`](../../README.md), [`DEMO.md`](../../DEMO.md),
[`ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does Mkt2 actually produce?

A cited **campaign plan**. From a campaign objective, a total budget, and a flight window it
produces: an audience selection (which consent-gated segments to target and why), a
channel-mix **budget allocation** (how the spend splits across channels), a **reach and
frequency** estimate, and a **pacing / flight-schedule** calendar. Every figure carries a
`Citation` back to the audience-warehouse row or channel benchmark it came from, and the
whole plan is written to a WORM audit trail. It is generic across two verticals (banking,
online retail) and the JP / AU / SG markets.

### What is deterministic vs done by the LLM?

The consequential math is **deterministic and replayable** (pure stdlib, unit-tested): the
audience selection (`domain/audience_service.py`), the channel-mix budget optimiser
(`domain/allocation_service.py`), the reach / frequency estimator (`domain/reach_service.py`),
and the pacing calendar (`domain/pacing_service.py`), stitched by the
`domain/plan_service.py` orchestrator. The LLM only **drafts** the creative brief and
**narrates** the plan summary. It never sets a number: a marketer or auditor can recompute
every allocation, reach figure and pacing row without the model. This is the "deterministic
domain service" pattern, and `grep -rE "google|fastapi|httpx|pydantic" src/campaign_planner/domain/`
returns nothing.

### Is anything auto-approved? Does it commit spend?

No. Every plan sets `requires_human_review=True` (maker-checker), and `ChannelMix`
unconditionally requires review; **no spend is committed until a qualified approver signs
off**. The escalation is not a per-repo boolean: it is routed to the **Hrz7** Human-Review
and Maker-Checker Console through the shared `review-kit` client (dependency rule R8),
with the descriptor, summary and citation snippets redacted before the wire and the verified
actor threaded as maker. The agent proposes; a human disposes.

### What does it NOT process? (no customer PII)

It does **not** ingest, store, or reason over raw customer records or per-customer
identifiers. It works over **aggregate, consent-gated audience segment counts** and
**per-channel cost / performance benchmarks**. That is why several PII controls are declared
omitted-by-design (see [security-faq.md](security-faq.md) and [compliance-faq.md](compliance-faq.md)):
there is no identifier stream to redact, no per-tenant customer store, and no ACL-scoped
retrieval layer. If a fork adds a per-customer surface, it must add those controls back.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable GRC systems. It **owns** the campaign-planning
domain logic and its outputs. It **integrates** (via the `platform` profile's thin HTTP
adapters, or the `gcp` managed services) several cross-cutting concerns that are owned by
sibling platform systems. Do not rebuild these in a fork:

| Concern | Owned by (catalog id / repo) | Mkt2's role |
|---|---|---|
| Runtime guardrail: prompt-injection / jailbreak defense, output screening | **Hrz1** `agent-guardrail-gateway` | consumes it at the model boundary (input + output screen) |
| Governed RAG / ACL-aware knowledge base with citations | **Hrz2** `enterprise-knowledge-base` | not used by the shipped vertical (no brand-corpus retrieval); a fork that adds one integrates it |
| Agent registry, versioning, identity, entitlements | **Hrz3** `agent-registry` | publishes its A2A agent card for discovery |
| AI-quality / eval / model-risk promotion gate | **Hrz4** `model-quality-gate` | its eval metrics gate promotion; the offline gate mirrors it |
| Observability + immutable WORM audit + FinOps | **Hrz5** `agent-observability` | writes audit events to it; traces spans (counts only, no content) through it |
| Human review / maker-checker console | **Hrz7** `human-review-console` | routes every plan's review escalation to it (R8) |
| Marketing compliance / financial-promotions claim check | **Mkt6** `marketing-compliance-gate` | the creative brief and any customer-facing claim are that system's job, not this one's |

So the guardrail, audit sink, eval platform, review console and marketing-claim gate are
*dependencies*, not features of this repo.

### How does this relate to the other marketing systems in the catalog?

Mkt2 is the plan-build step: audience, budget split, reach / frequency, pacing. Adjacent Mkt
systems handle different points and should not be duplicated here: **Mkt1** market
intelligence & competitor analysis (inputs that inform strategy), **Mkt3** brand-safe
creative & content studio (produces the creative assets a plan schedules), **Mkt4**
stats-based performance marketing & attribution (measures what a live campaign delivered),
**Mkt5** next-best-action recommendations & cross-sell, and **Mkt6** marketing compliance &
brand governance (the financial-promotions claim check). Check
[the organization's repository index](https://github.com/portable-genai) before building a
capability that may already have a home.

### Can I use this for a non-banking marketing product?

Yes, that is the point of the generic design. The reusable core (the four deterministic
engines, citations, audit, eval, maker-checker) transfers across verticals; the shipped
build already runs `banking` and `online_retail` as a `vertical:` setting, and JP / AU / SG
as a `market:` setting (config plus seed, never a hard-coded branch). To add a vertical or
market you change configuration and the seeded fixtures, not the engines. See
[`docs/ADOPTING.md`](../ADOPTING.md) and [adoption-faq.md](adoption-faq.md).

### How do I see it working?

`make demo` runs the real `CampaignPlanService` flow offline and renders the audit-first HTML
into `scripts/out/`; `make demo-server` is a presenter-controlled offline server;
`make smoke-local` builds one cited plan end to end from the CLI. Everything runs on
synthetic, fictional data (names suffixed FICTIONAL, URLs on `example.test`) with no cloud and
no API key.
