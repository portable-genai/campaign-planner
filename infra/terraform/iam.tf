# iam.tf - Least-privilege service accounts for the campaign-planner workloads.
#
# Control map:
#   Least privilege / separation of duties: two distinct identities - the Cloud Run runtime
#              (serving / API, which reads the audience warehouse, calls the model + guardrail
#              and writes audit) and the agent runtime (Gemini Enterprise Agent Platform /
#              reasoning engine). Each gets only the roles it needs; no shared kitchen-sink SA,
#              and no exported keys (Workload Identity; SA-key creation is denied in
#              org_policy.tf).
#   Residency: identities are project-scoped; data access is to in-region services only.
#   CMEK explicit: each SA that touches CMEK-encrypted data gets its own cryptoKey-use binding.

# --------------------------- Cloud Run runtime ------------------------------ #
resource "google_service_account" "runtime" {
  account_id   = "mkt-campaign-run"
  display_name = "campaign-planner Campaign Planner - Cloud Run runtime (serving / API)"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

locals {
  # Serving path: READ the audience warehouse, call the reasoning model + Model Armor
  # guardrail, run evals, write audit + traces. It never writes audience data.
  runtime_roles = [
    "roles/aiplatform.user",      # Gemini reasoning + Gen AI evals (Vertex AI)
    "roles/bigquery.dataViewer",  # read the audience-segment + benchmark tables
    "roles/bigquery.jobUser",     # run the read queries (client.query)
    "roles/modelarmor.user",      # INPUT / OUTPUT guardrail screening
    "roles/logging.logWriter",    # write audit events to the WORM sink
    "roles/cloudtrace.agent",     # OpenTelemetry spans (content OFF)
    "roles/storage.objectViewer", # read the agent-runtime staging bucket
  ]
}

resource "google_project_iam_member" "runtime" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime uses the CMEK for envelope ops it performs directly.
resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime.email}"
}

# ----------------------------- Agent runtime -------------------------------- #
# Identity for the Gemini Enterprise Agent Platform reasoning engine (agent_engine in
# settings.yaml). Kept separate from the serving identity so the agent surface has its own
# least-privilege role set.
resource "google_service_account" "agent_runtime" {
  account_id   = "mkt-campaign-agent"
  display_name = "campaign-planner Agent Runtime (Gemini Enterprise Agent Platform)"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "agent_runtime" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/storage.objectAdmin", # read / write its own staging bucket objects
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.agent_runtime.email}"
}

resource "google_kms_crypto_key_iam_member" "agent_runtime" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.agent_runtime.email}"
}
