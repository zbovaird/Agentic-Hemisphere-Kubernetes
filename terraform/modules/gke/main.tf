resource "google_container_cluster" "autopilot" {
  provider = google-beta

  name     = var.cluster_name
  location = var.region
  project  = var.project_id

  enable_autopilot = true

  release_channel {
    channel = var.release_channel
  }

  ip_allocation_policy {}

  resource_labels = var.labels

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  deletion_protection = false
}
