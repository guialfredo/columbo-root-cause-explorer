# Scenario S001: Environment Variable Override

## Overview
This scenario demonstrates a common debugging challenge where a RAG agent cannot connect to its Qdrant vector database due to configuration being overridden at runtime.

## The Bug
The RAG agent is configured via `docker-compose.yml` to connect to Qdrant using the service name `qdrant`. However, a runtime configuration file (`config/environment.yml`) overrides these environment variables with `localhost`, causing connection failures inside the container.

## Architecture
```
┌─────────────────────────────────────┐
│  rag_agent container                │
│                                     │
│  Environment:                       │
│    QDRANT_HOST=qdrant ✓            │
│    QDRANT_PORT=6333   ✓            │
│                                     │
│  Runtime Config (environment.yml): │
│    qdrant:                          │
│      host: localhost  ✗ (OVERRIDE)│
│      port: 6333                     │
│                                     │
│  Tries to connect to:               │
│    http://localhost:6333           │
│    (but should be http://qdrant:6333)│
└─────────────────────────────────────┘
                ✗
                │
                │  Connection fails
                │
                ▼
┌─────────────────────────────────────┐
│  qdrant container                   │
│                                     │
│  Listening on:                      │
│    0.0.0.0:6333                    │
│    (accessible as 'qdrant:6333')   │
└─────────────────────────────────────┘
```

## Root Cause
**ID**: `ENV_OVERRIDE_DOTENV`

**Summary**: The application loads a YAML configuration file at runtime that overrides the correct environment variables set by Docker Compose. The config file contains `localhost` which doesn't work inside the container network.

## Expected Debugging Steps
1. Observe that the rag_agent container fails to connect to Qdrant
2. Check the logs and notice it's trying to connect to `localhost:6333`
3. Inspect environment variables and see `QDRANT_HOST=qdrant` is set correctly
4. Discover that `APP_CONFIG_PATH` points to a config file
5. Examine the config file and find the override
6. Identify that `localhost` doesn't resolve to the Qdrant container
7. Determine the fix: either remove the override or change `localhost` to `qdrant`

## How to Run
```bash
cd scenarios/s001_env_override
cp .env.example .env  # Create .env from template
docker-compose up --build
```

## Expected Behavior
- The rag_agent will start and attempt to connect to Qdrant
- Connection attempts will fail repeatedly
- Logs will show attempts to connect to `http://localhost:6333`
- The container will exit after 20 failed attempts

## How to Fix
Two possible solutions:

### Solution 1: Remove the override from config file
Edit `config/environment.yml`:
```yaml
# Comment out or remove the qdrant section
# qdrant:
#   host: localhost
#   port: 6333
```

### Solution 2: Fix the host in config file
Edit `config/environment.yml`:
```yaml
qdrant:
  host: qdrant  # Use the Docker service name
  port: 6333
```

## Difficulty Level
**Easy-Medium** - Requires understanding of:
- Docker networking and service names
- Configuration precedence (env vars vs config files)
- Container introspection (environment variables, config files)

## Tags
- Configuration
- Environment Variables
- Docker Networking
- Config Override
- Runtime Configuration
