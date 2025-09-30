#!/bin/bash
set -e

SRC_DIR="$1"
OUTPUT_DIR="$2"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build using Docker
docker run --rm \
  -v "$SRC_DIR":/src:ro \
  -v "$OUTPUT_DIR":/output \
  --entrypoint /bin/bash \
  public.ecr.aws/lambda/python:3.11 \
  -c '
    rm -rf /output/* && \
    pip install --platform manylinux2014_x86_64 \
                --implementation cp \
                --python-version 3.11 \
                --only-binary=:all: \
                --upgrade \
                -r /src/requirements.txt \
                -t /output/ && \
    cp /src/*.py /output/
  '