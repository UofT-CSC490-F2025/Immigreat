resource "aws_lambda_function" "data_ingestion" {
  function_name = "data_ingestion-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:ingest-latest"

  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory

  architectures = ["arm64"]
  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      PGVECTOR_SECRET_ARN     = aws_secretsmanager_secret.pgvector_creds.arn
      PGVECTOR_DB_HOST        = aws_db_instance.pgvector.address 
      PGVECTOR_DB_NAME        = var.db_name 
      PGVECTOR_DB_PORT        = tostring(aws_db_instance.pgvector.port)

      BEDROCK_EMBEDDING_MODEL  = var.bedrock_embedding_model_id
      EMBEDDING_DIMENSIONS     = var.bedrock_embedding_dimensions
    }
  }
}

resource "aws_lambda_function" "ircc_scraping" {
  function_name = "ircc_scraping-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:scraping-latest"

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory

  architectures = ["arm64"]
  image_config {
    command = ["scraping.scraping_lambda.handler"]
  }

  environment {
    variables = {
      SCRAPE_DEFAULT_OUTPUT = "ircc_scraped_data.json"
      TARGET_S3_BUCKET      = aws_s3_bucket.immigration_documents.id
      TARGET_S3_KEY         = "document/ircc_scraped_data.json"
    }
  }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.immigration_documents.arn
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.data_ingestion.function_name}-${local.environment}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "scraping_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ircc_scraping.function_name}-${local.environment}"
  retention_in_days = 7
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.immigration_documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.data_ingestion.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "document/"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
