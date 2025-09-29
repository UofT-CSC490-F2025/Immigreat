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

variable "opensearch_instance_type" {
  description = "Instance type for OpenSearch domain"
  type        = string
  default     = "t3.small.search"
}

variable "opensearch_instance_count" {
  description = "Number of instances in the OpenSearch cluster"
  type        = number
  default     = 1
}

variable "opensearch_volume_size" {
  description = "Size of EBS volumes attached to OpenSearch nodes (in GB)"
  type        = number
  default     = 10
}

variable "opensearch_master_user" {
  description = "Master username for OpenSearch"
  type        = string
  default     = "admin"
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