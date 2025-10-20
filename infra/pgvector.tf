# PostgreSQL Parameter Group (for pgvector tuning)
resource "aws_db_parameter_group" "pgvector" {
  name   = "pgvector-instance-params"
  family = "postgres16" # use postgres16, not aurora-postgresql

  parameter {
    name  = "work_mem"
    value = "65536" # 64MB (for dev)
  }

  parameter {
    name  = "maintenance_work_mem"
    value = "524288" # 512MB (for dev)
  }

  tags = {
    Name = "pgvector-instance-parameter-group"
  }
}

# RDS PostgreSQL Instance (smallest size for testing)
resource "aws_db_instance" "pgvector" {
  identifier              = "pgvector-postgres"
  allocated_storage       = 20
  max_allocated_storage   = 100
  storage_type            = "gp2"

  engine                  = "postgres"
  engine_version          = "16.8"
  instance_class          = "db.t4g.micro"

  username                = var.db_username
  password                = var.db_password
  db_name                 = var.db_name

  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.postgres.id]
  publicly_accessible     = false

  parameter_group_name    = aws_db_parameter_group.pgvector.name

  storage_encrypted       = true
  backup_retention_period = 1
  skip_final_snapshot     = true

  deletion_protection     = false

  tags = {
    Name        = "pgvector-postgres-instance"
    Environment = "dev"
  }
}

output "postgres_endpoint" {
  value = aws_db_instance.pgvector.endpoint
}
