# kms.tf - One regional Customer-Managed Encryption Key (CMEK) in Singapore.
#
# Control map:
#   CMEK does NOT cascade: a CMEK on one resource does not protect data that resource hands
#              to another service. Each managed service this stack uses (Logging, Vertex AI,
#              BigQuery, Cloud Run, the staging bucket) gets its OWN cryptoKey IAM binding
#              here, never a project-wide grant.
#   Residency: the key ring location is var.region - a regional key, never the
#              global / multi-region key. Regional CMEK is what pins crypto material
#              in-country.

resource "google_kms_key_ring" "campaign" {
  name     = "campaign-planner"
  location = var.region # the selected region - regional, in-country key material

  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "campaign" {
  name     = "campaign-cmek"
  key_ring = google_kms_key_ring.campaign.id

  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days - periodic rotation for key hygiene

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    # A destroyed key is unrecoverable and would strand all CMEK-encrypted data.
    prevent_destroy = true
  }
}

# --------------------------------------------------------------------------- #
# Grant each service agent the right to use the key. CMEK does not cascade:
# every service that encrypts with this key needs its OWN binding here.
# --------------------------------------------------------------------------- #
data "google_project" "this" {
  project_id = var.project_id
}

# Cloud Logging service agent (CMEK on the WORM audit bucket).
resource "google_kms_crypto_key_iam_member" "logging" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-logging.iam.gserviceaccount.com"
}

# Vertex AI / Agent Platform service agent (CMEK on reasoning + eval + runtime state).
resource "google_kms_crypto_key_iam_member" "aiplatform" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# BigQuery service agent (CMEK on the audience-warehouse dataset / tables).
resource "google_kms_crypto_key_iam_member" "bigquery" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:bq-${data.google_project.this.number}@bigquery-encryption.iam.gserviceaccount.com"
}

# Cloud Run service agent (encrypts the service revision with CMEK).
resource "google_kms_crypto_key_iam_member" "run" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@serverless-robot-prod.iam.gserviceaccount.com"
}

# Cloud Storage service agent (CMEK on the agent-runtime staging bucket).
resource "google_kms_crypto_key_iam_member" "storage" {
  crypto_key_id = google_kms_crypto_key.campaign.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gs-project-accounts.iam.gserviceaccount.com"
}
