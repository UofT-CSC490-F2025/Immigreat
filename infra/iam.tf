resource "aws_security_group" "lambda" {
  name        = "data_ingestion-lambda-sg"
  description = "Security group for Lambda function accessing pgvector"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name        = "data_ingestion-lambda-sg"
    Environment = "dev"
  }
}


resource "aws_security_group_rule" "allow_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.postgres.id
  source_security_group_id = aws_security_group.lambda.id
  description              = "Allow Lambda to access PostgreSQL"
}


resource "aws_iam_role" "lambda_role" {
  name = "data_ingestion-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "data_ingestion-lambda-role"
    Environment = "dev"
  }
}
resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Lambda policy
resource "aws_iam_role_policy" "lambda_policy" {
  name = "data_ingestion-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # S3 - Read documents
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.immigration_documents.arn}/*"
      },
      # Secrets Manager - Read pgvector database credentials
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.pgvector_creds.arn
        ]
      },
      # Bedrock - Invoke embedding models
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v1",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
        ]
      },
      # VPC - Required for Lambda to access Aurora in VPC
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses"
        ]
        Resource = "*"
      }
    ]
  })
}
