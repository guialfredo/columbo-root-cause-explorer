# Columbo Evaluation Scenarios 🔍

Columbo is evaluated on a variety of scenarios that test its ability to identify and explain container debugging issues.

These scenarios come with varying levels of difficulty, depending both on the services architecture's complexity, as well as the complexity of the bug itself.

Each scenario includes the necessary infrastructure files (docker-compose, manifests, etc.) and utilities to spin up the test environment.

## 📋 Scenarios

| ID | Name | Difficulty | Services | Bug Type | Description |
|----|------|------------|----------|----------|-------------|
| s001 | Environment Override | 🟡 Medium | RAG Agent, Qdrant | Configuration | Environment variable `QDRANT_HOST` is overridden by YAML config file, causing connection failure to vector database |

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