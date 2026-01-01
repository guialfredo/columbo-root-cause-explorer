# Columbo Evaluation Framework

Evaluation metrics and experiment tracking for the Columbo debugging agent.

## Quick Start

### Install Evaluation Dependencies (Optional)

```bash
# Install MLflow for experiment tracking
poetry install --with evaluation
```

### Run Evaluation

```bash
# Basic evaluation (saves JSON + Markdown reports)
poetry run python evaluation/evaluate_scenario.py s001_env_override --cleanup

# With MLflow tracking
poetry run python evaluation/evaluate_scenario.py s001_env_override --cleanup --track

# View results in MLflow UI
mlflow ui
# Then open http://localhost:5000
```

## Metrics

### 1. Probe Recall (Automated)
- **What**: Percentage of mandatory probes that were called
- **Why**: Ensures the agent follows investigative best practices
- **Output**: 0.0 - 1.0 (0% - 100%)

### 2. Step Efficiency (Automated)
- **What**: How efficiently the agent solved the problem (steps_used vs optimal)
- **Why**: Measures investigation efficiency
- **Output**: Efficiency score (capped at 1.0) and ratio

### 3. Groundedness (LLM-as-Judge)
- **What**: Is the diagnosis well-supported by evidence?
- **Why**: Ensures the agent doesn't jump to conclusions
- **Output**: Score 0-10 with justification

## MLflow Integration

When using `--track` flag, all evaluation data is logged to MLflow:

**Metrics logged:**
- `probe_recall`
- `step_efficiency_score`
- `step_efficiency_ratio`
- `steps_used`
- `groundedness_score`

**Parameters logged:**
- `scenario_id`
- `difficulty`
- `category`
- `max_steps`
- `optimal_steps`

**Artifacts logged:**
- Session JSON
- Markdown report
- Evaluation JSON

**Tags for filtering:**
- `category`: Problem category
- `difficulty`: Scenario difficulty
- `confidence`: Diagnosis confidence level
- `probe_recall_status`: complete/incomplete

## Extending with New Metrics

To add a new metric:

1. Add calculation function to `metrics.py`:
```python
def calculate_my_metric(...) -> MyMetricResult:
    """Calculate my metric."""
    # Implementation
    return MyMetricResult(...)
```

2. Call it in `evaluate_scenario.py`
3. Add to MLflow logging in `tracking.py` (optional)
4. Update documentation

## Without MLflow

If you don't install the `evaluation` group, tracking will be automatically disabled with a warning. All metrics are still calculated and saved to JSON files.
