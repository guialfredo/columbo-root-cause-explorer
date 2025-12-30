Volume Permission Mismatch - UID/GID Conflict

A data processing pipeline fails with cryptic "Permission denied" errors when writing to a mounted volume. The container runs as a non-root user (good security practice! ), but the volume was created by a different setup script running as a different UID. Logs show successful initialization, but writes silently fail or crash the app.

Root Cause Layers:

Layer 1: Volume Ownership Mismatch

A setup.sh script pre-seeds the volume using Alpine (runs as root, UID 0)
Creates /data/config/settings.json owned by root:root (UID 0, GID 0)
Creates /data/checkpoints/ directory owned by root:root
Layer 2: Container User Context

worker container runs as USER appuser (UID 1000, GID 1000) in Dockerfile
This is a security best practice (non-root containers)
But volume files are owned by UID 0
Layer 3: Misleading Permissions

/data/config/settings.json is world-readable (644), so app can READ it ✓
/data/checkpoints/ directory has drwxr-xr-x (755), so app can LIST it ✓
But app cannot WRITE to /data/checkpoints/ (needs write permission)
Logs say "Initialized successfully" because read-only checks pass
Layer 4: Partial Failure

App reads config successfully, starts processing
After processing batch 1, tries to write checkpoint → Permission denied
Retry logic kicks in, reads config again → Works!
Processes batch 2, tries to write → Permission denied again
Looks intermittent, but it's actually consistent write failure


┌─────────────────────────────────────────────────┐
│  setup.sh (runs before docker-compose up)        │
│                                                  │
│  Command:                                         │
│    docker run --rm -v s005_data:/data alpine \  │
│      sh -c "mkdir -p /data/config /data/checkpoints && \
│              echo '{}' > /data/config/settings.json"│
│                                                  │
│  Runs as:  root (UID 0, GID 0)                   │
│                                                  │
│  Creates:                                        │
│    /data/config/settings.json (0: 0, 644)        │
│    /data/checkpoints/          (0:0, 755)       │
└─────────────────────────────────────────────────┘
                    │
                    │ Volume mount
                    ▼
┌─────────────────────────────────────────────────┐
│  Named Docker Volume:  s005_data                  │
│                                                  │
│  /data/config/settings.json                      │
│    Owner: UID 0, GID 0 (root)                   │
│    Permissions: 644 (rw-r--r--)                 │
│                                                  │
│  /data/checkpoints/                              │
│    Owner: UID 0, GID 0 (root)                   │
│    Permissions: 755 (rwxr-xr-x)                 │
└─────────────────────────────────────────────────┘
                    │
                    │ Volume mount
                    ▼
┌─────────────────────────────────────────────────┐
│  worker container                                │
│                                                  │
│  Dockerfile:  USER appuser                        │
│  Runtime UID: 1000, GID: 1000                   │
│                                                  │
│  Read attempt:                                    │
│    /data/config/settings.json → SUCCESS ✓       │
│    (world-readable)                              │
│                                                  │
│  Write attempt:                                  │
│    /data/checkpoints/state.json → FAIL ✗        │
│    Error: [Errno 13] Permission denied          │
│                                                  │
│  Logs:                                           │
│    "Pipeline initialized ✓"  (misleading)       │
│    "Processing batch 1..."                       │
│    "ERROR: Cannot save checkpoint"               │
└─────────────────────────────────────────────────┘

