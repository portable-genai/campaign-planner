# bigquery.tf : the audience-data warehouse (segments and channel benchmarks).
#
# Principle map:
#   Residency  : the dataset is created in var.region; audience data stays there.
#   CMEK       : the dataset uses the regional CMEK from kms.tf (the BigQuery service-agent
#                key binding lives in kms.tf, because CMEK does not cascade).
#
# THIS FILE DID NOT EXIST, and that is the defect it closes. `config/settings.yaml` has named
# `mkt_campaign_audience`, `audience_segments` and `channel_benchmarks` since the repository
# was written, and `adapters/gcp/bigquery_audience.py` queries all three. Everything AROUND
# them was provisioned: `apis.tf` enables the BigQuery API with a comment naming this very
# dataset, `iam.tf` grants the serving identity dataViewer and jobUser, and `kms.tf` binds the
# BigQuery service agent to the regional key. All of it pointed at something nothing created,
# so the managed profile would have failed at the first request with a not-found rather than
# with anything that explained itself, and every surrounding control looked correct.
#
# The absence was invisible offline because the local profile served an in-process dictionary
# and never ran SQL. tests/contract/test_demo_book.py now parses this file and fails when the
# adapter selects a column it does not declare, or when the shipped book carries one it does
# not have, so the schema and the reader cannot drift apart again while both look fine.
#
# scripts/load_demo_book.py fills these tables from the shipped fictional book, and refuses a
# dataset whose book_manifest does not declare itself fictional.

resource "google_bigquery_dataset" "audience" {
  dataset_id  = "mkt_campaign_audience" # matches settings.yaml bigquery.dataset
  project     = var.project_id
  location    = var.region
  description = "Campaign audience warehouse: addressable segments and channel benchmarks (CMEK)."

  default_encryption_configuration {
    kms_key_name = google_kms_crypto_key.campaign.id
  }

  # Audience data is internal: never world-readable, and never dropped by a plan that only
  # meant to change a schema.
  delete_contents_on_destroy = false

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.bigquery,
  ]
}

# One addressable segment per market and vertical. `consent_rate` is load-bearing rather than
# descriptive: the planner may only target the reachable AND consented subset, so a row that
# overstated it would let a plan address people who never agreed to be addressed.
resource "google_bigquery_table" "audience_segments" {
  dataset_id          = google_bigquery_dataset.audience.dataset_id
  table_id            = "audience_segments" # matches settings.yaml bigquery.segments_table
  project             = var.project_id
  deletion_protection = true

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  encryption_configuration {
    kms_key_name = google_kms_crypto_key.campaign.id
  }

  schema = jsonencode([
    { name = "id", type = "STRING", mode = "REQUIRED" },
    { name = "name", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "size", type = "INTEGER", mode = "REQUIRED" },
    { name = "reachable_size", type = "INTEGER", mode = "REQUIRED" },
    { name = "propensity", type = "FLOAT", mode = "REQUIRED" },
    { name = "expected_value", type = "FLOAT", mode = "REQUIRED" },
    { name = "consent_rate", type = "FLOAT", mode = "REQUIRED" },
    { name = "tags", type = "STRING", mode = "REPEATED" },
    { name = "evidence_summary", type = "STRING", mode = "REQUIRED" },
  ])
}

# The cost and performance assumptions the deterministic allocation engine spends against.
# The model never sets a CPM or a conversion rate; these rows do, which is what makes a
# budget split reproducible and arguable rather than generated.
resource "google_bigquery_table" "channel_benchmarks" {
  dataset_id          = google_bigquery_dataset.audience.dataset_id
  table_id            = "channel_benchmarks" # matches settings.yaml bigquery.benchmarks_table
  project             = var.project_id
  deletion_protection = true

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  encryption_configuration {
    kms_key_name = google_kms_crypto_key.campaign.id
  }

  schema = jsonencode([
    { name = "channel", type = "STRING", mode = "REQUIRED" },
    { name = "market", type = "STRING", mode = "REQUIRED" },
    { name = "vertical", type = "STRING", mode = "REQUIRED" },
    { name = "cpm", type = "FLOAT", mode = "REQUIRED" },
    { name = "ctr", type = "FLOAT", mode = "REQUIRED" },
    { name = "conversion_rate", type = "FLOAT", mode = "REQUIRED" },
    { name = "max_reach", type = "INTEGER", mode = "REQUIRED" },
    { name = "min_spend", type = "FLOAT", mode = "REQUIRED" },
  ])
}

# What this dataset holds and whether it may be replaced. `fictional` is the loader's
# overwrite guard: a populated dataset without it is somebody's real audience warehouse and
# the loader refuses. Not deletion-protected, because the loader rewrites this row on every
# load and the guard is the control rather than the flag.
resource "google_bigquery_table" "book_manifest" {
  dataset_id          = google_bigquery_dataset.audience.dataset_id
  table_id            = "book_manifest"
  project             = var.project_id
  deletion_protection = false

  # The same key the dataset names, declared again here on purpose. The dataset's
  # default_encryption_configuration makes BigQuery stamp that key onto every table it creates in
  # the dataset, so the live table carries an encryption_configuration whether or not this
  # resource declares one. Leaving it undeclared makes the next plan read the server-set block as
  # a REMOVAL, and removing an encryption configuration FORCES REPLACEMENT: the table is destroyed
  # and recreated, and a recreated table holds no rows. CMEK does not cascade in Terraform's model
  # even though it does in BigQuery's, which is why the key is named twice.
  encryption_configuration {
    kms_key_name = google_kms_crypto_key.campaign.id
  }

  schema = jsonencode([
    { name = "book_version", type = "STRING", mode = "REQUIRED" },
    { name = "as_of_date", type = "DATE", mode = "REQUIRED" },
    { name = "fictional", type = "BOOLEAN", mode = "REQUIRED" },
    { name = "loaded_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "source_commit", type = "STRING", mode = "NULLABLE" },
    { name = "tenant", type = "STRING", mode = "REQUIRED" },
  ])
}
