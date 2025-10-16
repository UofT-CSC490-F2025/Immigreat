#!/bin/bash
set -e

# Variables
REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="immigreat-lambda-repo"
IMAGE_TAG="latest"
SRC_DIR="../src/lambda"

# ECR Login
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build with explicit output format for Lambda compatibility
docker buildx build \
  --platform linux/arm64 \
  --output type=docker \
  --provenance=false \
  --sbom=false \
  -t $ECR_REPO_NAME:$IMAGE_TAG \
  $SRC_DIR

# Tag and push
docker tag $ECR_REPO_NAME:$IMAGE_TAG $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG