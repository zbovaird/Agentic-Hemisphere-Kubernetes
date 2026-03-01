variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "cluster_name" {
  description = "GKE cluster name (used in Workload Identity binding)"
  type        = string
}

variable "owner_namespace" {
  description = "Kubernetes namespace for the owner role"
  type        = string
  default     = "owner"
}

variable "employee_namespace" {
  description = "Kubernetes namespace for the employee role"
  type        = string
  default     = "employee"
}
