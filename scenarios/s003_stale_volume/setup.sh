#!/usr/bin/env bash
set -euo pipefail

# Ensure we run from this script's directory
cd "$(dirname "$0")"

./seed_volume.sh s003_data 1
