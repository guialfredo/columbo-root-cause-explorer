import dspy
from columbo.schemas import (
    EvidenceInput,
    ProbePlanningInput,
    EvidenceDigestInput,
    StopDecisionInput,
    DiagnosisInput,
    HypothesesOutput,
    ProbePlan,
    DigestOutput,
    StopDecisionOutput,
    DiagnosisResult,
)


# ============================================================================
# DSPy Signatures
# ============================================================================

class HypothesesFromEvidence(dspy.Signature):
    """Generate 3-5 ranked hypotheses from current evidence.
    
    Output structured Hypothesis objects with:
    - id: H1, H2, H3, etc. (sequential)
    - statement: Clear, testable hypothesis about the root cause
    - confidence: low/medium/high based on available evidence
    - rationale: Brief explanation of why this hypothesis is plausible
    """
    evidence_input: EvidenceInput = dspy.InputField()
    hypotheses_output: HypothesesOutput = dspy.OutputField()


hypothesis_gen = dspy.Predict(HypothesesFromEvidence)


class NextProbePlan(dspy.Signature):
    """You are an expert SRE diagnostic agent. Never repeat probes with identical arguments. 
    Prefer probes that disambiguate competing hypotheses.
    Early steps: be thorough and exploratory. 
    Middle steps: Balance breadth and depth. Final steps: Prioritize wrapping up and proposing solutions.
    Do not end early if you are unsure about root cause.
    
    CRITICAL: When specifying probe arguments:
    - ALWAYS use actual concrete values from the evidence (container names, file paths, port numbers, etc.)
    - NEVER use placeholders like '<container_name>', '<failing_container>', '<path>', etc.
    - If the evidence mentions specific containers, use that exact name
    - If multiple containers exist, choose the most relevant one based on the error/hypothesis
    - If a required value is not in the evidence, choose a probe that will discover it first
    """
    planning_input: ProbePlanningInput = dspy.InputField()
    probe_plan: ProbePlan = dspy.OutputField()


probe_planner = dspy.Predict(NextProbePlan)


class EvidenceDigest(dspy.Signature):
    """Extract salient facts from probe results."""
    digest_input: EvidenceDigestInput = dspy.InputField()
    digest_output: DigestOutput = dspy.OutputField()


evidence_digest = dspy.Predict(EvidenceDigest)


class ShouldStopDebugging(dspy.Signature):
    """Decide whether debugging should stop."""
    stop_input: StopDecisionInput = dspy.InputField()
    stop_decision: StopDecisionOutput = dspy.OutputField()


class ShouldStopDebuggingModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(ShouldStopDebugging)

    def forward(self, evidence, hypotheses, steps_used, steps_remaining):
        stop_input_model = StopDecisionInput(
            evidence=evidence,
            hypotheses=hypotheses,
            steps_used=steps_used,
            steps_remaining=steps_remaining
        )
        return self.predict(
            stop_input=stop_input_model,
            instructions="""
You are acting as a senior production SRE deciding whether debugging can stop.

Grounding rules:
- Base your decision strictly on the provided evidence.
- Do NOT assume the contents of files or runtime behavior unless directly observed.
- If the top hypothesis mentions a specific artifact (e.g., /app/config/environment.yml, Dockerfile ENV, config loader),
  you must have direct evidence from that artifact (e.g., file content, inspect output, code snippet) before stopping.

Special rules for data/volume issues:
- If hypotheses mention "stale data", "incompatible volume", "schema mismatch", "persistent state", or similar:
  * You MUST have actual file contents from the volume (via volume_file_read or volume_data_inspection)
  * The evidence MUST include the file_contents field with the actual data values
  * Seeing only "file exists" or "file size" or "No file contents captured" is NOT sufficient
  * Reading source code that validates data is NOT sufficient - you need the actual data values
  * Knowing a volume is mounted is NOT sufficient - you must inspect what's inside it
  * Do NOT infer volume contents from error messages - you must read the file directly

Special rules for port conflict issues:
- If error messages mention "port already allocated", "address already in use", "bind failed", or similar:
  * You MUST identify which specific container is occupying the conflicting port
  * Knowing "port X is unavailable" is NOT sufficient - you need the blocker's identity
  * Use port inspection probes to see all container port bindings
- Do NOT stop if the recommended fix involves manual host investigation (lsof, netstat, etc) - this means you haven't found the blocker yet

Special rules for permission/access issues:
- If error messages mention "permission denied", "access denied", "cannot write", "read-only", or similar:
  * You MUST inspect permissions/ownership of the relevant resource (use ls -ln, inspect_volume_file_permissions, or similar)
  * You MUST confirm the UID/GID that the container process is running as
  * Generic assumptions without evidence are insufficient - verify ownership and permissions with actual probe data
  * For write failures: ensure you've checked that the user lacks write permission (not just that the resource exists)

Stop criteria (should_stop='yes') require ALL of:
1) Root cause is proven (direct evidence, not inference).
2) The failure path is explained end-to-end (why this causes the observed error).
3) A fix can be proposed without guessing (no critical missing evidence).
4) For volume/data issues: actual data values have been inspected, not just inferred.

If steps_remaining is small, prioritize the single most discriminating missing piece of evidence.
Output format rules:
- should_stop must be exactly 'yes' or 'no'
- If should_stop='yes', missing_evidence must be 'none'
"""
        )


stop_decider = ShouldStopDebuggingModule()


class FinalDiagnosis(dspy.Signature):
    """Generate final diagnosis from all evidence."""
    diagnosis_input: DiagnosisInput = dspy.InputField()
    diagnosis_result: DiagnosisResult = dspy.OutputField()


class FinalDiagnosisModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(FinalDiagnosis)

    def forward(self, initial_problem, evidence, probes_summary):
        diagnosis_input_model = DiagnosisInput(
            initial_problem=initial_problem,
            evidence=evidence,
            probes_summary=probes_summary
        )
        return self.predict(
            diagnosis_input=diagnosis_input_model,
            instructions="""
You are acting as a senior production SRE.

General rules:
- Base conclusions strictly on provided evidence.
- If evidence is insufficient, explicitly say so.
- Avoid speculation and generic explanations.
- Be precise and technical.
- Do not repeat the input verbatim.
"""
        )


final_diagnosis = FinalDiagnosisModule()

