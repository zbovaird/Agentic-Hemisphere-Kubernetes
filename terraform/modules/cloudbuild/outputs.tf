output "trigger_id" {
  description = "Cloud Build trigger ID"
  value       = google_cloudbuild_trigger.build_images.trigger_id
}
