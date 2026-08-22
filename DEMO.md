# Mkt2 Campaign Planner - demo guide

Two ways to demo: a **local (offline)** demo that needs no Google Cloud, and a **GCP**
demo against the managed stack. Both are region-selectable and vertical-selectable.

All demo data is obviously fictional (every name suffixed FICTIONAL, every URL on
`example.test`).

## 1. Local (offline) demo - no cloud, no API key

The `local` profile is a real, deterministic offline stack: a seeded audience-data store, a
deterministic LLM drafter, a heuristic guardrail and an append-only audit log. Nothing
calls Google Cloud.

```bash
make install                 # python3.14 venv, [dev] only (no google-cloud-*)
make gate                    # the hard gate (ruff + format + mypy + pytest + eval)
```

### a) CLI - a cited plan offline

```bash
# Banking, Singapore:
MKT_CAMPAIGN_PROFILE=local mkt-campaign "savings account acquisition" -m SG -v banking -b 120000

# Online retail, Australia, back-loaded pacing:
MKT_CAMPAIGN_PROFILE=local mkt-campaign "seasonal sale campaign" -m AU -v online_retail -b 110000 --pacing back_loaded

# Banking, Japan, front-loaded:
MKT_CAMPAIGN_PROFILE=local mkt-campaign "multi-currency wallet launch" -m JP -v banking -b 200000 --pacing front_loaded
```

Each prints the ranked audience, the deterministic channel-mix budget allocation, the reach
/ frequency estimate, the pacing calendar, and the maker-checker "human review required"
banner - every figure cited.

### b) Static audit-first HTML (screenshots)

```bash
make demo                    # runs scripts/demo.py + scripts/render_plan_ui.py
open scripts/out/index.html  # a chooser across both verticals and JP/AU/SG
```

### c) Live presenter demo server (stdlib only)

```bash
make demo-server             # http://localhost:8111 - click "Next" to reveal each plan
```

### d) Presenter-paced browser walkthrough (Playwright)

A guided, narrated run of the same demo server: a real Chrome window opens, each step is
announced on the terminal (never on screen, so the audience sees a clean console) and waits
for you to press Enter before it clicks "Next" and highlights the panel to look at.

```bash
# one-time
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

# terminal 1
make demo-server

# terminal 2
.venv/bin/python scripts/demo_playwright.py
```

Unattended (self-test / recording): `HEADLESS=1 DEMO_AUTO=1 .venv/bin/python scripts/demo_playwright.py`.

### e) The API + the thin Next.js console

```bash
# Terminal 1 - the FastAPI backend on :8101 (local profile):
make run-api

# Terminal 2 - the console:
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8101 npm run dev
# open http://localhost:3000
```

Identity is server-verified: the local profile runs with NO IdP and seeds four demo
personas. The console shows a "Demo identity" picker (local profile only); over curl,
select a persona with the `X-Dev-Persona` header (default: the analyst persona; unknown
ids get a 401). The request body never carries an `actor`:

```bash
curl -s http://localhost:8101/v1/personas
curl -s http://localhost:8101/v1/plan \
  -H 'Content-Type: application/json' -H 'X-Dev-Persona: approver' \
  -d '{"objective": "savings account acquisition", "market": "SG",
       "vertical": "banking", "total_budget": 120000,
       "start_date": "2026-07-01", "end_date": "2026-07-28"}'
```

See [docs/embedding-and-identity.md](docs/embedding-and-identity.md) for embedding the
console in a client portal and the secure (IAP) deployment.

## 2. GCP demo - the managed stack

The `gcp` profile binds BigQuery (audience data), Gemini (drafting), Model Armor
(guardrail), Cloud Logging WORM (audit), Cloud Trace (tracing), the Gen AI evaluation
service (Hrz4 gate), an A2A registry and an MCP tool catalog. The residency region is resolved
from the selected market and validated (JP -> `asia-northeast1`, AU ->
`australia-southeast1`, SG -> `asia-southeast1`).

```bash
make install-gcp                              # adds the [gcp] extra
export GOOGLE_CLOUD_PROJECT=your-project
gcloud auth application-default login

# Build a plan on the managed stack (region selected from the market):
MKT_CAMPAIGN_PROFILE=gcp MKT_MARKET=SG MKT_VERTICAL=banking \
  mkt-campaign "savings account acquisition" -m SG -v banking -b 120000

# The production Hrz4 evaluation gate (Gen AI evaluation service):
MKT_CAMPAIGN_PROFILE=gcp python eval/run_eval.py --use-gcp
```

Select the region/vertical by changing `-m {JP|AU|SG}` and `-v {banking|online_retail}`; a
region outside the per-market allow-list is rejected before any network call.

## 3. Exit portability (on-prem) - fail-fast proof

```bash
MKT_CAMPAIGN_PROFILE=onprem mkt-campaign "savings" -m SG -v banking
# exits 2 and names the migration target; the domain logic is unchanged.
```
