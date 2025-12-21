import dspy
from debugging_assistant.probes import PROBE_SCHEMAS


# Build probe documentation string for LLM
def _build_probe_docs() -> str:
    """Build comprehensive probe documentation from PROBE_SCHEMAS."""
    docs = []
    for probe_name, schema in PROBE_SCHEMAS.items():
        args_doc = []
        for arg_name, arg_desc in schema.get("args", {}).items():
            args_doc.append(f"    - {arg_name}: {arg_desc}")
        
        args_str = "\n".join(args_doc) if args_doc else "    (no arguments)"
        
        docs.append(
            f"• {probe_name}: {schema['description']}\n"
            f"  Args:\n{args_str}\n"
            f"  Example: {schema['example']}"
        )
    
    return "\n\n".join(docs)


PROBE_DOCUMENTATION = _build_probe_docs()


# thinking step before any probe selection
class HypothesesFromEvidence(dspy.Signature):
    evidence: str = dspy.InputField(
        desc="What we observed so far (errors, probe results, snippets)."
    )
    hypotheses: str = dspy.OutputField(
        desc="3-5 hypotheses, ranked. Each: 'H#: ... | confidence: low/med/high | why'."
    )
    key_unknowns: str = dspy.OutputField(
        desc="What is missing to decide (short bullets)."
    )


hypothesis_gen = dspy.Predict(HypothesesFromEvidence)


# we enforce one probe per step for clarity
class NextProbePlan(dspy.Signature):
    """You are an expert SRE diagnostic agent. Never repeat probes with identical arguments. 
    Prefer probes that disambiguate competing hypotheses.
    Early steps: be thorough and exploratory. 
    Middle steps: Balance breadth and depth. Final steps: Prioritize wrapping up and proposing solutions.
    Do not end early if you are unsure about root cause."""
    
    evidence: str = dspy.InputField(
        desc="All evidence including initial problem, previously executed probes, and gathered findings. Check 'Previously Executed Probes' section to avoid repetition."
    )
    hypotheses: str = dspy.InputField()

    probe_name: str = dspy.OutputField(
        desc=f"Choose ONE probe from the available probes below. DO NOT repeat a probe with the same arguments that was already executed (check 'Previously Executed Probes' in evidence):\n\n{PROBE_DOCUMENTATION}"
    )
    probe_args: str = dspy.OutputField(
        desc="JSON dict with probe arguments. Use the 'Example' from probe documentation above. Only include required args unless you need to override defaults. If testing the same probe type, use DIFFERENT arguments than previous executions."
    )
    expected_signal: str = dspy.OutputField(
        desc="What result would increase/decrease confidence for top hypothesis."
    )
    stop_if: str = dspy.OutputField(
        desc="Condition to stop probing and move to fix proposal."
    )


probe_planner = dspy.Predict(NextProbePlan)


class EvidenceDigest(dspy.Signature):
    raw_probe_result: str = dspy.InputField(
        desc="Raw JSON/text output of the last probe."
    )
    prior_evidence_digest: str = dspy.InputField(
        desc="Current running digest (can be empty)."
    )
    updated_evidence_digest: str = dspy.OutputField(
        desc="Updated digest: only salient facts, include concrete values (host/port/status)."
    )


evidence_digest = dspy.Predict(EvidenceDigest)


class ShouldStopDebugging(dspy.Signature):
    evidence: str = dspy.InputField(desc="All evidence gathered so far including initial problem, executed probes, and findings.")
    hypotheses: str = dspy.InputField(desc="Current hypotheses about the problem.")
    steps_used: int = dspy.InputField(desc="Number of debug steps used so far.")
    steps_remaining: int = dspy.InputField(desc="Number of debug steps remaining.")

    should_stop: str = dspy.OutputField(
        desc=(
            "Decision: 'yes' ONLY if the root cause is proven by evidence (not inferred) "
            "and no critical uncertainty remains. Otherwise 'no'."
        )
    )
    confidence: str = dspy.OutputField(
        desc="high/medium/low with brief justification grounded in evidence."
    )
    missing_evidence: str = dspy.OutputField(
        desc=(
            "If should_stop='no': list the 1-3 most important missing evidence items "
            "needed to reach high confidence. If should_stop='yes': 'none'."
        )
    )
    evidence_quotes: str = dspy.OutputField(
        desc=(
            "3-6 short evidence excerpts supporting the decision. Each bullet starts with a step/probe reference "
            "and must be <= 25 words."
        )
    )
    reasoning: str = dspy.OutputField(desc="2-3 sentences explaining the decision, strictly evidence-based.")


class ShouldStopDebuggingModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(ShouldStopDebugging)

    def forward(self, evidence, hypotheses, steps_used, steps_remaining):
        return self.predict(
            evidence=evidence,
            hypotheses=hypotheses,
            steps_used=steps_used,
            steps_remaining=steps_remaining,
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
    initial_problem: str = dspy.InputField(
        desc="The original problem statement or error."
    )
    evidence: str = dspy.InputField(
        desc="All evidence gathered during debugging."
    )
    probes_summary: str = dspy.InputField(
        desc="Summary of all probes executed."
    )
    
    root_cause: str = dspy.OutputField(
        desc="Clear statement of the root cause. Be specific with technical details (service names, ports, configs, etc.)."
    )
    confidence: str = dspy.OutputField(
        desc="Confidence level: high/medium/low with brief justification."
    )
    recommended_fixes: str = dspy.OutputField(
        desc="Numbered list of specific, actionable fixes. Include exact commands, config changes, or code modifications needed."
    )
    additional_notes: str = dspy.OutputField(
        desc="Any caveats, alternative explanations, or follow-up actions (optional)."
    )


class FinalDiagnosisModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.predict = dspy.Predict(FinalDiagnosis)

    def forward(self, initial_problem, evidence, probes_summary):
        return self.predict(
            initial_problem=initial_problem,
            evidence=evidence,
            probes_summary=probes_summary,
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
