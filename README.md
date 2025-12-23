<div align="center">

# 🕵️ Columbo: Root Cause Explorer in Containerized Architectures

> *"Just one more thing..."* — Your AI debugging partner for containerized systems

</div>

An intelligent root cause exploration engine that helps you investigate failures in containerized environments. Like the famous detective, Columbo asks the right questions and follows the evidence until the mystery is solved.

## Overview

Columbo systematically investigates issues in your local containerized environments using hypothesis-driven reasoning. Instead of ad-hoc manual inspection, it guides a structured investigation by:

1. **Generating hypotheses** about potential root causes based on available evidence
2. **Planning and executing diagnostic probes** to gather targeted evidence
3. **Digesting findings** and updating its understanding iteratively
4. **Deciding when to stop** based on evidence quality and explicit confidence criteria
5. **Producing comprehensive diagnoses** with root causes and recommended fixes

The agent operates entirely through structured probes—deterministic inspection tools that examine container states, logs, configurations, network connectivity, and more.

## Key Features

- 🔍 **Hypothesis-Driven Investigation**: Generates and tests hypotheses systematically
- 🤖 **Autonomous Multi-Turn Reasoning**: Continues investigating until confident or max steps reached
- 🐳 **Container-Native**: Built-in probes for Docker containers, logs, exec commands, and networking
- 📊 **Structured Session Tracking**: Pydantic models for type-safe session management
- 🔄 **Dependency Resolution**: Automatic probe dependency management
- 📝 **Rich Reporting**: JSON artifacts and Markdown reports with full session history
- 🎯 **Smart Caching**: Avoids redundant probe executions through signature-based deduplication

## Architecture

```
User Problem → Debug Loop → [Generate Hypotheses → Plan Probe → Execute → Digest Evidence] → Final Diagnosis
                    ↓
            DebugSession (Pydantic)
                    ↓
        [ProbeCall, Finding, Hypothesis, RootCause]
                    ↓
            Save to JSON + Generate Report
```

The system uses:
- **DSPy** for LLM-powered reasoning modules
- **Pydantic** for type-safe data models and validation
- **Docker SDK** for container introspection
- **Structured converters** to bridge LLM outputs with Pydantic models

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design documentation.

## Available Probes

The agent has access to a comprehensive toolkit of diagnostic probes:

| Probe | Description |
|-------|-------------|
| `containers_state` | Check running/stopped status of all containers |
| `container_logs` | Retrieve recent logs from a specific container |
| `container_exec` | Execute shell commands inside containers |
| `network_probes` | Test connectivity between containers |
| `config_files_detection` | Discover configuration files (docker-compose.yml, .env, etc.) |
| `config_file_contents` | Read and analyze configuration files |
| `port_checks` | Verify port bindings and exposure |
| `env_vars_inspection` | Examine environment variables in containers |

Each probe is deterministic, never raises exceptions, and returns structured evidence suitable for LLM processing.

## Installation

### Prerequisites

- Python 3.11-3.14
- Docker Desktop or Docker Engine running locally
- OpenAI API key (or compatible LLM endpoint)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd api_tests
```

2. Create and activate a conda environment:
```bash
conda env create -f environment.yaml
conda activate api_test
```

3. Install dependencies:
```bash
poetry install
```

4. Configure your LLM API key:
```bash
# Create a .env file
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

## Usage

### Basic Usage

```python
from debugging_assistant.debug_loop import debug_loop
from debugging_assistant.session_utils import save_session_to_file, generate_session_report

# Define your problem
initial_evidence = """
My rag-agent is failing to connect to my vectordb container.
No error details visible in the logs.

Context:
- Vectordb should be running in a Docker container
- Expected to be accessible from the rag-agent container
- docker-compose.yml exists in the project root
"""

# Run the debug loop
result = debug_loop(
    initial_evidence=initial_evidence,
    max_steps=6,
    workspace_root="/path/to/your/project"
)

# Access results
diagnosis = result["diagnosis"]
session_model = result["session_model"]

print(f"Root Cause: {diagnosis['root_cause']}")
print(f"Confidence: {diagnosis['confidence']}")
print(f"Recommended Fixes: {diagnosis['recommended_fixes']}")

# Save session artifacts
save_session_to_file(session_model, directory="./debug_sessions")
generate_session_report(session_model, output_dir="./debug_sessions")
```

