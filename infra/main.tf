terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Generate unique names
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

locals {
  project_name = "immigration-rag"
  environment  = "dev"
  
  common_tags = {
    Project     = local.project_name
    Environment = local.environment
    ManagedBy   = "Terraform"
  }
}