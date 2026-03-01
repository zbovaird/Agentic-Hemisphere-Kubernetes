variable "owner_namespace" {
  description = "Name of the owner namespace"
  type        = string
  default     = "owner"
}

variable "manager_namespace" {
  description = "Name of the manager namespace"
  type        = string
  default     = "manager"
}

variable "employee_namespace" {
  description = "Name of the employee namespace"
  type        = string
  default     = "employee"
}

variable "employee_cpu_quota" {
  description = "CPU limit for the employee namespace"
  type        = string
  default     = "2"
}

variable "employee_memory_quota" {
  description = "Memory limit for the employee namespace"
  type        = string
  default     = "2Gi"
}

variable "employee_pod_quota" {
  description = "Maximum pods in the employee namespace"
  type        = string
  default     = "10"
}
