locals {
  # hôtes exposés par l'Ingress, tous sous le domaine localtest.me (-> 127.0.0.1)
  app_hosts      = { for k, v in var.environments : k => "${v.host}.${var.domain}" }
  grafana_host   = "grafana.${var.domain}"
  prom_host      = "prometheus.${var.domain}"
  alertm_host    = "alertmanager.${var.domain}"
  all_hosts      = concat(values(local.app_hosts), [local.grafana_host, local.prom_host, local.alertm_host])
  tls_namespaces = toset(concat([for k, v in var.environments : "helpdesk-${k}"], ["monitoring"]))
}

# ---------------------------------------------------------------- namespaces (A.8.31 : séparation des environnements)
resource "kubernetes_namespace_v1" "env" {
  for_each = var.environments

  metadata {
    name = "helpdesk-${each.key}"
    labels = {
      "app.kubernetes.io/part-of"          = "helpdesk"
      "environment"                        = each.key
      "pod-security.kubernetes.io/enforce" = "baseline"
      "pod-security.kubernetes.io/warn"    = "restricted"
    }
  }

  depends_on = [kind_cluster.this]
}

resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name   = "monitoring"
    labels = { "pod-security.kubernetes.io/enforce" = "privileged" } # node-exporter a besoin d'accès hôte
  }
  depends_on = [kind_cluster.this]
}

resource "kubernetes_namespace_v1" "ingress" {
  metadata {
    name   = "traefik"
    labels = { "pod-security.kubernetes.io/enforce" = "privileged" } # hostPort requis pour exposer l'Ingress sur kind
  }
  depends_on = [kind_cluster.this]
}

# Garde-fous FinOps/sécurité : un environnement ne peut pas consommer tout le cluster
resource "kubernetes_resource_quota_v1" "env" {
  for_each = var.environments

  metadata {
    name      = "quota"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }
  spec {
    hard = {
      "requests.cpu"    = each.value.cpu_quota
      "requests.memory" = each.value.mem_quota
      "pods"            = "30"
    }
  }
}

# Valeurs par défaut pour les conteneurs qui n'en déclarent pas
resource "kubernetes_limit_range_v1" "env" {
  for_each = var.environments

  metadata {
    name      = "defaults"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }
  spec {
    limit {
      type = "Container"
      default = {
        cpu    = "500m"
        memory = "256Mi"
      }
      default_request = {
        cpu    = "50m"
        memory = "64Mi"
      }
    }
  }
}
