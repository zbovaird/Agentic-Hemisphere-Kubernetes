output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.autopilot.name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.autopilot.endpoint
}

output "cluster_ca_certificate" {
  description = "GKE cluster CA certificate (base64)"
  value       = google_container_cluster.autopilot.master_auth[0].cluster_ca_certificate
}

output "workload_identity_pool" {
  description = "Workload Identity pool for the cluster"
  value       = "${var.project_id}.svc.id.goog"
}
