from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
import hashlib
import json

from pydantic import BaseModel, Field, ConfigDict, field_validator, computed_field


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class ArtifactFormat(str, Enum):
    markdown = "markdown"
    json = "json"


# ============================================================================
# DSPy Input Models
# ============================================================================

class EvidenceInput(BaseModel):
    """Input for hypothesis generation from evidence."""
    model_config = ConfigDict(extra="forbid")

    evidence: str = Field(
        ...,
        description="What we observed so far (errors, probe results, snippets)."
    )


class ProbePlanningInput(BaseModel):
    """Input for probe planning."""
    model_config = ConfigDict(extra="forbid")

    evidence: str = Field(..., description="Current evidence gathered.")
    hypotheses: str = Field(..., description="Current hypotheses about the problem.")
    tools_spec: str = Field(
        ...,
        description="Markdown-formatted documentation of available probes with descriptions, arguments (required/optional), and examples."
    )


class EvidenceDigestInput(BaseModel):
    """Input for evidence digestion."""
    model_config = ConfigDict(extra="forbid")

    raw_probe_result: str = Field(..., description="Raw JSON/text output of the last probe.")
    prior_evidence_digest: str = Field(..., description="Current running digest (can be empty).")


class StopDecisionInput(BaseModel):
    """Input for stop decision."""
    model_config = ConfigDict(extra="forbid")

    evidence: str = Field(
        ...,
        description="All evidence gathered so far including initial problem, executed probes, and findings."
    )
    hypotheses: str = Field(..., description="Current hypotheses about the problem.")
    steps_used: int = Field(..., description="Number of debug steps used so far.")
    steps_remaining: int = Field(..., description="Number of debug steps remaining.")


class DiagnosisInput(BaseModel):
    """Input for final diagnosis."""
    model_config = ConfigDict(extra="forbid")

    initial_problem: str = Field(..., description="The original problem statement or error.")
    evidence: str = Field(..., description="All evidence gathered during debugging.")
    probes_summary: str = Field(..., description="Summary of all probes executed.")


# ============================================================================
# DSPy Output Models
# ============================================================================

class HypothesesOutput(BaseModel):
    """Structured output for hypothesis generation."""
    model_config = ConfigDict(extra="forbid")

    hypotheses: List[Hypothesis] = Field(
        ..., 
        description="3-5 ranked hypotheses about the root cause. Each must have id, statement, confidence, and optionally rationale."
    )
    key_unknowns: str = Field(
        ...,
        description="What is missing to decide (short bullets)."
    )


class ProbePlan(BaseModel):
    """Structured output for probe planning."""
    model_config = ConfigDict(extra="forbid")

    probe_name: str = Field(..., description="Name of the probe to run (must be in tools_spec).")
    probe_args: str = Field(
        ..., 
        description=(
            "JSON dict of arguments for that probe. Use only keys allowed by tools_spec. "
            "CRITICAL: Use ACTUAL concrete values from evidence"
            "NEVER use placeholders like '<container_name>' or '<path>'. "
            "If a value is not in evidence, use a different probe to discover it first."
        )
    )
    expected_signal: str = Field(
        ..., 
        description="CONCISE statement (~80 chars) of what this probe will reveal. Focus on key discriminator."
    )
    stop_if: str = Field(..., description="Condition to stop probing and move to final diagnosis.")


class DigestOutput(BaseModel):
    """Structured output for evidence digestion."""
    model_config = ConfigDict(extra="forbid")

    finding: Finding = Field(
        ...,
        description="Extracted finding from probe result. Summary should be concise (1-2 sentences), structured contains key-value facts."
    )


class StopDecisionOutput(BaseModel):
    """Structured output for stop decision."""
    model_config = ConfigDict(extra="forbid")

    should_stop: Literal["yes", "no"] = Field(
        ...,
        description="Decision: 'yes' ONLY if the root cause is proven by evidence (not inferred) and no critical uncertainty remains. Otherwise 'no'."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level with brief justification grounded in evidence."
    )
    missing_evidence: str = Field(
        ...,
        description="If should_stop='no': list the 1-3 most important missing evidence items needed to reach high confidence. If should_stop='yes': 'none'."
    )
    evidence_quotes: str = Field(
        ...,
        description="3-6 short evidence excerpts supporting the decision. Each bullet starts with a step/probe reference and must be <= 25 words."
    )
    reasoning: str = Field(
        ...,
        description="CONCISE explanation (1-2 sentences, ~150 chars max) of the decision. Focus on key discriminating evidence."
    )


