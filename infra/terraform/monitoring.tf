# monitoring.tf - Log-based alerts on the posture-violation signals.
#
# Control map:
#   Posture alerts: a blocked attempt should page someone, not pass silently. Log-based
#              metrics + alert policies fire on the signals that mean the posture slipped:
#              guardrail / safety blocks, service-account key creation, and VPC-SC perimeter
#              denials. The app already redacts before it logs, so these metrics count events
#              without exposing payloads.
#
# Notification channels are intentionally left to the operator: attach your PagerDuty / email
# channel ids via the GCP console or extend this file, then add them to each alert policy's
# notification_channels list.

# --------------------- 1. Guardrail / safety blocks ------------------------- #
# Counts Model Armor guardrail blocks emitted into this app's audit log. The guardrail
# adapter records a blocked INPUT / OUTPUT decision in the campaign-planner-audit log.
resource "google_logging_metric" "guardrail_blocks" {
  project = var.project_id
  name    = "mkt_campaign_guardrail_blocks"

  filter = <<-EOT
    logName="projects/${var.project_id}/logs/campaign-planner-audit"
    AND (jsonPayload.event_type="guardrail_block" OR jsonPayload.guardrail_decision="blocked")
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "guardrail_blocks" {
  project      = var.project_id
  display_name = "campaign-planner guardrail block detected"
  combiner     = "OR"

  conditions {
    display_name = "Guardrail block count > 0"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.guardrail_blocks.name}\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  documentation {
    content = "A Model Armor guardrail blocked a campaign-planner request. Investigate the audit log entry; a spike may indicate prompt-injection probing."
  }
}

# ----------------- 2. Service-account key creation -------------------------- #
# org_policy.tf denies SA-key creation; this alerts if a creation is even attempted /
# slips through, captured from the Cloud Audit Log.
resource "google_logging_metric" "sa_key_creation" {
  project = var.project_id
  name    = "mkt_campaign_sa_key_creation"

  filter = <<-EOT
    logName:"cloudaudit.googleapis.com"
    AND protoPayload.methodName="google.iam.admin.v1.CreateServiceAccountKey"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "sa_key_creation" {
  project      = var.project_id
  display_name = "campaign-planner service-account key creation attempted"
  combiner     = "OR"

  conditions {
    display_name = "SA key creation count > 0"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.sa_key_creation.name}\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  documentation {
    content = "A service-account key creation was recorded. Org Policy should deny this (Workload Identity only); confirm and revoke any key created."
  }
}

# --------------------- 3. VPC-SC perimeter denials -------------------------- #
# Fires when a request is denied by the VPC Service Controls perimeter (attempted access
# across the residency boundary).
resource "google_logging_metric" "vpc_sc_denials" {
  project = var.project_id
  name    = "mkt_campaign_vpc_sc_denials"

  filter = <<-EOT
    logName:"cloudaudit.googleapis.com%2Fpolicy"
    AND protoPayload.metadata.violationReason!=""
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_alert_policy" "vpc_sc_denials" {
  project      = var.project_id
  display_name = "campaign-planner VPC-SC perimeter denial"
  combiner     = "OR"

  conditions {
    display_name = "VPC-SC denial count > 0"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.vpc_sc_denials.name}\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  documentation {
    content = "A request was denied by the VPC Service Controls perimeter. In dry-run this is expected during rollout; in enforced mode investigate the source identity / project."
  }
}
