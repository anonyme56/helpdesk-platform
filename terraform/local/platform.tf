# Socle de plateforme : ingress, métriques, supervision, logs. Versions des charts figées.

resource "helm_release" "kube_prometheus_stack" {
  name             = "kps"
  namespace        = kubernetes_namespace_v1.monitoring.metadata[0].name
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = "93.3.0"
  timeout          = 900
  create_namespace = false

  values = [yamlencode({
    # sur kind, ces composants ne sont pas scrapables : on évite des alertes permanentes sans intérêt
    kubeEtcd              = { enabled = false }
    kubeControllerManager = { enabled = false }
    kubeScheduler         = { enabled = false }
    kubeProxy             = { enabled = false }
    defaultRules = {
      rules = { etcd = false, kubeControllerManager = false, kubeSchedulerAlerting = false, kubeProxy = false }
    }

    prometheus = {
      prometheusSpec = {
        retention = "3d"
        # on prend en compte les ServiceMonitor / PrometheusRule de tous les namespaces
        serviceMonitorSelectorNilUsesHelmValues = false
        podMonitorSelectorNilUsesHelmValues     = false
        ruleSelectorNilUsesHelmValues           = false
        resources = {
          requests = { cpu = "100m", memory = "400Mi" }
          limits   = { memory = "900Mi" }
        }
      }
      ingress = {
        enabled          = true
        ingressClassName = "traefik"
        hosts            = [local.prom_host]
        tls              = [{ secretName = "helpdesk-tls", hosts = [local.prom_host] }]
      }
    }

    alertmanager = {
      alertmanagerSpec = {
        resources = { requests = { cpu = "10m", memory = "32Mi" }, limits = { memory = "128Mi" } }
      }
      ingress = {
        enabled          = true
        ingressClassName = "traefik"
        hosts            = [local.alertm_host]
        tls              = [{ secretName = "helpdesk-tls", hosts = [local.alertm_host] }]
      }
    }

    grafana = {
      adminPassword = random_password.grafana_admin.result
      resources     = { requests = { cpu = "50m", memory = "256Mi" }, limits = { memory = "768Mi" } }
      ingress = {
        enabled          = true
        ingressClassName = "traefik"
        hosts            = [local.grafana_host]
        tls              = [{ secretName = "helpdesk-tls", hosts = [local.grafana_host] }]
      }
      sidecar = {
        dashboards = { enabled = true, label = "grafana_dashboard", searchNamespace = "ALL" }
      }
      additionalDataSources = [{
        name      = "Loki"
        type      = "loki"
        uid       = "loki"
        url       = "http://loki.monitoring.svc.cluster.local:3100"
        access    = "proxy"
        isDefault = false
      }]
    }

    prometheusOperator = {
      resources = { requests = { cpu = "20m", memory = "64Mi" }, limits = { memory = "200Mi" } }
    }
    kube-state-metrics = {
      resources = { requests = { cpu = "10m", memory = "32Mi" }, limits = { memory = "128Mi" } }
    }
    prometheus-node-exporter = {
      resources = { requests = { cpu = "10m", memory = "16Mi" }, limits = { memory = "64Mi" } }
    }
  })]

  depends_on = [kubernetes_secret_v1.tls]
}

resource "helm_release" "traefik" {
  name       = "traefik"
  namespace  = kubernetes_namespace_v1.ingress.metadata[0].name
  repository = "https://traefik.github.io/charts"
  chart      = "traefik"
  version    = "42.4.0"
  timeout    = 600

  values = [yamlencode({
    deployment = { replicas = 1 }
    # hostPort sur un seul noeud : l'ancien pod doit s'arrêter avant que le nouveau démarre
    updateStrategy = { type = "RollingUpdate", rollingUpdate = { maxUnavailable = 1, maxSurge = 0 } }
    ingressClass   = { enabled = true, isDefaultClass = true }
    service        = { spec = { type = "ClusterIP" } }
    # sur kind, l'Ingress est joignable via des hostPort du noeud (mappés sur 8080/8443 côté machine)
    ports = {
      web = {
        hostPort = 80
        http     = { redirections = { entryPoint = { to = "websecure", scheme = "https", permanent = true } } }
      }
      websecure = { hostPort = 443, exposedPort = 8443 } # port vu de la machine hôte (redirection HTTP->HTTPS)
    }
    nodeSelector = { "ingress-ready" = "true" }
    tolerations  = [{ key = "node-role.kubernetes.io/control-plane", operator = "Exists", effect = "NoSchedule" }]
    log          = { level = "INFO", format = "json" }
    accessLog    = { enabled = true, format = "json" }
    metrics = {
      prometheus = { serviceMonitor = { enabled = true } }
    }
    resources = {
      requests = { cpu = "50m", memory = "64Mi" }
      limits   = { memory = "200Mi" }
    }
  })]

  depends_on = [helm_release.kube_prometheus_stack]
}

resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  namespace  = "kube-system"
  repository = "https://kubernetes-sigs.github.io/metrics-server"
  chart      = "metrics-server"
  version    = "3.14.0"

  values = [yamlencode({
    # certificats kubelet auto-signés sur kind
    args      = ["--kubelet-insecure-tls"]
    resources = { requests = { cpu = "20m", memory = "40Mi" }, limits = { memory = "100Mi" } }
  })]

  depends_on = [kind_cluster.this]
}

resource "helm_release" "loki" {
  name       = "loki"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki"
  version    = "7.6.0"
  timeout    = 600

  values = [yamlencode({
    deploymentMode = "SingleBinary"
    loki = {
      auth_enabled = false
      commonConfig = { replication_factor = 1 }
      storage      = { type = "filesystem" }
      schemaConfig = {
        configs = [{
          from         = "2024-04-01"
          store        = "tsdb"
          object_store = "filesystem"
          schema       = "v13"
          index        = { prefix = "loki_index_", period = "24h" }
        }]
      }
      limits_config = { retention_period = "72h" }
      compactor     = { retention_enabled = true, delete_request_store = "filesystem" }
    }
    singleBinary = {
      replicas    = 1
      persistence = { enabled = true, size = "2Gi" }
      resources   = { requests = { cpu = "50m", memory = "200Mi" }, limits = { memory = "500Mi" } }
    }
    backend      = { replicas = 0 }
    read         = { replicas = 0 }
    write        = { replicas = 0 }
    chunksCache  = { enabled = false }
    resultsCache = { enabled = false }
    gateway      = { enabled = false }
    lokiCanary   = { enabled = false }
    test         = { enabled = false }
    minio        = { enabled = false }
  })]

  depends_on = [kubernetes_namespace_v1.monitoring]
}

# Collecte des logs de tous les pods (lecture via l'API Kubernetes) puis envoi vers Loki
resource "helm_release" "alloy" {
  name       = "alloy"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name
  repository = "https://grafana.github.io/helm-charts"
  chart      = "alloy"
  version    = "1.16.0"

  values = [yamlencode({
    controller = { type = "deployment", replicas = 1 }
    alloy = {
      resources = { requests = { cpu = "30m", memory = "100Mi" }, limits = { memory = "300Mi" } }
      configMap = {
        content = <<-EOT
          discovery.kubernetes "pods" {
            role = "pod"
          }

          discovery.relabel "pods" {
            targets = discovery.kubernetes.pods.targets
            rule {
              source_labels = ["__meta_kubernetes_namespace"]
              target_label  = "namespace"
            }
            rule {
              source_labels = ["__meta_kubernetes_pod_name"]
              target_label  = "pod"
            }
            rule {
              source_labels = ["__meta_kubernetes_pod_container_name"]
              target_label  = "container"
            }
            rule {
              source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_name"]
              target_label  = "app"
            }
          }

          loki.source.kubernetes "pods" {
            targets    = discovery.relabel.pods.output
            forward_to = [loki.write.default.receiver]
          }

          loki.write "default" {
            endpoint {
              url = "http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push"
            }
          }
        EOT
      }
    }
  })]

  depends_on = [helm_release.loki]
}

# Tableau de bord Grafana : chargé automatiquement par le sidecar (label grafana_dashboard)
resource "kubernetes_config_map_v1" "dashboard_helpdesk" {
  metadata {
    name      = "dashboard-helpdesk"
    namespace = kubernetes_namespace_v1.monitoring.metadata[0].name
    labels    = { grafana_dashboard = "1" }
  }
  data = {
    "helpdesk-dashboard.json" = file("${path.module}/../../monitoring/helpdesk-dashboard.json")
  }
  depends_on = [helm_release.kube_prometheus_stack]
}
