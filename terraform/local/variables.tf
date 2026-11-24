variable "cluster_name" {
  description = "Nom du cluster kind"
  type        = string
  default     = "helpdesk"
}

variable "node_image" {
  description = "Image des noeuds Kubernetes (version figée pour la reproductibilité)"
  type        = string
  default     = "kindest/node:v1.35.8"
}

variable "http_port" {
  description = "Port hôte exposé pour le HTTP de l'Ingress"
  type        = number
  default     = 8080
}

variable "https_port" {
  description = "Port hôte exposé pour le HTTPS de l'Ingress"
  type        = number
  default     = 8443
}

variable "registry_port" {
  description = "Port hôte du registre d'images local"
  type        = number
  default     = 5001
}

variable "domain" {
  description = "Domaine résolvant vers 127.0.0.1 (localtest.me) : évite de modifier le fichier hosts"
  type        = string
  default     = "localtest.me"
}

variable "environments" {
  description = "Environnements applicatifs, un namespace chacun (ISO 27001 A.8.31)"
  type = map(object({
    host      = string
    cpu_quota = string
    mem_quota = string
  }))
  default = {
    dev = {
      host      = "helpdesk-dev"
      cpu_quota = "3"
      mem_quota = "3Gi"
    }
    test = {
      host      = "helpdesk-test"
      cpu_quota = "2"
      mem_quota = "2Gi"
    }
    prod = {
      host      = "helpdesk"
      cpu_quota = "4"
      mem_quota = "4Gi"
    }
  }
}

variable "generated_dir" {
  description = "Dossier (ignoré par Git) pour les fichiers générés : config de chiffrement etcd, kubeconfig"
  type        = string
  default     = ".generated"
}
