# Runbook: Mkt2 Campaign Planning and Budget-Allocation Assistant

Operational notes for deploying and running Mkt2 on the Gemini Enterprise Agent Platform in a
residency region (defaults `asia-southeast1`; JP and AU are per-market overrides). This is a
reference build; adapt it to your own change-management and model-risk sign-off before any live
use.

## 0. Profiles

`MKT_CAMPAIGN_PROFILE` selects the adapter stack. There is no default: leaving it unset is
"nobody chose", which is not the same as choosing `local`. An unset run still binds the
SDK-free adapters, because nothing else is installed, but every relaxation is refused: the
seeded no-auth personas are not served (every artifact route answers 401) and the CORS
allowlist is empty. Name the profile deliberately.

- `local` (SDK-free): the whole pipeline runs offline (deterministic optimiser and
  LLM, in-memory audience benchmarks). No Google Cloud SDK. This is what CI and the demo run.
- `gcp`: the managed stack (BigQuery audience benchmarks, Model Armor, Cloud Logging).
- `platform`: consume the shared Hrz services (guardrail / audit / eval / registry) over S2S.
- `onprem`: fail-fast placeholders that raise `NotImplementedError`, the migration target
  (see `docs/onprem-migration.md`).

`MKT_VERTICAL` (`banking` | `online_retail`) and `MKT_MARKET` (`JP` | `AU` | `SG`) select the
active vertical and market; the market's residency region and locales come from the per-market
profile in `config/settings.yaml`, never a hard-coded branch.

## 1. Offline demo and smoke (no cloud)

```bash
make demo          # build a cited plan + render the static audit-first HTML into scripts/out
make smoke-local   # end-to-end offline: build one cited plan under the local profile
make run-api       # FastAPI on 127.0.0.1:8101 (local profile binds loopback by default)
```

The agent card is served at `GET /.well-known/agent-card.json` and the health probe at
`GET /healthz` (reports the active profile, market and vertical).

## 2. Deploy (managed stack)

```bash
# 1. Provision infra (review the plan; the WORM bucket lock is irreversible when
#    locked = true, the default).
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, org_id, access_policy_id
terraform init -input=false && terraform plan
terraform apply

# 2. Export the outputs the app reads.
export GOOGLE_CLOUD_PROJECT="$(terraform output -raw project_id)"
export MKT_CAMPAIGN_REGION="$(terraform output -raw region)"
export MKT_CAMPAIGN_CMEK_KEY="$(terraform output -raw cmek_key)"
export MKT_CAMPAIGN_LOG_BUCKET="$(terraform output -raw log_bucket)"

# 3. Install the managed stack and run the API.
pip install -e ".[gcp,dev]"
export GOOGLE_CLOUD_PROJECT=your-sg-project MKT_CAMPAIGN_PROFILE=gcp
gcloud auth application-default login
make run-api PROFILE=gcp          # FastAPI on :8101 (front with the platform ingress)
```

For a quick project-scoped evaluation WITHOUT org-level prerequisites, set `enable_vpc_sc =
false` and the audit bucket `locked = false` so everything stays deletable (not compliant for
production). See `infra/terraform/terraform.tfvars.example` and `infra/terraform/README.md`.

The ADK agent is deployed to Agent Runtime separately via the Agent Platform SDK; see the
docstring in `src/campaign_planner/agent/root_agent.py`. Record the resulting `reasoningEngine`
resource name in `settings.agent_engine.resource_name` (or `MKT_AGENT_ENGINE`). To attach an
out-of-process governed MCP tool server, set `MKT_CAMPAIGN_MCP_SERVER_URL`; unset, the agent
uses its in-process FunctionTools.

## 3. Region selection and fail-fast

The Terraform `region` is validated against the residency allowlist; an apply against a region
outside it fails at `terraform plan`, before anything is created. BigQuery, Cloud Logging and
the WORM bucket are all created in the selected region, and a `gcp.resourceLocations` Org Policy
hard-restricts resource creation to it. The app also validates the active market's region at
load, so a mismatched deploy fails fast on both sides.

## 4. Key rotation, retention and the WORM lock

The CMEK crypto key (`kms.tf`) rotates on schedule; rotation is transparent to the app. The
audit bucket retention is `retention_days` (default 2557, ~7 years) and the bucket is
`locked = true` by default, which is **irreversible**. To trial without locking, set
`locked = false` (not compliant for production). Only screened prompts and responses are ever
written to the audit log.

## 5. Kill switch

To stop serving without tearing down state: scale the Cloud Run / Agent Runtime deployment to
zero, or remove the app service account's `roles/aiplatform.user` binding. The audit trail
remains intact.

## 6. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `NotImplementedError` from a CLI command (exit 2) | `MKT_CAMPAIGN_PROFILE=onprem` with placeholder adapters | Set `MKT_CAMPAIGN_PROFILE=gcp` (or implement the on-prem adapter) |
| Plan rejected: total budget not positive | `total_budget <= 0` in the request | Pass a positive budget in the market currency |
| Guardrail block on a benign objective (HTTP 400) | Model Armor template too strict | Tune the `model_armor` template filter confidence levels |
| CORS error from the embedded UI | Origin not in the per-tenant allowlist | Add the parent origin to `MKT_CAMPAIGN_CORS_ORIGINS` (never `*`) |
| HTTP 503 "refusing to serve the unauthenticated ... posture" | The bound identity adapter does not verify the end user (seeded personas, the on-prem placeholder, or no profile chosen) and the peer is not loopback | Front the service with IAP and set `MKT_CAMPAIGN_PROFILE=gcp`, or serve the offline demo on loopback only. `MKT_CAMPAIGN_ALLOW_INSECURE_DEMO=1` accepts the exposure deliberately |
| VPC-SC denies the apply | Runner identity outside the perimeter | Apply with `vpc_sc_enforce = false`, add the identity to `operator_members`, re-apply true |
