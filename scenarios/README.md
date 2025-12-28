# Columbo Evaluation Scenarios 🔍

Columbo is evaluated on a variety of scenarios that test its ability to identify and explain container debugging issues.

These scenarios come with varying levels of difficulty, depending both on the services architecture's complexity, as well as the complexity of the bug itself.

Each scenario includes the necessary infrastructure files (docker-compose, manifests, etc.) and utilities to spin up the test environment.

## 📋 Scenarios

| ID | Name | Difficulty | Services | Bug Type | Description |
|----|------|------------|----------|----------|-------------|
| s001 | Environment Override | 🟡 Medium | RAG Agent, Qdrant | Configuration | Environment variable `QDRANT_HOST` is overridden by YAML config file, causing connection failure to vector database |
| s002 | Image Not Rebuilt | 🟡 Medium | API Client, Mock API | Build Cache | Build argument changed in `.env` file but image not rebuilt, causing service to use stale endpoint |
| s003 | Stale Volume State | 🟡 Medium | Single App | Persistent State | Named Docker volume contains incompatible schema version from previous deployment, causing immediate crash despite correct image rebuild |

### Difficulty Levels
- 🟢 **Easy**: Single service, straightforward issue
- 🟡 **Medium**: Multiple services, requires understanding of service interactions
- 🔴 **Hard**: Complex architecture, multiple potential root causes
- ⚫ **Expert**: Distributed systems, timing issues, or subtle bugs

## 🚀 Running Scenarios

Each scenario folder contains:
- `docker-compose.yml` - Infrastructure setup
- `README.md` - Scenario description and expected behavior
- Application code with the introduced bug
- Expected root cause documentation