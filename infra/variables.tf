variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 120
}

variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "bedrock_embedding_model_id" {
  description = "Bedrock model ID for generating embeddings"
  type        = string
  default     = "amazon.titan-embed-text-v1"
}

variable "bedrock_embedding_dimensions" {
  description = "Dimension of embeddings from the model"
  type        = number
  default     = 1536  # Titan embeddings v1
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "immigrationDocsVectordb"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "serverless_min_capacity" {
  description = "Minimum Aurora Serverless v2 capacity units (ACUs). 1 ACU = 2GB RAM"
  type        = number
  default     = 0.5
}

variable "serverless_max_capacity" {
  description = "Maximum Aurora Serverless v2 capacity units (ACUs). 1 ACU = 2GB RAM"
  type        = number
  default     = 1
}

variable "max_parallel_workers" {
  description = "Maximum parallel workers for HNSW index builds (set to vCPUs - 2)"
  type        = number
  default     = 2  # Conservative default for small instances
}