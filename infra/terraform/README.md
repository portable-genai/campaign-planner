# `campaign-planner` Campaign Planner: Terraform (Singapore-resident, sovereign deploy)

This module provisions the **Singapore-resident** managed stack for the `campaign-planner` Campaign
Planning and Budget Allocation service. The region is **selected at deploy time** and
validated against the residency allowlist `allowed_regions`; it defaults to
`asia-southeast1` (Singapore) and every resource follows `var.region`. Only `project_id`,
the residency values and a few genuinely per-tenant values are variables.

It makes the cloud posture enforceable at deploy time: residency, encryption, perimeter and
audit are pinned here so `terraform plan` fails when a deploy would violate them, and a
reviewer can read the control next to the resource it governs. (This repo has no numbered
principle ledger, so each file's header maps its control to the documented posture in
`README.md` / `SPEC.md` and the `deploy-and-residency-hardening` skill.)

## What each file does

| File | Purpose |
|---|---|
| `providers.tf` | Provider pinning; region wired from `var.region`, never global. |
| `variables.tf` | The only knobs. `region` validated against `allowed_regions` (fail-fast); both default to `asia-southeast1`. |
| `terraform.tfvars.example` | Sample values (obviously fictional ids). Copy to `terraform.tfvars`. |
| `apis.tf` | Enable exactly the services the gcp adapters use, plus run / artifactregistry / cloudkms / iam / logging. |
| `org_policy.tf` | `gcp.resourceLocations` allowlist (derived from `var.region`), disable SA-key creation, no external IPs, uniform bucket access. |
| `kms.tf` | One regional CMEK key + a per-service IAM binding (logging, Vertex AI, BigQuery, Cloud Run, Storage). |
| `vpc_sc.tf` | Service perimeter around the AI / data APIs. `vpc_sc_dry_run = true` first. |
| `logging_worm.tf` | Locked (WORM) Cloud Logging bucket + sink + data-access audit config. |
| `monitoring.tf` | Log-based alerts: guardrail blocks, SA-key creation, VPC-SC denials. |
| `iam.tf` | Least-privilege runtime + agent-runtime service accounts (no keys). |
| `cloud_run.tf` | Cloud Run v2 service: the FastAPI container on port 8101, CMEK, `MKT_CAMPAIGN_PROFILE=gcp`, `/healthz` probes. |
| `agent_runtime.tf` | Regional, CMEK-encrypted staging bucket for the Gemini Enterprise Agent Platform runtime. |
| `outputs.tf` | Values to wire into the runtime environment after apply. |

## Which services are enabled (and why)

Tied to the `adapters: gcp:` bindings in `config/settings.yaml`:

- `aiplatform.googleapis.com`: `gemini_llm` (Vertex genai), `genai_eval`, the Agent Platform runtime.
- `bigquery.googleapis.com`: `bigquery_audience` (audience-segment + benchmark warehouse).
- `modelarmor.googleapis.com`: `model_armor_guardrail` (INPUT / OUTPUT screening).
- `logging.googleapis.com`: `cloud_logging_audit` (WORM audit sink).
- `cloudtrace.googleapis.com`: `cloud_trace_tracer` (OpenTelemetry spans).
- Always-needed for the deploy + posture: `run`, `artifactregistry`, `cloudkms`, `iam`, `storage`, `compute`, `orgpolicy`, `accesscontextmanager`, `monitoring`.

Services this repo never calls are not enabled.

## Residency posture

- Region is chosen at deploy time (`var.region`) and validated against the residency
  allowlist `var.allowed_regions` at `terraform plan` (`variables.tf`); the app validates its
  own region again at settings load (`config.py` / `settings.yaml`). Both default to
  `asia-southeast1`, and a deploy elsewhere must set BOTH terraform variables and the app's
  matching market profile.
- `gcp.resourceLocations` is derived from `var.region`, so it rejects any resource created
  outside the region actually deployed to (defence in depth).
- One regional CMEK key, bound per service (no project-wide grant); a global / multi-region
  key would not give residency.
- VPC-SC perimeter confines the AI / data APIs; dry-run first, enforce only after a clean run.
- The audit log lands in a locked (WORM) bucket with ~7-year retention; the app redacts
  before it logs, the infra makes the records immutable.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # fill in project_id, org_id, image, ...
terraform init -input=false
terraform plan                                  # or: make tf-plan (from repo root)
terraform apply
```

## Cautions

- **WORM lock is irreversible** (`logging_worm.tf`). Confirm `retention_days` before apply.
- **VPC-SC deploy order** matters (`vpc_sc.tf`): keep `vpc_sc_dry_run = true`, confirm no
  legitimate path breaks in the audit logs, add your runner / CI identity to an access level,
  then re-apply with `vpc_sc_dry_run = false` to enforce.
- Attach a notification channel to the alert policies in `monitoring.tf` so blocks page someone.
- This module is **not run** as part of the offline CI gate; it is infra-as-code for review.