class DiagnosisResult(BaseModel):
    """Structured output for final diagnosis."""
    model_config = ConfigDict(extra="forbid")

    root_cause: str = Field(
        ...,
        description="Clear statement of the root cause. Be specific with technical details (service names, ports, configs, etc.)."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level with brief justification."
    )
    recommended_fixes: str = Field(
        ...,
        description="Numbered list of specific, actionable fixes. Include exact commands, config changes, or code modifications needed."
    )
    additional_notes: str = Field(
        default="",
        description="Any caveats, alternative explanations, or follow-up actions (optional)."
    )


# ============================================================================
# Core Domain Models
# ============================================================================

class ProbeResult(BaseModel):
    """Typed output from a probe execution.
    
    All probes MUST return this schema. This enforces deterministic structure
    and separates raw infrastructure data (probes) from interpreted evidence (Finding).
    
    Design principles:
    - probe_name: identifies which probe ran
    - success: True if probe executed without error (even if findings are negative)
    - error: populated only if probe execution itself failed
    - data: probe-specific structured output (open dict for flexibility)
    """
    model_config = ConfigDict(extra="forbid")
    
    probe_name: str = Field(..., min_length=1, description="Name of the probe that produced this result")
    success: bool = Field(default=True, description="Whether probe executed successfully (not whether it found issues)")
    error: Optional[str] = Field(default=None, description="Error message if probe execution failed")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Probe-specific structured data (e.g., {'container': 'api', 'status': 'running'})"
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Flatten to dict for backward compatibility with LLM ingestion.
        
        Merges probe_name, success, error into data dict for seamless consumption.
        """
        result = {"probe_name": self.probe_name, "success": self.success}
        if self.error:
            result["error"] = self.error
        result.update(self.data)
        return result


class ProbeCall(BaseModel):
    """One executed probe call."""
    model_config = ConfigDict(extra="forbid")

    step: int = Field(..., ge=1)
    probe_name: str = Field(..., min_length=1)
    probe_args: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Keep these optional so you can store redacted results.
    # Can be dict or list depending on the probe
    result: Optional[Any] = None
    error: Optional[str] = None

    # Useful for deterministic “no-repeat” and caching.
    signature: Optional[str] = Field(
        default=None,
        description="Canonical signature for deduping, e.g. probe_name + normalized args."
    )
    @computed_field
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @computed_field
    @property
    def success(self) -> bool:
        """Whether probe executed successfully."""
        return self.error is None

    def compute_signature(self) -> str:
        """Generate deterministic signature for caching/deduplication."""
        # Sort args for consistency
        sorted_args = json.dumps(self.probe_args, sort_keys=True)
        sig_str = f"{self.probe_name}:{sorted_args}"
        return hashlib.sha256(sig_str.encode()).hexdigest()[:12]

class Finding(BaseModel):
    """A small, human-readable piece of evidence extracted from raw probe output."""
    model_config = ConfigDict(extra="forbid")

    step: int = Field(default=0, ge=0, description="Step number assigned by orchestration layer, not LLM.")
    severity: Severity = Severity.info
    summary: str = Field(
        ..., 
        min_length=1,
        description="CONCISE 1-2 sentence summary for UI display (~120 chars max). Focus on key facts."
    )
    detailed_summary: Optional[str] = Field(
        default=None,
        description="Longer, detailed analysis for agent reasoning (no length limit). Include all relevant facts, values, and context that might be needed for diagnosis."
    )

    # Structured anchors to support "proof".
    references: List[str] = Field(
        default_factory=list,
        description="Pointers like 'probe:container_logs step:3' or 'file:docker-compose.yml'."
    )
    structured: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value facts extracted (e.g., {'container': 'api', 'status': 'running', 'port': 5000})."
    )


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable identifier like H1, H2...")
    statement: str = Field(
        ..., 
        min_length=1,
        description="Concise, single-sentence hypothesis about the root cause (~80 chars max). Put details in rationale."
    )
    confidence: ConfidenceLevel = ConfidenceLevel.low
    rationale: Optional[str] = Field(
        default=None,
        description="Short why-this-hypothesis explanation grounded in evidence."
    )
    supported_by: List[str] = Field(
        default_factory=list,
        description="References to Findings that support it."
    )
    contradicted_by: List[str] = Field(
        default_factory=list,
        description="References to Findings that contradict it."
    )


class RootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(..., min_length=1, description="Precise root cause, end-to-end.")
    confidence: ConfidenceLevel = ConfidenceLevel.medium

    # “Proof gate”: force explicit evidence citations.
    proven_by: List[str] = Field(
        default_factory=list,
        description="References to Findings / ProbeCalls that directly prove the root cause."
    )

    # Optional: causal chain for clarity (great for your env override bug class).
    causal_chain: List[str] = Field(
        default_factory=list,
        description="Ordered bullets describing how the cause leads to the symptom."
    )


class FixAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1)
    steps: List[str] = Field(default_factory=list, description="Actionable steps/commands.")
    risk: Literal["low", "medium", "high"] = "low"
    verifies_with: List[str] = Field(
        default_factory=list,
        description="How to validate the fix (commands/probes/tests)."
    )


class InvestigationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=6)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tool_version: str = Field(..., description="Version/commit of your explorer.")
    workspace_root: Optional[str] = None

    # Useful for later: “what model produced this?”
    agent_backend: Optional[str] = Field(
        default=None, description="e.g. 'dspy + gpt-4.1' or 'heuristic'."
    )
    max_steps: int = Field(10, ge=1)
    steps_used: int = Field(0, ge=0)


class FinalArtifact(BaseModel):
    """
    The canonical output you can:
    - save to disk
    - render to Markdown
    - use for evaluation (did we prove root cause?)
    - paste into Slack/Jira
    """
    model_config = ConfigDict(extra="forbid")

    metadata: InvestigationMetadata

    initial_problem: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional: env, stack info, known constraints, repro command, etc."
    )

    # The story of the run:
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    probes: List[ProbeCall] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)

    # The outcome:
    root_cause: Optional[RootCause] = None
    recommended_fixes: List[FixAction] = Field(default_factory=list)

    # If we could not prove it:
    unresolved: List[str] = Field(
        default_factory=list,
        description="Key missing evidence items / remaining uncertainties."
    )

    # Nice-to-have for UX:
    summary: Optional[str] = Field(
        default=None,
        description="1-3 sentence human summary for Slack."
    )

    def is_proven(self) -> bool:
        return bool(self.root_cause and self.root_cause.proven_by)

    def to_public_view(self) -> "FinalArtifact":
        """
        Optional helper: return a redacted copy suitable for public sharing.
        You can implement redaction policies later (paths, secrets, hostnames).
        """
        return self.model_copy(deep=True)


# ============================================================================
# Runtime / Session State Models
# ============================================================================

class DebugSession(BaseModel):
    """Runtime state of a debugging session."""
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=6)
    initial_problem: str = Field(..., min_length=1)
    workspace_root: Optional[str] = None
    
    current_step: int = Field(0, ge=0)
    max_steps: int = Field(10, ge=1)
    
    # State tracking
    evidence_digest: str = Field(
        default="",
        description="Cumulative evidence summary fed to the agent."
    )
    active_hypotheses: List[Hypothesis] = Field(
        default_factory=list,
        description="Current working hypotheses."
    )
    
    # History
    probe_history: List[ProbeCall] = Field(
        default_factory=list,
        description="All probes executed in chronological order."
    )
    findings_log: List[Finding] = Field(
        default_factory=list,
        description="All findings discovered during the session."
    )
    
    # Completion
    should_stop: bool = False
    stop_reason: Optional[str] = None
    final_root_cause: Optional[RootCause] = None
    
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Whether the session has finished."""
        return self.should_stop or self.current_step >= self.max_steps

    @computed_field
    @property
    def steps_remaining(self) -> int:
        """Number of steps left."""
        return max(0, self.max_steps - self.current_step)

    def get_executed_probe_signatures(self) -> set:
        """Get set of probe signatures to prevent duplicates."""
        signatures = set()
        for probe in self.probe_history:
            if probe.signature:
                signatures.add(probe.signature)
            else:
                # Compute on the fly
                sig = probe.compute_signature()
                signatures.add(sig)
        return signatures