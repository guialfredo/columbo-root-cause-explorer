# Scenario S002: Image Not Rebuilt After Build Arg Change

## Overview
This scenario demonstrates a common Docker debugging challenge where build arguments are changed in the `.env` file, but the Docker image retains old values due to layer caching. The container fails to connect to the correct API endpoint because it was built with stale build arguments.

## The Bug
A developer updated the `API_ENDPOINT_URL` in the `.env` file to point to a new endpoint (`http://mock_api/status/200`), but the Docker image was not properly rebuilt. The build arg was baked into the image at build time, and Docker's layer cache reused the old image layers containing the outdated value (`http://api.old-domain.com/health`).

## Architecture
```
┌─────────────────────────────────────────┐
│  api_client container                   │
│                                         │
│  Image built with ARG:                  │
│    API_ENDPOINT_URL (at BUILD TIME)    │
│                                         │
│  Current .env file says:                │
│    API_ENDPOINT_URL=                    │
│      http://mock_api/status/200 ✓      │
│                                         │
│  But image still has OLD value:         │
│    API_ENDPOINT=                        │
│      http://api.old-domain.com/health ✗│
│                                         │
│  Tries to connect to:                   │
│    http://api.old-domain.com/health     │
│    (WRONG! Should be mock_api)          │
└─────────────────────────────────────────┘
                ✗
                │  Connection fails
                │  (endpoint doesn't exist)
                ▼
        [api.old-domain.com]
           (not running)


┌─────────────────────────────────────────┐
│  mock_api container (httpbin)           │
│                                         │
│  Running and healthy at:                │
│    http://mock_api/status/200          │
│                                         │
│  But api_client never tries to          │
│  connect here!                          │
└─────────────────────────────────────────┘
```

## Root Cause
**ID**: `IMAGE_NOT_REBUILT`

**Summary**: When build arguments (ARG) are changed in the `.env` file or docker-compose.yml, Docker's layer caching can cause the image to be reused with old values baked in. Build arguments are resolved at image build time and become immutable once the image is created. Simply running `docker-compose up` without `--build` won't pick up the new values.

**Key Concept**: Unlike runtime environment variables (which can be changed without rebuilding), build arguments (ARG) are compiled into the image layers. Changing them requires:
- Rebuilding the image: `docker-compose up --build`
- OR busting the cache: `docker-compose build --no-cache`

## Expected Debugging Steps
1. Observe that the api_client container fails to connect
2. Check the logs and see it's trying to connect to `http://api.old-domain.com/health`
3. Inspect the `.env` file and notice `API_ENDPOINT_URL=http://mock_api/status/200`
4. Notice the mismatch: .env says `mock_api` but logs show `old-domain.com`
5. Check the Dockerfile and discover `ARG API_ENDPOINT_URL` + `ENV API_ENDPOINT=${API_ENDPOINT_URL}`
6. Realize that ARG values are baked in at build time
7. Check image build date/time and confirm it's old (pre-dates the .env change)
8. Identify solution: rebuild with `docker-compose build --no-cache && docker-compose up`

## Expected Behavior
- The mock_api container starts successfully and is healthy
- The api_client container starts but fails to connect
- Logs show attempts to connect to `http://api.old-domain.com/health` (the OLD endpoint)
- Connection attempts fail because that endpoint doesn't exist
- The .env file shows the CORRECT endpoint: `http://mock_api/status/200`
- This mismatch indicates the image needs rebuilding

## Difficulty Level
**Medium** - Requires understanding of:
- Docker build arguments (ARG) vs environment variables (ENV)
- Docker layer caching
- Build-time vs runtime configuration
- The difference between `docker-compose up` and `docker-compose up --build`
- Image inspection and history
