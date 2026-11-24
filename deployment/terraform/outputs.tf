output "cloud_run_url" {
  description = "Deployed Cloud Run service URL."
  value       = google_cloud_run_v2_service.agent.uri
}

output "a2a_agent_card_url" {
  description = "A2A Agent Card discovery endpoint."
  value       = "${google_cloud_run_v2_service.agent.uri}/.well-known/agent.json"
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository URL."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "runtime_service_account" {
  description = "Least-privilege service account email for Cloud Run."
  value       = google_service_account.runtime.email
}
