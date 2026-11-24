# Secrets générés par Terraform : jamais écrits dans Git, un jeu distinct par environnement.
# Ils vivent dans l'état Terraform (à protéger : backend chiffré en vrai projet) et dans etcd (chiffré, cf. cluster.tf).

resource "random_password" "db" {
  for_each = var.environments
  length   = 28
  special  = false
}

resource "random_password" "redis" {
  for_each = var.environments
  length   = 28
  special  = false
}

resource "random_password" "s3_access" {
  for_each = var.environments
  length   = 16
  special  = false
  upper    = true
}

resource "random_password" "s3_secret" {
  for_each = var.environments
  length   = 36
  special  = false
}

resource "random_password" "jwt" {
  for_each = var.environments
  length   = 64
  special  = false
}

resource "random_password" "admin" {
  for_each = var.environments
  length   = 20
  special  = false
}

resource "random_bytes" "file_key" {
  for_each = var.environments
  length   = 32
}

resource "random_password" "backup" {
  for_each = var.environments
  length   = 40
  special  = false
}

resource "random_password" "grafana_admin" {
  length  = 20
  special = false
}

resource "kubernetes_secret_v1" "app" {
  for_each = var.environments

  metadata {
    name      = "helpdesk-secrets"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }
  data = {
    "db-password"       = random_password.db[each.key].result
    "redis-password"    = random_password.redis[each.key].result
    "s3-access-key"     = random_password.s3_access[each.key].result
    "s3-secret-key"     = random_password.s3_secret[each.key].result
    "jwt-secret"        = random_password.jwt[each.key].result
    "admin-password"    = random_password.admin[each.key].result
    "backup-passphrase" = random_password.backup[each.key].result
    # clé Fernet = 32 octets en base64 "url-safe"
    "file-encryption-key" = replace(replace(random_bytes.file_key[each.key].base64, "+", "-"), "/", "_")
  }
}

# Configuration d'identités du stockage objet (SeaweedFS lit ce JSON au démarrage)
resource "kubernetes_secret_v1" "s3_config" {
  for_each = var.environments

  metadata {
    name      = "s3-config"
    namespace = kubernetes_namespace_v1.env[each.key].metadata[0].name
  }
  data = {
    "s3.json" = jsonencode({
      identities = [{
        name        = "app"
        credentials = [{ accessKey = random_password.s3_access[each.key].result, secretKey = random_password.s3_secret[each.key].result }]
        actions     = ["Admin", "Read", "Write", "List", "Tagging"]
      }]
    })
  }
}

# ---------------------------------------------------------------- TLS (chiffrement en transit, A.8.24)
# En local : autorité interne + certificat serveur. En production on utiliserait cert-manager + Let's Encrypt.
resource "tls_private_key" "ca" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_self_signed_cert" "ca" {
  private_key_pem       = tls_private_key.ca.private_key_pem
  is_ca_certificate     = true
  validity_period_hours = 8760
  allowed_uses          = ["cert_signing", "crl_signing"]
  subject {
    common_name  = "Helpdesk Lab CA"
    organization = "Projet BC3"
  }
}

resource "tls_private_key" "server" {
  algorithm   = "ECDSA"
  ecdsa_curve = "P256"
}

resource "tls_cert_request" "server" {
  private_key_pem = tls_private_key.server.private_key_pem
  dns_names       = local.all_hosts
  subject {
    common_name  = "helpdesk.${var.domain}"
    organization = "Projet BC3"
  }
}

resource "tls_locally_signed_cert" "server" {
  cert_request_pem      = tls_cert_request.server.cert_request_pem
  ca_private_key_pem    = tls_private_key.ca.private_key_pem
  ca_cert_pem           = tls_self_signed_cert.ca.cert_pem
  validity_period_hours = 4380
  allowed_uses          = ["digital_signature", "key_encipherment", "server_auth"]
}

resource "kubernetes_secret_v1" "tls" {
  for_each = local.tls_namespaces
  type     = "kubernetes.io/tls"

  metadata {
    name      = "helpdesk-tls"
    namespace = each.key
  }
  data = {
    "tls.crt" = "${tls_locally_signed_cert.server.cert_pem}${tls_self_signed_cert.ca.cert_pem}"
    "tls.key" = tls_private_key.server.private_key_pem
  }

  depends_on = [kubernetes_namespace_v1.env, kubernetes_namespace_v1.monitoring]
}

resource "local_file" "ca_cert" {
  filename = "${local.gen_dir}/ca.crt"
  content  = tls_self_signed_cert.ca.cert_pem
}
