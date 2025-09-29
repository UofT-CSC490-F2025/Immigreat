resource "aws_opensearch_domain" "immigration_docs" {
  domain_name    = "${local.project_name}-${random_string.suffix.result}"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type  = var.opensearch_instance_type
    instance_count = var.opensearch_instance_count
    
    # Dedicated master nodes (only for production)
    dedicated_master_enabled = false
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.opensearch_volume_size
  }


  # Domain endpoint options
  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  # Fine-grained access control
  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true
    
    master_user_options {
      master_user_name     = var.opensearch_master_user
      master_user_password = random_password.opensearch_password.result
    }
  }

  # Access policy
  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "*" }
      Action    = "es:*"
      Resource  = "arn:aws:es:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:domain/${local.project_name}-${random_string.suffix.result}/*"
    }]
  })

  tags = merge(local.common_tags, {
    Name = "Immigration Docs OpenSearch"
  })
}

# Generate random password for OpenSearch
resource "random_password" "opensearch_password" {
  length  = 16
  special = true
  
  # Ensure password meets OpenSearch requirements
  min_lower   = 1
  min_upper   = 1
  min_numeric = 1
  min_special = 1
}

# Store OpenSearch credentials in AWS Secrets Manager
resource "aws_secretsmanager_secret" "opensearch_creds" {
  name = "${local.project_name}-opensearch-creds-${random_string.suffix.result}"
  
  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "opensearch_creds" {
  secret_id = aws_secretsmanager_secret.opensearch_creds.id
  
  secret_string = jsonencode({
    endpoint = aws_opensearch_domain.immigration_docs.endpoint
    username = var.opensearch_master_user
    password = random_password.opensearch_password.result
  })
}

# Data sources
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}