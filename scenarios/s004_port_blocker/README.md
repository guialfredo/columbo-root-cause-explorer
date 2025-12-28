# Scenario S004: Port Conflict with Leftover Container

## Overview
This scenario demonstrates a port conflict issue where a Docker Compose stack fails to start because a leftover container from a previous development session is still running and occupying the required port. The compose configuration is correct, but the host port is already in use.

## The Bug
A RAG agent application needs to connect to a Qdrant vector database on port 6333. The `docker-compose.yml` file is correctly configured, and the images build successfully. However, when attempting to start the services, the Qdrant container fails to start because port 6333 is already in use. A forgotten container named `data_processor_dev` from a previous development session is still running and has bound to port 6333 on the host. The critical issue: the port conflict prevents Qdrant from starting at all, so the RAG agent has no backend to connect to.

## Architecture
```
┌─────────────────────────────────────────┐
│  Host Machine (Port 6333)               │
│                                         │
│  ❌ Already bound by:                   │
│     Container: data_processor_dev       │
│     Started: Previous dev session       │
│     Status: Running                     │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ data_processor_dev (blocker)      │  │
│  │   Port: 6333 (bound) ✓           │  │
│  │   Image: alpine:3.20              │  │
│  │   Running: socat TCP listener     │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ❌ Cannot start:                       │
│     Container: s004_qdrant              │
│     Reason: Port 6333 unavailable       │
│     Status: Exits immediately           │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ s004_qdrant (blocked)             │  │
│  │   Port: 6333 (requested) ✗       │  │
│  │   Error: address already in use   │  │
│  │   Status: Exited (code 1)         │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ s004_rag_agent (waiting)          │  │
│  │   Depends on: qdrant              │  │
│  │   Status: May start but fails     │  │
│  │   Reason: Cannot reach Qdrant     │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Root Cause
**ID**: `PORT_CONFLICT`

**Summary**: Docker publishes container ports to the host using port mappings (e.g., `6333:6333`). When multiple containers request the same host port, only the first one succeeds. The compose configuration is correct, but a leftover container from a previous session has claimed port 6333. Docker Compose cannot start the new `qdrant` service because the port is unavailable.

**Key Concept**: Host ports are a shared resource across ALL containers on the system, not just those in the current project. Stopping a compose stack with `docker compose down` only affects that project's containers. Containers started outside the project (or from previous sessions with different project names) persist independently and can block ports.

## Expected Debugging Steps
1. Observe that the compose stack doesn't start properly (agent must check compose state)
2. Run `docker ps` or use container probes to check running containers
3. Notice that `s004_qdrant` is missing or exited (not running)
4. Check `docker ps -a` to see all containers including stopped ones
5. See that `s004_qdrant` has exited status
6. Check compose logs or `docker logs s004_qdrant` for error messages
7. Find "port is already allocated" or "address already in use" error
8. List ALL containers on the system: `docker ps -a` 
9. Discover the `data_processor_dev` container is running
10. Inspect ports: `docker port data_processor_dev` shows it's using 6333
11. Realize this blocker is unrelated to current project
12. Identify solution: remove blocker with `docker rm -f data_processor_dev`
13. Restart the compose stack successfully

## Expected Behavior
- Docker Compose attempts to start the `qdrant` service with port mapping `6333:6333`
- The Docker daemon tries to bind port 6333 on the host
- **The operation fails because port 6333 is already in use by `data_processor_dev`**
- Docker Compose shows an error (which the runner should not pass to the agent)
- The `qdrant` container exits immediately with status code (likely 1 or 125)
- The `rag_agent` service may start but immediately fails because Qdrant is unreachable
- **Key**: The agent must discover the port conflict through probes, not from handed error messages
- Investigation requires checking container states, logs, and system-wide port usage

## Why Rebuilding Doesn't Fix This
- **Port conflicts are host-level issues**, not related to images or builds
- Rebuilding images with `docker compose up --build` doesn't affect running containers from other projects
- `docker compose down` only stops/removes containers created by the current project
- The blocker container (`data_processor_dev`) is independent and must be explicitly removed
- This is by design: Docker doesn't automatically clean up containers from different projects or manual `docker run` commands

## Difficulty Level
**Medium** - Requires understanding of:
- Docker port publishing and host-level port binding
- The difference between project-scoped containers and system-wide containers
- Container lifecycle and persistence across compose projects
- How to list all containers (`docker ps -a`), not just the current project
- Port inspection and conflict resolution
- That `docker compose down` doesn't clean up external containers
