variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Vertex AI endpoint"
  type        = string
}

variable "display_name" {
  description = "Display name for the Vertex AI endpoint"
  type        = string
}

variable "model_id" {
  description = "Vertex AI model resource name to deploy (empty string skips deployment)"
  type        = string
  default     = ""
}

variable "traffic_split" {
  description = "Traffic split map: deployed_model_id -> percentage"
  type        = map(number)
  default     = {}
}

variable "labels" {
  description = "Labels to apply to the endpoint"
  type        = map(string)
  default     = {}
}
