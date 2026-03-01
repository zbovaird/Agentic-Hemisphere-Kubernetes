provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "kubernetes" {
  host                   = "https://${module.gke.cluster_endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.cluster_ca_certificate)
}

data "google_client_config" "default" {}

module "gke" {
  source = "./modules/gke"

  project_id   = var.project_id
  region       = var.region
  cluster_name = var.cluster_name
  labels       = var.labels
}

module "iam" {
  source = "./modules/iam"

  project_id   = var.project_id
  cluster_name = var.cluster_name

  depends_on = [module.gke]
}

module "vertex" {
  source = "./modules/vertex"

  project_id    = var.project_id
  region        = var.region
  display_name  = var.vertex_display_name
  model_id      = var.vertex_model_id
  traffic_split = var.vertex_traffic_split
  labels        = var.labels
}

module "namespaces" {
  source = "./modules/namespaces"

  employee_cpu_quota    = var.employee_cpu_quota
  employee_memory_quota = var.employee_memory_quota
  employee_pod_quota    = var.employee_pod_quota

  depends_on = [module.gke]
}
