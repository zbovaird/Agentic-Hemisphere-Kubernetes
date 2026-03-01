resource "kubernetes_namespace" "owner" {
  metadata {
    name = var.owner_namespace
    labels = {
      role                                         = "owner"
      "pod-security.kubernetes.io/enforce"         = "baseline"
      "pod-security.kubernetes.io/enforce-version" = "latest"
    }
  }
}

resource "kubernetes_namespace" "manager" {
  metadata {
    name = var.manager_namespace
    labels = {
      role                                         = "manager"
      "pod-security.kubernetes.io/enforce"         = "baseline"
      "pod-security.kubernetes.io/enforce-version" = "latest"
    }
  }
}

resource "kubernetes_namespace" "employee" {
  metadata {
    name = var.employee_namespace
    labels = {
      role                                         = "employee"
      "pod-security.kubernetes.io/enforce"         = "restricted"
      "pod-security.kubernetes.io/enforce-version" = "latest"
    }
  }
}

resource "kubernetes_resource_quota" "employee_quota" {
  metadata {
    name      = "employee-quota"
    namespace = kubernetes_namespace.employee.metadata[0].name
  }

  spec {
    hard = {
      "limits.cpu"    = var.employee_cpu_quota
      "limits.memory" = var.employee_memory_quota
      pods            = var.employee_pod_quota
    }
  }
}
