#!/bin/bash
set -e

# Variables
REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="immigreat-lambda-repo"
IMAGE_TAG="latest"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/../src"
INGEST_DOCKERFILE="${SRC_DIR}/Dockerfile.ingest"
SCRAPING_DOCKERFILE="${SRC_DIR}/Dockerfile.scraping"

build_and_push() {
  local dockerfile="$1"
  local suffix="$2"

  local local_image="${ECR_REPO_NAME}:${suffix}-${IMAGE_TAG}"
  local remote_image="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${local_image}"

  echo "Building ${local_image} using ${dockerfile}"
  docker buildx build \
    --platform linux/arm64 \
    --output type=docker \
    --provenance=false \
    --sbom=false \
    -f "${dockerfile}" \
    -t "${local_image}" \
    "${SRC_DIR}"

  echo "Tagging ${local_image} as ${remote_image}"
  docker tag "${local_image}" "${remote_image}"

  echo "Pushing ${remote_image}"
  docker push "${remote_image}"
}

# ECR Login
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

build_and_push "${INGEST_DOCKERFILE}" "ingest"
build_and_push "${SCRAPING_DOCKERFILE}" "scraping"
