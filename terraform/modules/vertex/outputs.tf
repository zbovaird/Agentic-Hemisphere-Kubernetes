output "endpoint_id" {
  description = "Vertex AI endpoint resource name"
  value       = google_vertex_ai_endpoint.hemisphere.name
}

output "endpoint_display_name" {
  description = "Vertex AI endpoint display name"
  value       = google_vertex_ai_endpoint.hemisphere.display_name
}
