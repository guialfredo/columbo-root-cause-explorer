#!/usr/bin/env bash
set -euo pipefail

# Use COMPOSE_PROJECT_NAME from environment if available, otherwise fallback to static name
# This ensures volume name matches what docker-compose will create
if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
  VOLUME_NAME="${COMPOSE_PROJECT_NAME}_s005_data"
else
  VOLUME_NAME="s005_permission_denied_s005_data"
fi

echo "Setting up volume with initial data..."
echo "Volume name: $VOLUME_NAME"

# Create volume if it doesn't exist
docker volume create "$VOLUME_NAME" >/dev/null 2>&1 || true

# Seed the volume as root (UID 0)
docker run --rm -v "${VOLUME_NAME}:/data" alpine:3.20 sh -c '
  mkdir -p /data/config /data/checkpoints
  echo "{\"batch_size\": 100}" > /data/config/settings.json
  echo "Volume initialized by setup script (UID 0)"
  ls -la /data/
'

echo "✓ Volume seeded"