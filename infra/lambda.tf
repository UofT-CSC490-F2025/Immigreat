resource "aws_lambda_function" "data_ingestion" {
  function_name = "data_ingestion-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:latest"

  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory

  architectures = ["arm64"]

  image_config {
    command = ["data_ingestion.handler"]
  }
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
    command = ["scraping.ircc_scraping_lambda.handler"]
  }

  environment {
    variables = {
      SCRAPE_DEFAULT_OUTPUT = "ircc_scraped_data.json"
      TARGET_S3_BUCKET      = aws_s3_bucket.immigration_documents.id
      TARGET_S3_KEY         = "document/ircc_scraped_data.json"
    }
  }
}

# Add these resources after the existing aws_lambda_function.ircc_scraping resource

resource "aws_lambda_function" "irpr_irpa_scraping" {
  function_name = "irpr_irpa_scraping-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:scraping-latest"

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory

  architectures = ["arm64"]
  image_config {
    command = ["scraping.irpr_irpa_scraping_lambda.handler"]
  }

  environment {
    variables = {
      SCRAPE_DEFAULT_OUTPUT = "irpr_irpa_data.json"
      TARGET_S3_BUCKET      = aws_s3_bucket.immigration_documents.id
      TARGET_S3_KEY         = "document/irpr_irpa_data.json"
    }
  }
}

resource "aws_lambda_function" "refugee_law_lab_scraping" {
  function_name = "refugee_law_lab_scraping-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:scraping-latest"

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory

  architectures = ["arm64"]
  image_config {
    command = ["scraping.refugee_law_scraping_lambda.handler"]
  }

  environment {
    variables = {
      SCRAPE_DEFAULT_OUTPUT = "refugeelawlab_data_en.json"
      TARGET_S3_BUCKET      = aws_s3_bucket.immigration_documents.id
      TARGET_S3_KEY         = "document/refugeelawlab_data_en.json"
    }
  }
}

resource "aws_lambda_function" "forms_scraping" {
  function_name = "forms_scraping-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:scraping-latest"

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory

  architectures = ["arm64"]
  image_config {
    command = ["scraping.forms_scraping_lambda.handler"]
  }

  environment {
    variables = {
      SCRAPE_DEFAULT_OUTPUT = "forms_scraped_data.json"
      TARGET_S3_BUCKET      = aws_s3_bucket.immigration_documents.id
      TARGET_S3_KEY         = "document/forms_scraped_data.json"
    }
  }
}

resource "aws_lambda_function" "rag_pipeline" {
  function_name = "rag_pipeline-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:latest"

  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory

  architectures = ["arm64"]

  image_config {
    command = ["model.rag_pipeline.handler"]
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      PGVECTOR_SECRET_ARN      = aws_secretsmanager_secret.pgvector_creds.arn
      PGVECTOR_DB_HOST         = aws_db_instance.pgvector.address 
      PGVECTOR_DB_NAME         = var.db_name 
      PGVECTOR_DB_PORT         = tostring(aws_db_instance.pgvector.port)

      BEDROCK_EMBEDDING_MODEL  = var.bedrock_embedding_model_id
      EMBEDDING_DIMENSIONS     = var.bedrock_embedding_dimensions
      BEDROCK_CHAT_MODEL       = var.bedrock_chat_model_id
      RERANK_MODEL             = var.bedrock_rerank_model_id
      
      # RAG pipeline configuration
      ANTHROPIC_VERSION        = "bedrock-2023-05-31"
      CONTEXT_MAX_CHUNKS       = "12"
      FE_RAG_FACETS            = "source,title,section"
      FE_RAG_MAX_FACET_VALUES  = "2"
      FE_RAG_EXTRA_LIMIT       = "5"
      RERANK_API_VERSION       = "2"
    }
  }
}

# Public HTTPS endpoint for rag_pipeline (simple alternative to API Gateway)
resource "aws_lambda_function_url" "rag_pipeline_url" {
  function_name      = aws_lambda_function.rag_pipeline.function_name
  authorization_type = "NONE"  # open for testing; tighten later if needed
  cors {
    allow_origins = ["*"]
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
    max_age       = 3600
  }
}

# Explicitly allow unauthenticated public invocations via Function URL
resource "aws_lambda_permission" "rag_pipeline_function_url_public" {
  statement_id             = "AllowPublicFunctionUrlInvoke"
  action                   = "lambda:InvokeFunctionUrl"
  function_name            = aws_lambda_function.rag_pipeline.function_name
  principal                = "*"
  function_url_auth_type   = "NONE"
}

# Lightweight DB admin/query lambda (list tables, describe table)
resource "aws_lambda_function" "db_admin" {
  function_name = "db-admin-function-${local.environment}"
  role          = aws_iam_role.lambda_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:latest"

  timeout     = 60
  memory_size = 256

  architectures = ["arm64"]

  image_config {
    command = ["model.db_admin_lambda.handler"]
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      PGVECTOR_SECRET_ARN = aws_secretsmanager_secret.pgvector_creds.arn
      PGVECTOR_DB_HOST    = aws_db_instance.pgvector.address
      PGVECTOR_DB_NAME    = var.db_name
      PGVECTOR_DB_PORT    = tostring(aws_db_instance.pgvector.port)
    }
  }
}

resource "aws_cloudwatch_log_group" "db_admin_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.db_admin.function_name}"
  retention_in_days = 7
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.immigration_documents.arn
}

resource "aws_cloudwatch_log_group" "rag_pipeline_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.rag_pipeline.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.data_ingestion.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "scraping_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ircc_scraping.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "irpr_irpa_scraping_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.irpr_irpa_scraping.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "refugee_law_lab_scraping_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.refugee_law_lab_scraping.function_name}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "forms_scraping_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.forms_scraping.function_name}"
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
