#!/usr/bin/env bash
set -euo pipefail

# Ensure we run from this script's directory
cd "$(dirname "$0")"

# Use compose project name for volume if available, otherwise plain name
if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
  VOLUME_NAME="${COMPOSE_PROJECT_NAME}_s003_data"
else
  VOLUME_NAME="s003_data"
fi

./seed_volume.sh "$VOLUME_NAME" 1
