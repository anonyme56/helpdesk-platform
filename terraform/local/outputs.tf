output "kubeconfig_context" {
  value = "kind-${var.cluster_name}"
}

output "app_urls" {
  value = { for k, h in local.app_hosts : k => "https://${h}:${var.https_port}" }
}

output "grafana_url" {
  value = "https://${local.grafana_host}:${var.https_port}"
}

output "prometheus_url" {
  value = "https://${local.prom_host}:${var.https_port}"
}

output "alertmanager_url" {
  value = "https://${local.alertm_host}:${var.https_port}"
}

output "registry" {
  value = "localhost:${var.registry_port}"
}

output "grafana_admin_password" {
  value     = random_password.grafana_admin.result
  sensitive = true
}

output "app_admin_passwords" {
  value     = { for k, p in random_password.admin : k => p.result }
  sensitive = true
}

output "ca_certificate_file" {
  value = local_file.ca_cert.filename
}
