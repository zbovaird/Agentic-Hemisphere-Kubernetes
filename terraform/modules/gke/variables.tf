variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the cluster"
  type        = string
}

variable "cluster_name" {
  description = "Name of the GKE Autopilot cluster"
  type        = string
}

variable "release_channel" {
  description = "GKE release channel"
  type        = string
  default     = "REGULAR"
}

variable "labels" {
  description = "Labels to apply to the cluster"
  type        = map(string)
  default     = {}
}
