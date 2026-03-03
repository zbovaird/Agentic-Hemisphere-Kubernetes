variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "registry_url" {
  description = "Full Artifact Registry URL (e.g. us-central1-docker.pkg.dev/PROJECT/hemisphere-repo)"
  type        = string
}

variable "github_owner" {
  description = "GitHub repository owner (user or org)"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "Agentic-Hemisphere-Kubernetes"
}
