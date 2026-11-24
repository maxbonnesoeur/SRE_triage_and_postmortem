variable "project_id" {
  description = "Google Cloud Project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service and Artifact Registry repository name."
  type        = string
  default     = "sre-triage-agent"
}

variable "container_image" {
  description = "Container image URI to deploy to Cloud Run."
  type        = string
}

variable "allow_unauthenticated" {
  description = "Whether to allow public unauthenticated access (false recommended for enterprise)."
  type        = bool
  default     = false
}
