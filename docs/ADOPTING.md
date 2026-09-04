# Adopting this repo as your base

This repository is a **common base** that banks, retailers, and other organisations fork to
build their own campaign-planning and budget-allocation agents. It ships a reusable hexagonal
core (a pure-stdlib domain, typed ports, swappable adapter profiles, a green offline gate)
plus a fully worked campaign-planning vertical, generic across banking and online retail and
the JP / AU / SG markets, that you can keep, retune, or replace.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical
rebrand** (one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the ports, the four profiles, and
> §7 the security catalogue), [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding a port /
> sub-service), the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is layered so the boundary is explicit:

| Layer | Where | For a new vertical / brand |
|---|---|---|
| **Kernel** (vertical-neutral) | The stable `domain/kernel.py` import surface, `domain/serialization.py`, and the generic ports | keep untouched |
| **Policy** (your numbers) | The validated `config/settings.yaml:policy` audience, allocation, reach and pacing values plus eval rubrics | change by config, not engine code |
| **Vertical** (campaign artifacts) | The artifact models in `domain/models.py` (`Plan`, `ChannelMix`, `AudienceSegment`, `ReachFrequency`, `FlightSchedule`), the narrating services, the local seed fixtures, the eval golden set, the UI plan views | rewrite / reseed for your data |

`domain/kernel.py` is the stable neutral import surface and exports no plan, channel mix or
audience aggregate. Most of the kernel and the four deterministic engines transfer directly
to another marketing-planning fork; you reseed audience/benchmark data and retune policy.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): the neutral types and the four engines in `domain/`,
  `ports/`, `tests/contract/`, the eval harness mechanics (`eval/run_eval.py`), CI workflows,
  and the hexagon wiring (`config.py` `Container`).
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the local
  audience / benchmark seed and every fixture, `adapters/onprem/*`, UI theming / branding, the
  golden eval dataset, and the regulator rows in `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned
changes onto each release rather than merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name, the CLI entry point, the `MKT_CAMPAIGN_`
env prefix, the resource-id stem, and the distribution name across the tree in one pass.
Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_campaign_agent --cli acme-campaign \
    --env-prefix ACME --resource acme-campaign-planner --dry-run

# Apply:
python scripts/rename_fork.py --package acme_campaign_agent --cli acme-campaign \
    --env-prefix ACME --resource acme-campaign-planner --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make gate
```

The distribution name defaults to the `--resource` value (here `campaign-planner` maps to
your `--resource`); pass `--dist` to override. Add `--include-docs` to sweep Markdown prose
too. The script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** Set the market and its region: `MKT_MARKET` and the per-market
   `markets:` block in `config/settings.yaml`, plus the Terraform `region` / tfvars, to your
   in-country region. The build defaults to `SG` / `asia-southeast1`; JP maps to
   `asia-northeast1` and AU to `australia-southeast1`. See [`docs/runbook.md`](runbook.md).
2. **Identity / IdP.** The repo owns no login flow: `gcp` / `platform` verify the Cloud
   IAP-injected assertion (`MKT_CAMPAIGN_IAP_AUDIENCE`), `local` uses seeded dev personas
   (`X-Dev-Persona`, offline only), and `onprem` is a client-IdP placeholder. Wire your IdP by
   implementing the `onprem` identity adapter or configuring IAP on the service. See
   [`docs/embedding-and-identity.md`](embedding-and-identity.md).
3. **Vertical + market seed data.** The bundled audience segments and channel benchmarks are
   synthetic. Set `MKT_VERTICAL` (`banking` | `online_retail`) and `MKT_MARKET`
   (`JP` | `AU` | `SG`), and replace the seed (`MKT_LOCAL_SEED`, or the bundled fictional seed)
   with your own aggregate, consent-gated segment data. Adding a vertical or market is a config
   plus seed change, not an engine edit.
4. **Optimiser numbers.** Own the `config/settings.yaml:policy` values your marketing and
   finance functions care about: audience weighting, allocation saturation/epsilon, reach
   factor and pacing ramp. The production composition root threads these validated values
   into the pure engines; eval thresholds remain in `eval/rubrics/*.yaml`.
5. **Reference data is fictional.** Every fixture and the bundled seed use obviously-fake
   names (suffixed FICTIONAL, URLs on `example.test`). **Do not run against real data without
   your own legal, security and model-risk sign-off.**
6. **Eval golden set.** Rebuild `eval/datasets/golden_plans.jsonl` and the rubrics for your
   vertical / market: a fork inherits a green gate that measures the WRONG thing until you do.
   The gate structure is generic; the golden cases are yours.
7. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root, `EXPOSE 8101`,
   `/healthz`), `infra/terraform/` (Org Policy, CMEK, VPC-SC, WORM logging), and the
   loopback-by-default API binding before you expose anything.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches*
are owned by sibling platform services; integrate rather than rebuild them (see
[`docs/faq/features-faq.md`](faq/features-faq.md) for the full map): the guardrail gateway
(`agent-guardrail-gateway`), the agent registry (`agent-registry`), the AI-quality / eval gate (`model-quality-gate`), observability + WORM
audit (`agent-observability`), the human-review console (`human-review-console`), and the marketing compliance / financial-
promotions gate (`marketing-compliance-gate`). The `platform` profile's adapters are already thin HTTP clients to
those services.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set market + region + Terraform tfvars to your in-country region.
- [ ] Wired your IdP (onprem adapter or IAP) and set `MKT_CAMPAIGN_IAP_AUDIENCE` if using IAP.
- [ ] Set `MKT_VERTICAL` / `MKT_MARKET` and replaced the audience / benchmark seed data.
- [ ] Owned the optimiser numbers (allocation fields, reach threshold, eval thresholds).
- [ ] Replaced every synthetic fixture.
- [ ] Rebuilt the eval golden set + rubrics for your vertical / market.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address).
- [ ] Decided which sibling platform services you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
