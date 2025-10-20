resource "aws_s3_bucket" "immigration_documents" {
  bucket = "${local.project_name}-documents-${random_string.suffix.result}"

  force_destroy = true
  
  tags = merge(local.common_tags, {
    Name = "Immigration Documents Storage"
    Type = "Document Storage"
  })
}

resource "aws_s3_bucket_public_access_block" "documents_pab" {
  bucket = aws_s3_bucket.immigration_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


resource "aws_s3_bucket_notification" "data_ingestion" {
  bucket = aws_s3_bucket.immigration_documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.data_ingestion.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "documents/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}