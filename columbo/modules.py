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
    """Generate hypotheses from current evidence."""
    evidence_input: EvidenceInput = dspy.InputField()
    hypotheses_output: HypothesesOutput = dspy.OutputField()


hypothesis_gen = dspy.Predict(HypothesesFromEvidence)


class NextProbePlan(dspy.Signature):
    """You are an expert SRE diagnostic agent. Never repeat probes with identical arguments. 
    Prefer probes that disambiguate competing hypotheses.
    Early steps: be thorough and exploratory. 
    Middle steps: Balance breadth and depth. Final steps: Prioritize wrapping up and proposing solutions.
    Do not end early if you are unsure about root cause."""
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

Stop criteria (should_stop='yes') require ALL of:
1) Root cause is proven (direct evidence, not inference).
2) The failure path is explained end-to-end (why this causes the observed error).
3) A fix can be proposed without guessing (no critical missing evidence).

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

