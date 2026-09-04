# campaign-planner (`campaign-planner`) - Campaign Planning and Budget Allocation

**Industries:** Retail & e-commerce, Banking, Consumer goods, Telecom, Travel & hospitality, Media

A ports-and-adapters reference build that turns a marketing audience warehouse into a
**cited, auditable campaign plan**: which audience segments to target, how to split the
budget across channels, the reach and frequency that buys, and the pacing calendar that
spends it. It is generic across **banking and online retail** and the **JP / AU / SG**
markets, built on the Gemini Enterprise Agent Platform.

The deterministic engines are the heart of the system; the LLM only drafts the creative
brief and narrates the plan summary. Every figure carries provenance and every plan is
maker-checker gated (``requires_human_review=True``) before any budget is committed.

## What it does

Given an objective, a market, a vertical, a budget and a flight window, `campaign-planner`:

1. **selects the audience** - ranks candidate segments by a deterministic
   propensity x value x consent score and drops anyone who did not consent;
2. **allocates the budget** - an efficiency-greedy optimiser splits spend across channels
   by deterministic cost-per-conversion, honouring per-channel reach caps and spend floors;
3. **estimates reach / frequency** - de-duplicated unique reach, average frequency and
   effective ("3+") reach over the consented addressable audience;
4. **builds the pacing calendar** - a flight schedule (even / front-loaded / back-loaded)
   whose legs reconcile exactly to the budget;
5. **drafts the creative brief and summary** with the LLM, grounded on the deterministic
   plan, then assembles a cited :class:`Plan` that requires human review.

## Architecture (ports and adapters)

```
src/campaign_planner/
  domain/            PURE stdlib: models (Plan, AudienceSegment, ChannelMix, BudgetLine,
                     FlightSchedule, Citation, Vertical/Market enums) + the four
                     deterministic engines + the orchestrator. No SDKs, no I/O.
  ports/             typing.Protocol, @runtime_checkable - the hexagon boundary
                     (AudienceDataPort, LlmPort, GuardrailPort, AuditSinkPort,
                     IdentityPort, ...)
  adapters/
    gcp/             managed: BigQuery audience, Gemini LLM, Model Armor, Cloud Logging
                     WORM, Cloud Trace, Gen AI eval, A2A registry, MCP catalog. LAZY imports.
    local/           WORKING offline stack: SDK-free, deterministic, seedable. CI default.
    onprem/          fail-fast placeholders satisfying the same Protocols (portability proof)
    platform/        thin HTTP clients to the shared platform siblings
  config.py          Settings + Container (DI): dotted-path port -> adapter bindings
  api/  cli/         driving adapters: FastAPI (port 8101) + the `mkt-campaign` CLI
config/settings.yaml profile -> {port: adapter}, region, model ids, knobs
eval/run_eval.py     `model-quality-gate` promotion gate over a synthetic golden set (thresholds)
ui/                  thin Next.js console
```

Three deployment profiles, one domain: `gcp` (managed Google Cloud), `local` (a real
offline stack - the dev/test/CI default), `onprem` (fail-fast `NotImplementedError` stubs
that prove exit-portability). Switch with `MKT_CAMPAIGN_PROFILE`.

## Identity and embedding

Identity is **server-verified**: the API never accepts a client-supplied `actor`. The
active profile's `IdentityPort` adapter resolves a verified `Principal` per request
(local = seeded dev personas via `X-Dev-Persona` and the UI persona picker; gcp/platform =
verification of the Cloud IAP-injected assertion; onprem = client-IdP placeholder), and
that principal is the audit actor on every plan. The Next.js console runs standalone or
embeds same-origin in a client portal (`NEXT_PUBLIC_BASE_PATH`, `NEXT_PUBLIC_EMBED=1`),
guarded by an env-driven CORS allowlist and CSP `frame-ancestors`. See
[docs/embedding-and-identity.md](docs/embedding-and-identity.md).

## Generic, multi-vertical, APAC

- **Verticals:** banking and online retail are both first-class, configurable verticals with
  their own seed data and benchmarks. No bank-only logic in the domain.
- **Markets:** JP (`asia-northeast1`), AU (`australia-southeast1`), SG (`asia-southeast1`),
  with locale (ja + en) and per-market residency regions, all config + seed.
- All synthetic data is obviously fictional (every name suffixed FICTIONAL, every URL on
  `example.test`).

## Quickstart

```bash
make install                 # python3.14 venv, [dev] only (no google-cloud-*)
make gate                    # ruff + ruff format + mypy + pytest + eval (the hard gate)
make smoke-local             # build a cited plan offline (SG banking)
make demo                    # offline demo + static audit-first HTML in scripts/out/
make run-api                 # FastAPI on :8101 (local profile)
cd ui && npm install && npm run build   # thin Next.js console
```

See [DEMO.md](DEMO.md) for the local (offline) and GCP demos.

## Quality gate

The hard gate, green before any change lands, in a fresh `[dev]`-only venv (no
google-cloud-*): `ruff check src tests` + `ruff format --check src tests` + `mypy src` +
`pytest -m 'not integration' -q` + `python eval/run_eval.py`. CI also builds the Next.js
console.