### Running the Example

```bash
python -m debugging_assistant.main
```

This will run the example debugging session and save:
- `debug_session_<id>.json`: Full session data with all probes and findings
- `report_<id>.md`: Human-readable markdown report

## Session Structure

Each debugging session is captured in a strongly-typed Pydantic model:

```python
class DebugSession(BaseModel):
    session_id: str
    initial_problem: str
    workspace_root: Optional[str]
    max_steps: int
    probe_history: List[ProbeCall]
    findings_log: List[Finding]
    hypotheses_log: List[Hypothesis]
    root_cause: Optional[RootCause]
    # ... and more
```

This enables:
- Type-safe access to session data
- JSON serialization/deserialization
- Computed fields (e.g., total execution time)
- Validation and constraints

## Configuration

### LLM Configuration

By default, the agent uses `gpt-4o-mini` via DSPy. To use a different model:

```python
import dspy

lm = dspy.LM("anthropic/claude-3-sonnet", api_key=api_key)
dspy.configure(lm=lm)
```

### Probe Configuration

Probes can be customized in `probes.py`. Each probe follows this signature:

```python
def my_custom_probe(containers, probe_name: str, **kwargs):
    """
    Returns: dict with evidence data
    - Never raises exceptions
    - Returns structured data suitable for LLM digestion
    """
    return {"evidence": "..."}
```

Register new probes in `probe_registry` and document them in `PROBE_SCHEMAS`.

## Example Output

```
DEBUGGING SESSION COMPLETE
======================================================================

Total probing steps: 5
Session ID: 156eb7fc

======================================================================
DIAGNOSIS SUMMARY
======================================================================

Root Cause:
The rag-agent container cannot resolve the hostname 'vectordb' because 
the vector database container is not running. The docker-compose.yml 
defines it as 'chromadb' but it's stopped.

Confidence: high

Recommended Fixes:
1. Start the chromadb container: docker compose up -d chromadb
2. Verify network connectivity: docker network inspect api_tests_default
3. Update rag-agent to use correct hostname 'chromadb' instead of 'vectordb'
```

## Project Structure

```
api_tests/
├── debugging_assistant/
│   ├── debug_loop.py        # Main debug loop orchestration
│   ├── modules.py           # DSPy reasoning modules
│   ├── probes.py            # Diagnostic probe implementations
│   ├── schemas.py           # Pydantic data models
│   └── session_utils.py     # Session persistence and reporting
├── debug_sessions/          # Saved debugging sessions and reports
├── docs/
│   └── ARCHITECTURE.md      # Detailed architecture documentation
├── rag_agent/               # Example containerized application
├── docker-compose.yml
└── README.md
```

## Advanced Features

### Probe Dependency Resolution

The system automatically resolves probe dependencies. For example, `config_file_contents` depends on `config_files_detection`:

```python
PROBE_DEPENDENCIES = {
    "config_file_contents": {
        "requires": "config_files_detection",
        "transform": lambda result: {"found_files": [f["path"] for f in result]}
    }
}
```

### Session Analytics

```python
from debugging_assistant.session_utils import analyze_probe_performance

perf = analyze_probe_performance(session_model)
print(f"Total time: {perf['total_time']:.2f}s")
print(f"Success rate: {perf['success_rate']:.1%}")
```

### Signature-Based Deduplication

The agent tracks probe signatures (name + args) to avoid redundant executions:

```python
signature = f"{probe_name}:{json.dumps(probe_args, sort_keys=True)}"
if signature in executed_signatures:
    print("⚠️  Probe already executed, skipping...")
```

## Contributing

Contributions welcome! Areas for enhancement:
- Additional probe types (filesystem, process inspection, etc.)
- Support for non-Docker containerization (Kubernetes, Podman)
- Multi-container orchestration debugging
- Integration with observability tools (Prometheus, Grafana)

## License

[Add your license here]

## Acknowledgments

Built with:
- [DSPy](https://github.com/stanfordnlp/dspy) for LLM programming
- [Pydantic](https://pydantic.dev/) for data validation
- [Docker SDK for Python](https://docker-py.readthedocs.io/)



