"""
Evaluation metrics for Columbo debugging agent.

Metrics:
1. Probe Recall - Did the agent call all mandatory probes?
2. Step Efficiency - How many steps vs optimal?
3. Groundedness - Is the diagnosis well-supported by evidence?
"""

from typing import List, Set, Dict, Any
from pydantic import BaseModel, Field
import dspy


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
) -> Dict[str, Any]:
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


# ============================================================================
# Groundedness Evaluation (LLM-as-Judge)
# ============================================================================

class GroundednessGrader(dspy.Signature):
    """
    Grade whether the diagnosis is well-grounded in the evidence collected.
    
    Evaluates if the agent jumped to conclusions or properly supported claims
    with concrete evidence from probes.
    """
    
    diagnosis_root_cause: str = dspy.InputField(
        desc="The root cause identified by the agent"
    )
    diagnosis_confidence: str = dspy.InputField(
        desc="The confidence level stated by the agent"
    )
    evidence_digest: str = dspy.InputField(
        desc="Summary of all evidence gathered during the investigation"
    )
    probes_summary: str = dspy.InputField(
        desc="List of probes executed with their key findings"
    )
    
    score: float = dspy.OutputField(
        desc="Score from 0.0 to 10.0. High score = well-grounded (concrete evidence supports diagnosis). Low score = jumped to conclusions (claims not backed by evidence)"
    )
    justification: str = dspy.OutputField(
        desc="2-3 sentences explaining the score. Cite specific evidence that supports or contradicts the diagnosis. Note any unsupported claims or logical leaps."
    )


class GroundednessResult(BaseModel):
    """Results from groundedness evaluation."""
    score: float = Field(..., ge=0.0, le=10.0, description="Groundedness score (0-10)")
    justification: str = Field(..., description="Explanation of the score")
    
    def __str__(self) -> str:
        """Human-readable summary."""
        if self.score >= 8.0:
            status = "✅"
            label = "Well-grounded"
        elif self.score >= 5.0:
            status = "⚠️"
            label = "Partially grounded"
        else:
            status = "❌"
            label = "Poorly grounded"
        
        return f"{status} Groundedness: {self.score:.1f}/10.0 ({label})"


def calculate_groundedness(
    diagnosis: Dict[str, str],
    evidence_digest: str,
    probes_executed: List[dict],
) -> GroundednessResult:
    """
    Evaluate whether the diagnosis is well-grounded in collected evidence.
    Uses LLM-as-judge to assess if conclusions are justified.
    
    Args:
        diagnosis: The diagnosis dict with root_cause, confidence, etc.
        evidence_digest: Cumulative evidence summary
        probes_executed: List of probe calls with results
        
    Returns:
        GroundednessResult with score and justification
    """
    # Build probes summary
    probes_summary_lines = []
    for i, probe in enumerate(probes_executed, 1):
        probe_name = probe.get("probe_name", "unknown")
        # Get a brief summary of the result (first 200 chars)
        result = probe.get("result", {})
        if isinstance(result, dict):
            result_summary = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
        else:
            result_summary = str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
        
        probes_summary_lines.append(f"{i}. {probe_name}: {result_summary}")
    
    probes_summary = "\n".join(probes_summary_lines) if probes_summary_lines else "No probes executed"
    
    # Run LLM grader
    grader = dspy.ChainOfThought(GroundednessGrader)
    
    result = grader(
        diagnosis_root_cause=diagnosis.get("root_cause", ""),
        diagnosis_confidence=diagnosis.get("confidence", ""),
        evidence_digest=evidence_digest or "No evidence digest available",
        probes_summary=probes_summary,
    )
    
    # Parse score, ensuring it's within bounds
    try:
        score = float(result.score)
        score = max(0.0, min(10.0, score))
    except (ValueError, TypeError):
        score = 5.0  # Default to middle score on parse error
    
    return GroundednessResult(
        score=score,
        justification=result.justification,
    )
