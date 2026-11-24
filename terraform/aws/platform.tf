data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

# ---------------------------------------------------------------- réseau
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.name}-${var.environment}"
  cidr = var.vpc_cidr
  azs  = local.azs

  # sous-réseaux privés pour les noeuds, dédiés pour la base ; publics uniquement pour les load balancers
  private_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets   = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 100 + i)]
  database_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 200 + i)]

  create_database_subnet_group = true
  enable_nat_gateway           = true
  single_nat_gateway           = true # FinOps : une seule NAT au lieu d'une par zone

  # journaux de flux réseau (A.8.15 / A.8.16)
  enable_flow_log                                 = true
  create_flow_log_cloudwatch_log_group            = true
  create_flow_log_cloudwatch_iam_role             = true
  flow_log_cloudwatch_log_group_retention_in_days = 30

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

# ---------------------------------------------------------------- clés de chiffrement (A.8.24)
resource "aws_kms_key" "data" {
  description             = "${var.name} ${var.environment} - données (RDS, S3)"
  enable_key_rotation     = true
  deletion_window_in_days = 14
}

resource "aws_kms_key" "eks" {
  description             = "${var.name} ${var.environment} - secrets Kubernetes (etcd)"
  enable_key_rotation     = true
  deletion_window_in_days = 14
}

# ---------------------------------------------------------------- cluster Kubernetes
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${var.name}-${var.environment}"
  cluster_version = "1.33"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # API Kubernetes : privée par défaut (accès via VPN / bastion). Si l'accès public est activé, il reste
  # limité à une liste blanche de réseaux, jamais 0.0.0.0/0.
  cluster_endpoint_public_access       = var.api_public_access
  cluster_endpoint_public_access_cidrs = var.api_allowed_cidrs
  cluster_endpoint_private_access      = true

  # Secrets Kubernetes chiffrés dans etcd avec notre clé KMS (équivalent du chiffrement etcd du lab)
  cluster_encryption_config = {
    provider_key_arn = aws_kms_key.eks.arn
    resources        = ["secrets"]
  }

  # journaux du plan de contrôle : audit des actions sur le cluster (A.8.15)
  cluster_enabled_log_types              = ["api", "audit", "authenticator"]
  cloudwatch_log_group_retention_in_days = 30

  enable_irsa = true # rôles IAM par ServiceAccount (moindre privilège)

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      capacity_type  = var.node_capacity_type
      min_size       = var.node_min_size
      max_size       = var.node_max_size
      desired_size   = var.node_min_size

      # IMDSv2 obligatoire : empêche le vol de credentials depuis un pod compromis (SSRF)
      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 1
      }
      block_device_mappings = {
        xvda = { device_name = "/dev/xvda", ebs = { volume_size = 30, volume_type = "gp3", encrypted = true } }
      }
    }
  }
}
