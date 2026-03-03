variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Artifact Registry repository"
  type        = string
}

variable "repository_id" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "hemisphere-repo"
}

variable "labels" {
  description = "Labels to apply to the repository"
  type        = map(string)
  default     = {}
}
