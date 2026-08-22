# variables.tf - The only knobs. Everything else is a concrete in-region value.
#
# Control map:
#   Residency: `region` is SELECTED AT DEPLOY TIME and validated against the residency
#              allowlist `allowed_regions` so a caller fails fast rather than deploying to
#              an unvetted, out-of-jurisdiction region. Both default to asia-southeast1
#              (Singapore), so the out-of-the-box posture is unchanged; deploying anywhere
#              else is a deliberate act that must set BOTH variables. This mirrors the
#              app's own load-time region check (config.market_profile / settings.yaml).
#   Auditability / retention: `retention_days` is a variable (the WORM bucket lock is
#              irreversible, so the retention window must be a deliberate input). It mirrors
#              config/settings.yaml logging.retention_days (2557, ~7 years).
#
# Per the build contract, ONLY project_id and a few genuinely per-tenant values
# (org/billing ids, the image ref, the VPC-SC toggle) are variables. All service
# identifiers, locations and template names are concrete.

variable "project_id" {
  description = "Target GCP project id (required). Single-tenant, Singapore-resident."
  type        = string
}

variable "allowed_regions" {
  description = <<-EOT
    Residency allowlist: the regions this stack may be deployed to. The region is chosen at
    deploy time (var.region) and validated against this list to FAIL FAST, so an operator
    cannot accidentally deploy to an unvetted region. Extending this list is the deliberate
    residency review point: add a region only after confirming the full managed stack
    (Vertex AI, Model Armor, DLP, BigQuery, Cloud Run, Cloud KMS, Logging) and your
    residency obligations are satisfied in that region.
  EOT
  type        = list(string)
  default     = ["asia-southeast1"]

  validation {
    condition     = length(var.allowed_regions) > 0
    error_message = "allowed_regions must list at least one residency-approved region."
  }
}

variable "region" {
  description = <<-EOT
    Deployment region, SELECTED AT DEPLOY TIME. Defaults to asia-southeast1 (Singapore) but
    is overridable. Validated against var.allowed_regions so an unapproved region fails fast
    at `terraform plan` rather than deploying data out of jurisdiction.
  EOT
  type        = string
  default     = "asia-southeast1"

  validation {
    # Cross-variable validation (Terraform >= 1.9). Fails at plan time = setup time.
    condition     = contains(var.allowed_regions, var.region)
    error_message = "region must be one of var.allowed_regions (residency allowlist). Add it there first if that region is approved for this workload."
  }
}

variable "zone" {
  description = "Default zone for zonal resources. Must lie inside the selected var.region."
  type        = string
  default     = "asia-southeast1-a"

  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must be a zone of the selected region (e.g. \"${var.region}-a\")."
  }
}

variable "retention_days" {
  description = "WORM audit-log retention in days. Default ~7 years. Lock is irreversible."
  type        = number
  default     = 2557 # ~7 years; mirrors config/settings.yaml logging.retention_days

  validation {
    condition     = var.retention_days >= 2557
    error_message = "Compliance retention must be at least 2557 days (~7 years)."
  }
}

variable "image" {
  description = "Fully-qualified container image for the Cloud Run service (Artifact Registry, asia-southeast1, built from the repo Dockerfile)."
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/your-gcp-project/mkt/campaign-planner:0.1.0"
}

variable "org_id" {
  description = "Organization id. Required for Org Policy and Access Context Manager (VPC-SC)."
  type        = string
  default     = ""
}

variable "access_policy_id" {
  description = <<-EOT
    Existing Access Context Manager policy id (numeric, no prefix) for the org.
    Required when enable_vpc_sc = true; the service perimeter is created under it.
    Create once per org with:
      gcloud access-context-manager policies create \
        --organization=ORG_ID --title="sg-residency"
  EOT
  type        = string
  default     = ""
}

variable "enable_vpc_sc" {
  description = "Create the VPC Service Controls perimeter around the AI / data APIs."
  type        = bool
  default     = true
}

variable "vpc_sc_dry_run" {
  description = "Stand the perimeter up in dry-run (spec only, not enforced) first. Set false to enforce ONLY after a clean dry-run in the audit logs."
  type        = bool
  default     = true
}
