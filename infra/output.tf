output "db_endpoint" {
  description = "RDS PostgreSQL endpoint (read/write)"
  value       = aws_db_instance.pgvector.address
}

output "db_identifier" {
  description = "RDS PostgreSQL instance identifier"
  value       = aws_db_instance.pgvector.id
}

output "database_name" {
  description = "Database name"
  value       = var.db_name
}

output "port" {
  description = "Database port"
  value       = aws_db_instance.pgvector.port
}

output "connection_string" {
  description = "PostgreSQL connection string (without password)"
  value       = "postgresql://${var.db_username}:PASSWORD@${aws_db_instance.pgvector.address}:${aws_db_instance.pgvector.port}/${var.db_name}"
  sensitive   = true
}

output "psql_command" {
  description = "psql command to connect to the database"
  value       = "PGPASSWORD='your-password' psql -h ${aws_db_instance.pgvector.address} -U ${var.db_username} -d ${var.db_name}"
  sensitive   = true
}

output "security_group_id" {
  description = "Security group ID for PostgreSQL instance"
  value       = aws_security_group.postgres.id
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret containing database credentials"
  value       = aws_secretsmanager_secret.pgvector_creds.arn
}

output "rag_pipeline_function_url" {
  description = "Public HTTPS URL for rag_pipeline Lambda (Function URL)"
  value       = aws_lambda_function_url.rag_pipeline_url.function_url
}
