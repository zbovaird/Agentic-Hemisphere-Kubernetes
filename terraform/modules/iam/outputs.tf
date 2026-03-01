output "rh_planner_sa_email" {
  description = "RH Planner Google Service Account email"
  value       = google_service_account.rh_planner.email
}

output "lh_executor_sa_email" {
  description = "LH Executor Google Service Account email"
  value       = google_service_account.lh_executor.email
}

output "operator_sa_email" {
  description = "Operator Google Service Account email"
  value       = google_service_account.operator.email
}
