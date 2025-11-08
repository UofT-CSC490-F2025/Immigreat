terraform {
  backend "s3" {
    # Backend configuration is provided via -backend-config flag
    # Use: terraform init -backend-config=enviroments/dev-backend.hcl
    # Or:  terraform init -backend-config=enviroments/prod-backend.hcl
  }
}