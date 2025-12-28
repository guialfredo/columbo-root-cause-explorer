#!/usr/bin/env bash
set -euo pipefail

# Block port 6333 on the host so the qdrant service can't publish it.
# Simulates a leftover container from a previous scenario occupying the port.
# Using a non-obvious name to make investigation more challenging.
CONTAINER_NAME="data_processor_dev"
PORT="6333"

# Clean up if it already exists
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# Run a simple TCP listener on the host port
docker run -d --name "$CONTAINER_NAME" -p "${PORT}:${PORT}" alpine:3.20 \
  sh -c "apk add --no-cache socat >/dev/null 2>&1 && exec socat TCP-LISTEN:${PORT},fork,reuseaddr -"
