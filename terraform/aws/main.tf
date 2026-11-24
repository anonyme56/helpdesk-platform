terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95"
    }
  }

  # En vrai projet : état distant chiffré + verrou (S3 + DynamoDB), jamais un tfstate local ni dans Git.
  # backend "s3" {
  #   bucket         = "helpdesk-tfstate-<compte>"
  #   key            = "helpdesk/terraform.tfstate"
  #   region         = "eu-west-3"
  #   encrypt        = true
  #   dynamodb_table = "helpdesk-tfstate-lock"
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project     = "helpdesk"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}

variable "region" {
  description = "Région AWS (Paris : données hébergées en France, cf. RGPD)"
  type        = string
  default     = "eu-west-3"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "name" {
  type    = string
  default = "helpdesk"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "node_instance_types" {
  description = "Types d'instances des noeuds Kubernetes"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_capacity_type" {
  description = "ON_DEMAND ou SPOT (SPOT : environ -60 % sur le compute, acceptable pour dev/test)"
  type        = string
  default     = "ON_DEMAND"
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 4
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_multi_az" {
  description = "Haute disponibilité de la base (double le coût de l'instance)"
  type        = bool
  default     = false
}

variable "monthly_budget_usd" {
  description = "Budget mensuel : alerte à 80 % (réel) et 100 % (prévu)"
  type        = number
  default     = 250
}

variable "budget_alert_email" {
  type    = string
  default = "finops@example.com"
}

variable "api_public_access" {
  description = "Expose l'API Kubernetes sur Internet (liste blanche api_allowed_cidrs). false = privée uniquement."
  type        = bool
  default     = false
}

variable "api_allowed_cidrs" {
  description = "Réseaux autorisés à joindre l'API du cluster (jamais 0.0.0.0/0 en production)"
  type        = list(string)
  default     = ["203.0.113.0/24"]
}
