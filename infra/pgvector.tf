resource "aws_rds_cluster_parameter_group" "pgvector" {
  name   = "pgvector-cluster-params"
  family = "aurora-postgresql16"

  # Optimize for parallel HNSW index builds (pgvector 0.7.0 feature)
  parameter {
    name  = "max_parallel_workers"
    value = var.max_parallel_workers
  }

  parameter {
    name  = "max_parallel_maintenance_workers"
    value = var.max_parallel_workers
  }

  parameter {
    name  = "max_worker_processes"
    value = var.max_parallel_workers + 8
    apply_method = "pending-reboot"
  }

  # Increase work_mem for better vector operations
  parameter {
    name  = "work_mem"
    value = "65536"  # 64MB in KB (reduced for dev)
  }

  # Increase maintenance_work_mem for faster index builds
  parameter {
    name  = "maintenance_work_mem"
    value = "524288"  # 512MB in KB (reduced for dev)
  }

  tags = {
    Name = "pgvector-cluster-parameter-group"
  }
}

# Aurora DB Parameter Group
resource "aws_db_parameter_group" "pgvector" {
  name   = "pgvector-instance-params"
  family = "aurora-postgresql16"

  tags = {
    Name = "pgvector-instance-parameter-group"
  }
}

# Aurora PostgreSQL Serverless v2 Cluster
resource "aws_rds_cluster" "pgvector" {
  cluster_identifier      = "pgvector-aurora-cluster"
  engine                  = "aurora-postgresql"
  engine_mode             = "provisioned"  # Required for Serverless v2
  engine_version          = "16.3"
  database_name           = var.db_name
  master_username         = var.db_username
  master_password         = var.db_password
  
  db_subnet_group_name            = aws_db_subnet_group.main.name
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.pgvector.name
  vpc_security_group_ids          = [aws_security_group.aurora.id]

  storage_encrypted               = true
  backup_retention_period         = 1
  preferred_backup_window         = "03:00-04:00"
  preferred_maintenance_window    = "mon:04:00-mon:05:00"
  
  skip_final_snapshot             = true
  final_snapshot_identifier       = "pgvector-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  enabled_cloudwatch_logs_exports = ["postgresql"]

  # Serverless v2 scaling configuration
  serverlessv2_scaling_configuration {
    min_capacity = var.serverless_min_capacity
    max_capacity = var.serverless_max_capacity
  }

  deletion_protection = false

  tags = {
    Name        = "pgvector-aurora-serverless-cluster"
    Environment = "dev"
  }
}

# Aurora PostgreSQL Serverless v2 Instance
resource "aws_rds_cluster_instance" "pgvector_serverless" {
  identifier              = "pgvector-aurora-serverless-instance-1"
  cluster_identifier      = aws_rds_cluster.pgvector.id
  instance_class          = "db.serverless" 
  engine                  = aws_rds_cluster.pgvector.engine
  engine_version          = aws_rds_cluster.pgvector.engine_version
  db_parameter_group_name = aws_db_parameter_group.pgvector.name

  publicly_accessible     = false
  auto_minor_version_upgrade = null

  performance_insights_enabled = false
  performance_insights_retention_period = null

  monitoring_interval = 0

  tags = {
    Name        = "pgvector-aurora-serverless-instance"
    Environment = "dev"
  }
}