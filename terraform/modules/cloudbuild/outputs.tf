output "trigger_id" {
  description = "Cloud Build trigger ID (empty if GitHub not linked)"
  value       = var.github_owner != "" ? google_cloudbuild_trigger.build_images[0].trigger_id : ""
}
