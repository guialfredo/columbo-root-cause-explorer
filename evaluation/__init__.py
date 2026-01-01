"""
Evaluation framework for Columbo debugging agent.

This package contains all evaluation-related functionality:
- Metrics calculation (probe recall, step efficiency, groundedness)
- Scenario evaluation script
- Future: batch evaluation, metric aggregation, visualization
"""

from .metrics import (
    calculate_probe_recall,
    calculate_step_efficiency,
    calculate_groundedness,
    ProbeRecallResult,
    GroundednessResult,
)

__all__ = [
    "calculate_probe_recall",
    "calculate_step_efficiency",
    "calculate_groundedness",
    "ProbeRecallResult",
    "GroundednessResult",
]
