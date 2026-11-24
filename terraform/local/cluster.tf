# Cluster Kubernetes local (kind) + registre d'images + chiffrement des Secrets dans etcd.
# Équivalent local d'un cluster managé (EKS/AKS/GKE) : voir ../aws pour la cible cloud.

locals {
  gen_dir = abspath("${path.module}/${var.generated_dir}")
}

# ---------------------------------------------------------------- chiffrement des Secrets au repos (A.8.24)
resource "random_bytes" "etcd_key" {
  length = 32
}

resource "local_sensitive_file" "etcd_encryption" {
  filename        = "${local.gen_dir}/enc/enc.yaml"
  file_permission = "0600"
  content         = <<-EOT
    apiVersion: apiserver.config.k8s.io/v1
    kind: EncryptionConfiguration
    resources:
      - resources: ["secrets"]
        providers:
          - aescbc:
              keys:
                - name: key1
                  secret: ${random_bytes.etcd_key.base64}
          - identity: {}
  EOT
}

# ---------------------------------------------------------------- registre d'images local
resource "docker_image" "registry" {
  name         = "registry:2"
  keep_locally = true
}

resource "docker_container" "registry" {
  name    = "kind-registry"
  image   = docker_image.registry.image_id
  restart = "always"

  ports {
    internal = 5000
    external = var.registry_port
    ip       = "127.0.0.1"
  }

  # le réseau "kind" est créé avec le cluster : on s'y rattache pour que les noeuds joignent le registre
  networks_advanced {
    name = "kind"
  }

  depends_on = [kind_cluster.this]
}

# ---------------------------------------------------------------- cluster
resource "kind_cluster" "this" {
  name           = var.cluster_name
  node_image     = var.node_image
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    containerd_config_patches = [
      <<-EOT
      [plugins."io.containerd.cri.v1.images".registry]
        config_path = "/etc/containerd/certs.d"
      EOT
    ]

    node {
      role = "control-plane"

      kubeadm_config_patches = [
        <<-EOT
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
        EOT
        ,
        <<-EOT
        kind: ClusterConfiguration
        apiServer:
          extraArgs:
            encryption-provider-config: /etc/kubernetes/enc/enc.yaml
          extraVolumes:
            - name: enc
              hostPath: /etc/kubernetes/enc
              mountPath: /etc/kubernetes/enc
              readOnly: true
              pathType: DirectoryOrCreate
        EOT
      ]

      extra_mounts {
        host_path      = "${local.gen_dir}/enc"
        container_path = "/etc/kubernetes/enc"
      }

      extra_port_mappings {
        container_port = 80
        host_port      = var.http_port
        listen_address = "127.0.0.1"
      }
      extra_port_mappings {
        container_port = 443
        host_port      = var.https_port
        listen_address = "127.0.0.1"
      }
    }
  }

  depends_on = [local_sensitive_file.etcd_encryption]
}

# Dit à containerd (sur le noeud) que "localhost:<port>" est servi en HTTP par le conteneur kind-registry.
resource "terraform_data" "registry_mirror" {
  triggers_replace = [kind_cluster.this.id, docker_container.registry.id]

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -e
      NODE="${var.cluster_name}-control-plane"
      DIR="/etc/containerd/certs.d/localhost:${var.registry_port}"
      docker exec "$NODE" mkdir -p "$DIR"
      printf '[host."http://kind-registry:5000"]\n' | docker exec -i "$NODE" sh -c "cat > $DIR/hosts.toml"
    EOT
    environment = {
      MSYS_NO_PATHCONV = "1"
    }
  }
}
