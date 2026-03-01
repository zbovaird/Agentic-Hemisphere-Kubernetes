output "owner_namespace" {
  description = "Owner namespace name"
  value       = kubernetes_namespace.owner.metadata[0].name
}

output "manager_namespace" {
  description = "Manager namespace name"
  value       = kubernetes_namespace.manager.metadata[0].name
}

output "employee_namespace" {
  description = "Employee namespace name"
  value       = kubernetes_namespace.employee.metadata[0].name
}
