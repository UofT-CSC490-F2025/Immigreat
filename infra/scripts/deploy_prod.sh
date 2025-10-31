#!/bin/bash
set -e
cd "$(dirname "$0")/.."
echo "🚀 Deploying to PROD environment..."

# Stage 1: Initialize and create ECR repository only
echo "📦 Stage 1: Creating ECR repository..."
terraform init -reconfigure -backend-config=enviroments/prod-backend.hcl
terraform apply -var-file=enviroments/prod.tfvars -target=aws_ecr_repository.lambda_repo -auto-approve

# Stage 2: Build and push Docker images
echo "🐳 Stage 2: Building and pushing Docker images..."
./scripts/build_lambda.sh

# Stage 3: Deploy everything else
echo "🚀 Stage 3: Deploying Lambda functions and remaining infrastructure..."
terraform plan -var-file=enviroments/prod.tfvars
read -p "⚠️  Apply changes to PRODUCTION? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    terraform apply -var-file=enviroments/prod.tfvars
fi