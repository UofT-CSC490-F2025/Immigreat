# DynamoDB table for storing chat sessions and conversation history
resource "aws_dynamodb_table" "chat_sessions" {
  name         = "immigreat-chat-sessions-${local.environment}"
  billing_mode = "PAY_PER_REQUEST"  # On-demand pricing, scales automatically
  hash_key     = "session_id"
  range_key    = "timestamp"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  # Optional: Add TTL to auto-expire old sessions after 7 days
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name        = "immigreat-chat-sessions-${local.environment}"
    Environment = local.environment
    Purpose     = "Chat conversation history storage"
  }
}

# Output the table name for easy reference
output "dynamodb_chat_table_name" {
  description = "DynamoDB table name for chat sessions"
  value       = aws_dynamodb_table.chat_sessions.name
}

output "dynamodb_chat_table_arn" {
  description = "DynamoDB table ARN for chat sessions"
  value       = aws_dynamodb_table.chat_sessions.arn
}

