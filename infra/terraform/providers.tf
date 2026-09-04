# providers.tf - Provider pinning for the campaign-planner Campaign Planner sovereign deploy.
#
# Control map (this repo has no numbered principle ledger; controls map to the
# documented posture in README.md / SPEC.md and the deploy-and-residency-hardening skill):
#   Residency: every provider call is pinned to var.region (the allowlisted deploy region).
#              There is no global / multi-region default endpoint.
#   No lock-in: Terraform is the only place infra is described; the application talks to
#              ports (see config.py / settings.yaml adapters block), never these resources.
#
# google-beta is declared because some sovereignty surfaces (Access Context Manager,
# org_policy v2) are exposed on the beta provider in the pinned line.

terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.40, < 7.0" # current GA line (mid-2026)
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.40, < 7.0"
    }
  }
}

# Primary (GA) provider - every resource defaults to Singapore.
provider "google" {
  project = var.project_id
  region  = var.region # the selected region, pinned, never global
}

# Beta provider - same project / region, used only where a resource needs it.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
