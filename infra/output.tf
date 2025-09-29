output "opensearch_endpoint" {
  value       = aws_opensearch_domain.immigration_docs.endpoint
  description = "OpenSearch domain endpoint"
}

output "opensearch_dashboard_url" {
  value       = "https://${aws_opensearch_domain.immigration_docs.endpoint}/_dashboards/"
  description = "OpenSearch Dashboards URL"
}

output "opensearch_secret_name" {
  value       = aws_secretsmanager_secret.opensearch_creds.name
  description = "Name of secret containing OpenSearch credentials"
  sensitive   = true
}