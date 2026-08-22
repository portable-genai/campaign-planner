# apis.tf - Enable exactly the managed services Mkt2 depends on, nothing speculative.
#
# Control map:
#   Managed-first / minimal surface: only services the pinned gcp adapters actually call
#              (config/settings.yaml adapters: block) are enabled.
#   Residency: enabling these APIs is the prerequisite for the regional, CMEK-protected
#              resources defined in the sibling files.
#
# Each service is tied to the gcp adapter that uses it:
#   aiplatform        -> gemini_llm (Vertex genai), genai_eval (vertexai.evals),
#                        a2a_registry / agent runtime (Gemini Enterprise Agent Platform)
#   bigquery          -> bigquery_audience (audience-segment + benchmark warehouse)
#   modelarmor        -> model_armor_guardrail (INPUT/OUTPUT safety checks)
#   logging           -> cloud_logging_audit (WORM audit sink)
#   cloudtrace        -> cloud_trace_tracer (OpenTelemetry spans)
# Always-needed platform services for any Singapore-resident Cloud Run deploy:
#   run, artifactregistry, cloudkms, iam, storage, compute, orgpolicy, accesscontextmanager.
#
# disable_on_destroy = false so a `terraform destroy` of this stack does not yank platform
# APIs out from under other workloads in a shared project.

locals {
  required_services = [
    # Services the gcp adapters call.
    "aiplatform.googleapis.com", # Gemini reasoning + Gen AI evals + Agent Platform
    "bigquery.googleapis.com",   # audience warehouse (mkt_campaign_audience dataset)
    "modelarmor.googleapis.com", # Model Armor guardrail template
    "logging.googleapis.com",    # Cloud Logging WORM audit bucket + sink
    "cloudtrace.googleapis.com", # Cloud Trace (OpenTelemetry spans)
    # Always-needed for the Cloud Run deploy + residency posture.
    "run.googleapis.com",                  # Cloud Run v2 service (the API container)
    "artifactregistry.googleapis.com",     # image registry (asia-southeast1)
    "cloudkms.googleapis.com",             # regional CMEK key ring + key
    "iam.googleapis.com",                  # least-privilege service accounts
    "storage.googleapis.com",              # agent-runtime staging bucket
    "compute.googleapis.com",              # networking for the perimeter
    "orgpolicy.googleapis.com",            # residency org-policy constraints
    "accesscontextmanager.googleapis.com", # VPC Service Controls perimeter
    "monitoring.googleapis.com",           # log-based metrics + alert policies
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
