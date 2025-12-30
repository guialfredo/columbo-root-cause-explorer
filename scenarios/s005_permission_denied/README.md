# Volume Permission Mismatch - UID/GID Conflict

A data processing pipeline fails with cryptic "Permission denied" errors when writing to a mounted volume. The container runs as a non-root user (security best practice), but the volume was seeded by a setup script running as root. Logs show successful initialization, but writes fail with permission errors.

## Scenario Overview

**Symptom**: Container starts successfully and reads configuration, but crashes when attempting to write checkpoint files.

**Deceptive Element**: The app appears to initialize correctly because it can *read* the config file (world-readable), masking the underlying permission issue that only surfaces on write attempts.

## Root Cause Layers

### Layer 1: Volume Ownership Mismatch

- `setup.sh` pre-seeds the volume using Alpine (runs as root, UID 0)
- Creates `/data/config/settings.json` owned by `root:root` (UID 0, GID 0)
- Creates `/data/checkpoints/` directory owned by `root:root`

### Layer 2: Container User Context

- Worker container runs as `USER appuser` (UID 1000, GID 1000) via Dockerfile
- This follows security best practices (non-root containers)
- However, volume files remain owned by UID 0

### Layer 3: Misleading Permissions

- `/data/config/settings.json` is world-readable (644) → app can READ it ✓
- `/data/checkpoints/` has `drwxr-xr-x` (755) → app can LIST it ✓
- But app **cannot WRITE** to `/data/checkpoints/` (no write permission for other)
- Logs report "Initialized successfully" because read-only checks pass

### Layer 4: Partial Failure Pattern

1. App reads config successfully → starts processing
2. After processing batch, tries to write checkpoint → **Permission denied**
3. Container crashes and restarts (or hangs with error message)

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│  setup.sh (runs before docker-compose up)       │
│                                                 │
│  $ docker run --rm \                            │
│      -v s005_permission_denied_s005_data:/data \ │
│      alpine:3.20 sh -c '...'                    │
│                                                 │
│  Runs as:  root (UID 0, GID 0)                  │
│                                                 │
│  Creates:                                       │
│    /data/config/settings.json  (0:0, 644)      │
│    /data/checkpoints/          (0:0, 755)      │
└─────────────────────────────────────────────────┘
                    │
                    │ Volume persists
                    ▼
┌─────────────────────────────────────────────────┐
│  Named Docker Volume:                           │
│    s005_permission_denied_s005_data             │
│                                                 │
│  /data/config/settings.json                     │
│    Owner: UID 0, GID 0 (root)                   │
│    Permissions: 644 (rw-r--r--)                 │
│                                                 │
│  /data/checkpoints/                             │
│    Owner: UID 0, GID 0 (root)                   │
│    Permissions: 755 (rwxr-xr-x)                 │
└─────────────────────────────────────────────────┘
                    │
                    │ Mounted by compose
                    ▼
┌─────────────────────────────────────────────────┐
│  worker container (s005_worker)                 │
│                                                 │
│  Dockerfile:  USER appuser                      │
│  Runtime UID: 1000, GID: 1000                   │
│                                                 │
│  Read attempt:                                  │
│    /data/config/settings.json → SUCCESS ✓       │
│    (world-readable, 644)                        │
│                                                 │
│  Write attempt:                                 │
│    /data/checkpoints/state.json → FAIL ✗        │
│    Error: [Errno 13] Permission denied          │
│                                                 │
│  Logs:                                          │
│    "✓ Config loaded from /data/config/..."      │
│    "✓ Data pipeline initialized"                │
│    "Processing batch 1..."                      │
│    "✗ ERROR: Failed to save checkpoint"         │
│    "  [Errno 13] Permission denied: ..."        │
└─────────────────────────────────────────────────┘
```

## Expected Debug Path

1. **Observe symptoms**: Container logs show permission denied errors
2. **Inspect container user**: Check what UID the container runs as
3. **Examine volume permissions**: List files in the volume with ownership details
4. **Identify mismatch**: UID 1000 (container) vs UID 0 (volume files)
5. **Trace volume creation**: Find setup.sh that seeded volume as root
6. **Formulate root cause**: Volume initialized with wrong ownership for container user

## Design Notes

**Exception Handling**: The `save_checkpoint()` function intentionally uses broad `except Exception` rather than specific `PermissionError` handling. This simulates real-world code where developers often use generic exception handling that masks the specific nature of errors, making the debugging scenario more challenging and realistic.