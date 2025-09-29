# Archive Lambda code
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
}

# Permission for S3 to invoke Lambda
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sample.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.immigration_documents.arn
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.sample.function_name}"
  retention_in_days = 7
}