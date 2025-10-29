bucket         = "terraform-state-bucket-immigreat"
key            = "terraform/prod/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "terraform-state-lock"