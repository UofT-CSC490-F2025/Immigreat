resource "aws_secretsmanager_secret" "pgvector_creds" {
  name        = "pgvector/dev/db-credentials"
  description = "pgvector Aurora PostgreSQL credentials"

  tags = {
    Name        = "pgvector-db-credentials"
    Environment = "dev"
  }
}

resource "aws_secretsmanager_secret_version" "pgvector_creds" {
  secret_id = aws_secretsmanager_secret.pgvector_creds.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_rds_cluster.pgvector.endpoint
    port     = aws_rds_cluster.pgvector.port
    dbname   = var.db_name
    engine   = "postgres"
  })
}