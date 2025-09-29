data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../src/lambda/sample.py"
  output_path = "${path.module}/../src/lambda/sample.zip"
}

resource "aws_lambda_function" "sample" {
  function_name    = "sample-function"
  role            = aws_iam_role.lambda_role.arn
  handler         = "sample.handler"  # sample.py with handler() function
  runtime         = "python3.11"
  
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      OPENSEARCH_ENDPOINT = aws_opensearch_domain.immigration_docs.endpoint
      OPENSEARCH_SECRET   = aws_secretsmanager_secret.opensearch_creds.name
      OPENSEARCH_INDEX    = "immigration-documents"
      BEDROCK_EMBEDDING_MODEL  = var.bedrock_embedding_model_id
      EMBEDDING_DIMENSIONS     = var.bedrock_embedding_dimensions
      AWS_REGION              = var.aws_region
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