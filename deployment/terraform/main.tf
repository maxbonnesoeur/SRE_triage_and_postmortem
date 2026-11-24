locals {
  required_apis = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
  ])

  runtime_roles = toset([
    "roles/aiplatform.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
  ])
}

resource "google_project_service" "apis" {
  for_each           = local.required_apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.service_name
  description   = "Container images for SRE Triage & Postmortem Commander"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "runtime" {
  account_id   = "${var.service_name}-sa"
  display_name = "SRE Triage Agent Cloud Run Runtime SA"
}

resource "google_project_iam_member" "runtime_permissions" {
  for_each = local.runtime_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "agent" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "SRE_OTEL_EXPORTER"
        value = "gcp_trace"
      }
      env {
        name  = "SRE_REQUIRE_APPROVAL_FOR_DESTRUCTIVE_OPS"
        value = "true"
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.runtime_permissions,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.agent.location
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
