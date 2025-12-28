# Scenario S003: Stale Volume State

## Overview
This scenario demonstrates a persistent volume data issue where an application fails after updating, even though the image is rebuilt correctly. The named Docker volume contains incompatible state from a previous version, causing immediate crashes.

## The Bug
The application was updated to expect schema version 2, and the Docker image was rebuilt with the new code. However, a named volume (`s003_data`) still contains a `schema_version.txt` file with version 1 from the previous deployment. The app detects this mismatch and exits immediately with a fatal error.

## Architecture
```
┌─────────────────────────────────────────┐
│  s003_app container                     │
│                                         │
│  Image contains NEW code:               │
│    - Expects schema_version=2 ✓        │
│    - Image rebuilt successfully         │
│                                         │
│  On startup, reads:                     │
│    /data/schema_version.txt            │
│                                         │
│  Volume contains OLD data:              │
│    schema_version=1 ✗                  │
│                                         │
│  Result:                                │
│    FATAL: incompatible persistent state │
│    Container exits immediately          │
└─────────────────────────────────────────┘
                │
                │ Volume mount
                ▼
┌─────────────────────────────────────────┐
│  Named Docker Volume: s003_data         │
│                                         │
│  Contents:                              │
│    /data/schema_version.txt             │
│      ↳ "1" (STALE!)                    │
│                                         │
│  This volume persists across:           │
│    - Image rebuilds ✓                   │
│    - Container restarts ✓               │
│    - docker-compose up/down ✓          │
│                                         │
│  NOT cleared by:                        │
│    - docker-compose up --build         │
│    - docker-compose down               │
│                                         │
│  ONLY cleared by:                       │
│    - docker-compose down -v            │
│    - docker volume rm s003_data        │
└─────────────────────────────────────────┘
```

## Root Cause
**ID**: `STALE_VOLUME_CAUSING_ISSUE`

**Summary**: The application stores persistent state in a named Docker volume. When the application code is updated to expect a new schema/data format, the old data in the volume remains unchanged. Named volumes persist independently of images and containers, surviving rebuilds and restarts. This creates a mismatch between the application's expectations (schema v2) and the actual data (schema v1).

**Key Concept**: Unlike image layers (which are replaced on rebuild) and environment variables (which can be changed), named volume data persists until explicitly deleted. Developers often forget this and only rebuild images, leaving incompatible state in volumes.

## Expected Debugging Steps
1. Observe that the s003_app container exits immediately after starting
2. Check the logs and see: `FATAL: incompatible persistent state in volume: schema_version=1, expected=2`
3. Inspect the Dockerfile and app.py to confirm the code expects schema_version=2
4. Verify that the image was recently rebuilt (check image creation date)
5. Realize the code/image is correct, but persistent data might be wrong
6. Discover the named volume `s003_data` is mounted to `/data`
7. Inspect the volume contents and find `/data/schema_version.txt` contains "1"
8. Identify the solution: clear/reset the volume or implement data migration

## Expected Behavior
- The image builds successfully with the new code (expects schema v2)
- The container starts and attempts to run `app.py`
- The app reads `/data/schema_version.txt` from the volume
- It finds version "1" but expects version "2"
- The app prints: `FATAL: incompatible persistent state in volume: schema_version=1, expected=2`
- The container exits with code 1
- The container enters sleep mode due to `|| true; sleep infinity` in the command
- Rebuilding the image doesn't fix the issue—the volume still contains stale data

## Why Image Rebuilds Don't Fix This
- **Images**: Contain application code, dependencies, and filesystem layers
- **Volumes**: Contain runtime data that **persists independently** of images
- Rebuilding an image with `docker-compose up --build` updates the code but **does NOT** touch volume contents
- This is by design: volumes are meant to preserve data across deployments

## Difficulty Level
**Medium** - Requires understanding of:
- Named volumes vs anonymous volumes vs bind mounts
- Volume lifecycle (independent of containers and images)
- Difference between ephemeral container state and persistent volume state
- The fact that `docker-compose down` doesn't remove volumes by default
- Volume inspection and manipulation
