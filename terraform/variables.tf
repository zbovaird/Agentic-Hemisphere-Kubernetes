variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-east1"
}

variable "cluster_name" {
  description = "Name of the GKE Autopilot cluster"
  type        = string
  default     = "hemisphere-cluster"
}

variable "vertex_display_name" {
  description = "Display name for the Vertex AI endpoint"
  type        = string
  default     = "hemisphere-endpoint"
}

variable "vertex_model_id" {
  description = "Vertex AI model resource name for deployment"
  type        = string
  default     = ""
}

variable "vertex_traffic_split" {
  description = "Traffic split map: deployed_model_id -> percentage (must sum to 100)"
  type        = map(number)
  default     = {}
}

variable "employee_cpu_quota" {
  description = "CPU quota for the employee namespace"
  type        = string
  default     = "2"
}

variable "employee_memory_quota" {
  description = "Memory quota for the employee namespace"
  type        = string
  default     = "2Gi"
}

variable "employee_pod_quota" {
  description = "Maximum number of pods in the employee namespace"
  type        = string
  default     = "10"
}

variable "github_owner" {
  description = "GitHub repository owner (user or org) for Cloud Build trigger"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repository name for Cloud Build trigger"
  type        = string
  default     = "Agentic-Hemisphere-Kubernetes"
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    project   = "agentic-hemisphere"
    managed   = "terraform"
  }
}
