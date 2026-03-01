locals {
  workload_identity_pool = "${var.project_id}.svc.id.goog"
}

# --- RH Planner Service Account ---

resource "google_service_account" "rh_planner" {
  project      = var.project_id
  account_id   = "rh-planner-sa"
  display_name = "RH Planner Service Account"
  description  = "Workload Identity SA for the Right Hemisphere planner pod"
}

resource "google_project_iam_member" "rh_planner_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.rh_planner.email}"
}

resource "google_service_account_iam_member" "rh_planner_wi_binding" {
  service_account_id = google_service_account.rh_planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.workload_identity_pool}[${var.owner_namespace}/rh-planner]"
}

# --- LH Executor Service Account ---

resource "google_service_account" "lh_executor" {
  project      = var.project_id
  account_id   = "lh-executor-sa"
  display_name = "LH Executor Service Account"
  description  = "Workload Identity SA for ephemeral Left Hemisphere executor pods"
}

resource "google_project_iam_member" "lh_executor_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.lh_executor.email}"
}

resource "google_service_account_iam_member" "lh_executor_wi_binding" {
  service_account_id = google_service_account.lh_executor.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.workload_identity_pool}[${var.employee_namespace}/lh-executor]"
}

# --- Operator Service Account ---

resource "google_service_account" "operator" {
  project      = var.project_id
  account_id   = "hemisphere-operator-sa"
  display_name = "Hemisphere Operator Service Account"
  description  = "Workload Identity SA for the Kopf operator (Corpus Callosum)"
}

resource "google_project_iam_member" "operator_container" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.operator.email}"
}

resource "google_service_account_iam_member" "operator_wi_binding" {
  service_account_id = google_service_account.operator.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.workload_identity_pool}[${var.owner_namespace}/hemisphere-operator]"
}
