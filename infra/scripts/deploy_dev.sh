#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "🔧 Deploying to DEV environment..."
terraform init -backend-config=enviroments/dev-backend.hcl
terraform plan -var-file=enviroments/dev.tfvars
read -p "Apply changes? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    terraform apply -var-file=enviroments/dev.tfvars
fi