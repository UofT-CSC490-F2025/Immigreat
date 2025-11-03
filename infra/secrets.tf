resource "aws_secretsmanager_secret" "pgvector_creds" {
  name        = "pgvector/${local.environment}/db-credentials"
  description = "pgvector RDS PostgreSQL credentials"
  
  recovery_window_in_days = 0

  tags = {
    Name        = "pgvector-db-credentials-${local.environment}"
    Environment = local.environment
  }
}

resource "aws_secretsmanager_secret_version" "pgvector_creds" {
  secret_id = aws_secretsmanager_secret.pgvector_creds.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_db_instance.pgvector.address
    port     = aws_db_instance.pgvector.port
    dbname   = var.db_name
    engine   = "postgres"
  })
}