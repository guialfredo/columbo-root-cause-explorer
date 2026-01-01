"""
Evaluation metrics for Columbo debugging agent.

Starting with probe recall: did the agent call all mandatory probes?
"""

from typing import List, Set, Dict
from pydantic import BaseModel, Field


class ProbeRecallResult(BaseModel):
    """Results from probe recall evaluation."""
    recall: float = Field(..., ge=0.0, le=1.0, description="Recall percentage (0.0-1.0)")
    mandatory_probes_called: List[str] = Field(default_factory=list)
    mandatory_probes_missed: List[str] = Field(default_factory=list)
    total_mandatory: int = Field(..., ge=0)
    
    def __str__(self) -> str:
        """Human-readable summary."""
        if self.total_mandatory == 0:
            return "No mandatory probes defined"
        
        status = "✅" if self.recall == 1.0 else "⚠️"
        return (
            f"{status} Probe Recall: {self.recall:.1%} "
            f"({len(self.mandatory_probes_called)}/{self.total_mandatory})"
        )


def calculate_probe_recall(
    mandatory_probes: List[str],
    probes_executed: List[dict],
) -> ProbeRecallResult:
    """
    Calculate probe recall: percentage of mandatory probes that were called.
    
    Args:
        mandatory_probes: List of mandatory probe names from manifest
        probes_executed: List of probe call dicts from the session (each with "probe_name")
        
    Returns:
        ProbeRecallResult with recall percentage and details
    """
    if not mandatory_probes:
        # No mandatory probes defined - perfect recall by default
        return ProbeRecallResult(
            recall=1.0,
            mandatory_probes_called=[],
            mandatory_probes_missed=[],
            total_mandatory=0,
        )
    
    # Extract probe names that were actually called
    called_probes: Set[str] = {
        probe["probe_name"] 
        for probe in probes_executed 
        if "probe_name" in probe and probe["probe_name"]
    }
    
    # Determine which mandatory probes were called and missed
    mandatory_set = set(mandatory_probes)
    called_mandatory = mandatory_set.intersection(called_probes)
    missed_mandatory = mandatory_set.difference(called_probes)
    
    # Calculate recall
    recall = len(called_mandatory) / len(mandatory_set)
    
    return ProbeRecallResult(
        recall=recall,
        mandatory_probes_called=sorted(list(called_mandatory)),
        mandatory_probes_missed=sorted(list(missed_mandatory)),
        total_mandatory=len(mandatory_set),
    )


def calculate_step_efficiency(
    optimal_steps: int,
    steps_used: int,
) -> Dict[str, float]:
    """
    Calculate step efficiency metrics.
    
    Args:
        optimal_steps: Optimal number of steps from manifest
        steps_used: Actual number of steps taken
        
    Returns:
        Dictionary with step efficiency metrics
    """
    # Simple efficiency score: optimal steps / actual steps
    # Capped at 1.0 for overperformance
    efficiency_ratio = optimal_steps / steps_used if steps_used > 0 else 0.0
    efficiency_score = min(1.0, efficiency_ratio)
    
    return {
        "steps_used": steps_used,
        "optimal_steps": optimal_steps,
        "efficiency_score": efficiency_score,
        "efficiency_ratio": efficiency_ratio,
    }
