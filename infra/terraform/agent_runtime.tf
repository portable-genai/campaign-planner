# agent_runtime.tf - Staging bucket for the Gemini Enterprise Agent Platform runtime.
#
# The repo has a reserved agent package (src/campaign_planner/agent) and an agent_engine
# block in config/settings.yaml; the Agent Platform reasoning engine needs a regional,
# CMEK-encrypted staging bucket for its deployment artifacts. The runtime identity it runs
# as is google_service_account.agent_runtime (iam.tf).
#
# Control map:
#   Residency: bucket location is var.region (regional, single region, not multi).
#   CMEK explicit: encrypted with the regional key (storage SA binding in kms.tf).
#   Private data plane: uniform bucket-level access + public access prevention (mirrors the
#              org_policy.tf uniform-bucket-access constraint).

resource "google_storage_bucket" "agent_staging" {
  name     = "${var.project_id}-mkt-campaign-agent-staging"
  location = var.region # the selected region - regional, in-country
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  encryption {
    default_kms_key_name = google_kms_crypto_key.campaign.id
  }

  # Keep a few prior staged versions; expire them so the bucket does not grow unbounded.
  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.storage,
  ]
}
