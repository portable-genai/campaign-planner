# org_policy.tf - Org Policy constraints enforcing the selected-region residency (defence in depth).
#
# Control map:
#   Residency (defence in depth): even if someone hand-edits a resource, gcp.resourceLocations
#              REJECTS the creation of resources outside the selected region. This is the master
#              residency control behind the per-resource pinning in the sibling files.
#   No exported keys (least privilege): iam.disableServiceAccountKeyCreation forces Workload
#              Identity instead of long-lived JSON keys; key creation is also alerted on in
#              monitoring.tf.
#   Private data plane: no external IPs + uniform bucket access keep data in-country and off
#              the open internet.
#
# Scoped to the project via parent = "projects/...". To enforce org-wide, move these to
# parent = "organizations/${var.org_id}".
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy

# Master residency policy: only allow locations inside the selected region.
resource "google_org_policy_policy" "resource_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        # e.g. "in:asia-southeast1-locations" - the selected region plus its sub-locations.
        allowed_values = ["in:${var.region}-locations"]
      }
    }
  }

  depends_on = [google_project_service.required]
}

# Disable service-account key creation: use Workload Identity instead (no long-lived keys).
resource "google_org_policy_policy" "no_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Disable VM external IPs: keep the data plane private.
resource "google_org_policy_policy" "no_external_ip" {
  name   = "projects/${var.project_id}/policies/compute.vmExternalIpAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      deny_all = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Require uniform bucket-level access (no per-object ACL exfiltration paths).
resource "google_org_policy_policy" "uniform_bucket_access" {
  name   = "projects/${var.project_id}/policies/storage.uniformBucketLevelAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}
