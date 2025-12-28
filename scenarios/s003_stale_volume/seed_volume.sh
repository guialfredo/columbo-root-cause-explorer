#!/usr/bin/env bash
set -euo pipefail

# Seed a named docker volume with stale state for the scenario
# Usage:
#   ./seed_volume.sh s0xx_data 1
#   ./seed_volume.sh <volume_name> <schema_version>

VOLUME_NAME="${1:-}"
SCHEMA_VERSION="${2:-}"

if [[ -z "$VOLUME_NAME" || -z "$SCHEMA_VERSION" ]]; then
  echo "Usage: $0 <volume_name> <schema_version>"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found in PATH"
  exit 1
fi

echo "Seeding docker volume '$VOLUME_NAME' with schema_version=$SCHEMA_VERSION"

# Create volume if missing (idempotent)
docker volume create "$VOLUME_NAME" >/dev/null

# Write the stale schema file into the volume (idempotent overwrite)
docker run --rm \
  -v "${VOLUME_NAME}:/data" \
  alpine:3.20 \
  sh -c "mkdir -p /data && echo '${SCHEMA_VERSION}' > /data/schema_version.txt && cat /data/schema_version.txt"

echo "✓ Volume seeded"
