resource "null_resource" "build_lambda" {
  triggers = {
    requirements = filemd5("${path.module}/../src/lambda/requirements.txt")
    code         = filemd5("${path.module}/../src/lambda/sample.py")
  }

  provisioner "local-exec" {
    command = "chmod +x ${path.module}/build_lambda.sh && ${path.module}/build_lambda.sh ${abspath(path.module)}/../src/lambda ${abspath(path.module)}/../build/lambda"
  }
}


data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../build/lambda"
  output_path = "${path.module}/../build/sample.zip"
  
  depends_on = [null_resource.build_lambda]
}

resource "aws_lambda_function" "sample" {
  function_name    = "sample-function"
  role            = aws_iam_role.lambda_role.arn
  handler         = "sample.handler"
  runtime         = "python3.11"
  
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory

  vpc_config {
    subnet_ids         = [aws_subnet.private_2.id]
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

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sample.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.immigration_documents.arn
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.sample.function_name}"
  retention_in_days = 7
}