output "cluster_name" {
  description = "GKE cluster name"
  value       = module.gke.cluster_name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = module.gke.cluster_endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "GKE cluster CA certificate (base64)"
  value       = module.gke.cluster_ca_certificate
  sensitive   = true
}

output "rh_planner_sa_email" {
  description = "Google Service Account email for the RH Planner"
  value       = module.iam.rh_planner_sa_email
}

output "lh_executor_sa_email" {
  description = "Google Service Account email for the LH Executor"
  value       = module.iam.lh_executor_sa_email
}

output "operator_sa_email" {
  description = "Google Service Account email for the Operator"
  value       = module.iam.operator_sa_email
}

output "vertex_endpoint_id" {
  description = "Vertex AI endpoint resource name"
  value       = module.vertex.endpoint_id
}

output "owner_namespace" {
  description = "Owner namespace name"
  value       = module.namespaces.owner_namespace
}

output "employee_namespace" {
  description = "Employee namespace name"
  value       = module.namespaces.employee_namespace
}

output "monitoring_dashboard_id" {
  description = "Cloud Monitoring dashboard ID"
  value       = module.monitoring.dashboard_id
}
