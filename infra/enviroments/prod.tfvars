aws_region = "us-east-1"
db_password = "YOUR_PROD_PASSWORD_HERE"  # Use a different, strong password
db_name = "immigrationDocsVectordb"
lambda_memory = 1024  # More memory for prod
lambda_timeout = 900
serverless_min_capacity = 1
serverless_max_capacity = 4  # Higher capacity for prod

# Environment identifier
environment = "prod"