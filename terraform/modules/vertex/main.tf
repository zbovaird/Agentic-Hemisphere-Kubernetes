resource "google_vertex_ai_endpoint" "hemisphere" {
  provider = google-beta

  name         = "hemisphere-endpoint"
  display_name = var.display_name
  location     = var.region
  project      = var.project_id
  labels       = var.labels

  lifecycle {
    ignore_changes = [
      traffic_split,
    ]
  }
}
