#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "🚀 Deploying to PROD environment..."
terraform init -reconfigure -backend-config=enviroments/prod-backend.hcl
terraform plan -var-file=enviroments/prod.tfvars
read -p "⚠️  Apply changes to PRODUCTION? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    terraform apply -var-file=enviroments/prod.tfvars
fi