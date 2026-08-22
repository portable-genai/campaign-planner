# outputs.tf - Values the app / operators need to wire settings.yaml after apply.
#
# These map onto config/settings.yaml / config.py fields so a deploy is "apply, then export
# these into the runtime environment".

output "project_id" {
  description = "The deployment project id."
  value       = var.project_id
}

output "region" {
  description = "The region this stack deployed to (selected at deploy time from var.allowed_regions)."
  value       = var.region
}

# --------------------------------- KMS -------------------------------------- #
output "cmek_key" {
  description = "Regional CMEK crypto key id (protects logs, BigQuery, Cloud Run, staging bucket)."
  value       = google_kms_crypto_key.campaign.id
}

# ------------------------------- Cloud Run ---------------------------------- #
output "service_url" {
  description = "Base URL of the Mkt2 Cloud Run service."
  value       = google_cloud_run_v2_service.campaign.uri
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.campaign.name
}

# ----------------------------- Service accounts ----------------------------- #
output "runtime_service_account" {
  description = "Least-privilege Cloud Run runtime identity (Workload Identity, no keys)."
  value       = google_service_account.runtime.email
}

output "agent_runtime_service_account" {
  description = "Agent Platform reasoning-engine identity."
  value       = google_service_account.agent_runtime.email
}

# ------------------------------- WORM logging ------------------------------- #
output "log_bucket" {
  description = "Locked WORM audit log bucket id (settings.yaml logging.bucket)."
  value       = google_logging_project_bucket_config.worm_audit.id
}

output "audit_sink_writer_identity" {
  description = "Sink writer identity (grant it bucket access if cross-project)."
  value       = google_logging_project_sink.audit_to_worm.writer_identity
}

# ------------------------------- Agent staging ------------------------------ #
output "agent_staging_bucket" {
  description = "Regional, CMEK-encrypted staging bucket for the Agent Platform runtime."
  value       = google_storage_bucket.agent_staging.name
}
