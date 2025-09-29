terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.0"
}


provider "aws" {
  region = "us-east-1"
}

resource "random_string" "bucket_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "aws_s3_bucket" "immigration_documents" {
  bucket = "immigration-documents-${random_string.bucket_suffix.result}"
  
  tags = {
    Name        = "Immigration Documents"
    Purpose     = "Document Storage"
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket_public_access_block" "immigration_documents_pab" {
  bucket = aws_s3_bucket.immigration_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


output "bucket_name" {
  value = aws_s3_bucket.immigration_documents.id
  description = "The name of the immigration documents S3 bucket"
}

output "bucket_arn" {
  value = aws_s3_bucket.immigration_documents.arn
  description = "The ARN of the immigration documents S3 bucket"
}