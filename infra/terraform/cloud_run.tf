# cloud_run.tf - Cloud Run v2 service for the campaign-planner FastAPI app.
#
# Runs the container built from the repo Dockerfile (campaign_planner.api.app:app on port
# 8101) as the dedicated least-privilege runtime identity (Workload Identity, no keys),
# encrypted with the regional CMEK key, in the selected region.
#
# Control map:
#   Residency: location pinned to var.region (the allowlisted deploy region).
#   CMEK: the revision is encrypted with the regional key (run SA binding in kms.tf).
#   Least privilege: runs as google_service_account.runtime, not the default compute SA.
#   Managed-first / controlled ingress: ingress is internal + load balancer, not open to the
#              public internet.
#   Profile opt-in: MKT_CAMPAIGN_PROFILE=gcp is set EXPLICITLY here (the app defaults to the
#              offline `local` profile when unset; production must opt in to the managed stack).

resource "google_cloud_run_v2_service" "campaign" {
  name     = "campaign-planner"
  location = var.region
  project  = var.project_id

  # Internal + load balancer ingress - not exposed to the open internet.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # Encrypt the revision with the regional CMEK key.
    encryption_key                   = google_kms_crypto_key.campaign.id
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 1
      max_instance_count = 4
    }

    containers {
      image = var.image

      ports {
        container_port = 8101
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # Opt in to the managed stack explicitly (never rely on the baked-in `local` default).
      env {
        name  = "MKT_CAMPAIGN_PROFILE"
        value = "gcp"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      # settings.yaml defaults to asia-southeast1; pass the selected region through explicitly.
      env {
        name  = "MKT_REGION"
        value = var.region
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8101
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8101
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.run,
    google_project_iam_member.runtime,
  ]
}
