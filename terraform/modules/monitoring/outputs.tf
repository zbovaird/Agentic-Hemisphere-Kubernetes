output "dashboard_id" {
  description = "Cloud Monitoring dashboard ID"
  value       = google_monitoring_dashboard.hemisphere_overview.id
}
