# vpc_sc.tf - VPC Service Controls perimeter around the AI / data plane.
#
# Control map:
#   Residency + exfiltration control: a service perimeter draws a logical boundary around
#              the sovereignty-critical APIs (Vertex AI, BigQuery, Model Armor, Logging,
#              Cloud Trace, KMS). Data cannot be read across the boundary to a non-Singapore
#              project, which is what stops the audience warehouse and audit log from leaving
#              the country.
#
# Guarded by var.enable_vpc_sc (count = 0 to skip in non-prod / dev).
#
# DRY-RUN FIRST (var.vpc_sc_dry_run = true by default):
#   With dry_run = true the perimeter is described in `spec` only and is NOT enforced; denied
#   calls are logged but allowed through, so you can confirm from the audit logs that no
#   legitimate path breaks. Flip vpc_sc_dry_run = false to move the same config into `status`
#   (enforced) ONLY after a clean dry-run, and after adding your operator / CI identity to an
#   access level so the apply itself is not denied.
#   # verify: VPC-SC dry-run mode for a safe rollout.

locals {
  perimeter_restricted_services = [
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "modelarmor.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudkms.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_access_context_manager_service_perimeter" "campaign" {
  count = var.enable_vpc_sc ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/mkt_campaign_planner_sg"
  title  = "mkt_campaign_planner_sg"

  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # Enforced configuration: populated only when vpc_sc_dry_run = false.
  dynamic "status" {
    for_each = var.vpc_sc_dry_run ? [] : [1]
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  # Dry-run configuration: populated only when vpc_sc_dry_run = true (default). Denied calls
  # are logged, not blocked, so the rollout can be watched before enforcing.
  dynamic "spec" {
    for_each = var.vpc_sc_dry_run ? [1] : []
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  # Tells the API the spec block is a dry-run, not the enforced status.
  use_explicit_dry_run_spec = var.vpc_sc_dry_run

  depends_on = [google_project_service.required]
}
