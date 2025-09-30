output "cluster_endpoint" {
  description = "Aurora cluster endpoint (read/write)"
  value       = aws_rds_cluster.pgvector.endpoint
}

output "reader_endpoint" {
  description = "Aurora cluster reader endpoint (read-only)"
  value       = aws_rds_cluster.pgvector.reader_endpoint
}

output "cluster_identifier" {
  description = "Aurora cluster identifier"
  value       = aws_rds_cluster.pgvector.cluster_identifier
}

output "database_name" {
  description = "Database name"
  value       = aws_rds_cluster.pgvector.database_name
}

output "port" {
  description = "Database port"
  value       = aws_rds_cluster.pgvector.port
}

output "connection_string" {
  description = "PostgreSQL connection string (without password)"
  value       = "postgresql://${var.db_username}:PASSWORD@${aws_rds_cluster.pgvector.endpoint}:${aws_rds_cluster.pgvector.port}/${var.db_name}"
  sensitive   = true
}

output "psql_command" {
  description = "psql command to connect to the database"
  value       = "PGPASSWORD='your-password' psql -h ${aws_rds_cluster.pgvector.endpoint} -U ${var.db_username} -d ${var.db_name}"
  sensitive   = true
}

output "security_group_id" {
  description = "Security group ID for Aurora cluster"
  value       = aws_security_group.aurora.id
}

output "db_secret_arn" {
  description = "ARN of the Secrets Manager secret containing database credentials"
  value       = aws_secretsmanager_secret.pgvector_creds.arn
}