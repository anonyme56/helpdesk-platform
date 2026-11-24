# ---------------------------------------------------------------- base de données PostgreSQL managée
resource "aws_security_group" "db" {
  name_prefix = "${var.name}-${var.environment}-db-"
  vpc_id      = module.vpc.vpc_id
  description = "PostgreSQL : accessible uniquement depuis les noeuds Kubernetes"

  ingress {
    description     = "PostgreSQL depuis les noeuds EKS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.name}-${var.environment}"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 100 # croissance automatique plutôt que surdimensionnement initial
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.data.arn

  db_name  = "helpdesk"
  username = "helpdesk"
  # mot de passe généré et stocké par AWS dans Secrets Manager : absent du code et de l'état Terraform
  manage_master_user_password = true

  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period   = 7 # sauvegardes automatiques + restauration à un instant donné (A.8.13)
  backup_window             = "02:00-03:00"
  copy_tags_to_snapshot     = true
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name}-${var.environment}-final"

  performance_insights_enabled        = true
  performance_insights_kms_key_id     = aws_kms_key.data.arn
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]
  auto_minor_version_upgrade          = true
  iam_database_authentication_enabled = true
}

# ---------------------------------------------------------------- stockage objet
locals {
  buckets = toset(["attachments", "exports", "backups"])
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  # le nom inclut le compte : unique au niveau mondial
  bucket = "${var.name}-${var.environment}-${each.key}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = local.buckets
  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true # réduit les appels KMS, donc le coût
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

# Cycle de vie : stockage froid puis suppression (FinOps + minimisation des données conservées)
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id

  rule {
    id     = "tiering-et-expiration"
    status = "Enabled"
    filter {}

    transition {
      days          = each.key == "backups" ? 30 : 90
      storage_class = each.key == "backups" ? "GLACIER_IR" : "STANDARD_IA"
    }
    expiration {
      days = each.key == "exports" ? 30 : 365
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Refuse tout accès non chiffré en transit (HTTP)
data "aws_iam_policy_document" "tls_only" {
  for_each = local.buckets
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this[each.key].arn, "${aws_s3_bucket.this[each.key].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.this[each.key].id
  policy   = data.aws_iam_policy_document.tls_only[each.key].json
}

# ---------------------------------------------------------------- IAM : moindre privilège (A.5.15, A.8.2)
data "aws_iam_policy_document" "app" {
  statement {
    sid       = "ObjectsRW"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = [for b in ["attachments", "exports"] : "${aws_s3_bucket.this[b].arn}/*"]
  }
  statement {
    sid       = "ListBuckets"
    actions   = ["s3:ListBucket"]
    resources = [for b in ["attachments", "exports"] : aws_s3_bucket.this[b].arn]
  }
  statement {
    sid       = "KmsForS3"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }
}

resource "aws_iam_policy" "app" {
  name   = "${var.name}-${var.environment}-app"
  policy = data.aws_iam_policy_document.app.json
}

# la sauvegarde peut uniquement ÉCRIRE dans le bucket backups
data "aws_iam_policy_document" "backup" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this["backups"].arn}/*"]
  }
  statement {
    actions   = ["kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }
}

resource "aws_iam_policy" "backup" {
  name   = "${var.name}-${var.environment}-backup"
  policy = data.aws_iam_policy_document.backup.json
}

# rôles assumés par les pods via leur ServiceAccount (IRSA) : aucune clé d'accès longue durée
module "irsa_app" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name        = "${var.name}-${var.environment}-app"
  role_policy_arns = { app = aws_iam_policy.app.arn }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["helpdesk-${var.environment}:backend", "helpdesk-${var.environment}:worker"]
    }
  }
}

module "irsa_backup" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name        = "${var.name}-${var.environment}-backup"
  role_policy_arns = { backup = aws_iam_policy.backup.arn }
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["helpdesk-${var.environment}:backup"]
    }
  }
}

# ---------------------------------------------------------------- FinOps : budget créé avec l'infrastructure
resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-${var.environment}-mensuel"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}

# ---------------------------------------------------------------- sorties
output "cluster_name" {
  value = module.eks.cluster_name
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "db_secret_arn" {
  description = "Secret Secrets Manager contenant le mot de passe de la base (généré par AWS)"
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "bucket_names" {
  value = { for k, b in aws_s3_bucket.this : k => b.bucket }
}

output "app_role_arn" {
  value = module.irsa_app.iam_role_arn
}
