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
    - statement: CONCISE one-sentence hypothesis (~10-15 words max). Focus on the core issue.
    - confidence: low/medium/high based on available evidence
    - rationale: Brief explanation with supporting details (this can be longer)
    
    CRITICAL: Keep statements short and punchy for UI display. Put elaboration in rationale.
    Example good statement: "Vectordb service not reachable from rag-agent container"
    Example bad statement: "The rag-agent cannot reach the vectordb because the two containers are on different networks and there is no shared network configured in docker-compose"
    
    CONFIDENCE RANKING: 
    - Rank hypotheses by likelihood/evidence strength
    - Use DIFFERENT confidence levels to show your ranking (high > medium > low)
    - H1 should typically have higher confidence than H4
    - high: Strong direct evidence supports this hypothesis
    - medium: Some evidence points this way but not conclusive
    - low: Plausible but speculative without strong evidence
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
    
    EXPECTED SIGNAL:
    - Keep it CONCISE (~80 chars max) for UI display
    - Focus on the KEY discriminator this probe reveals
    - Example good: "Will show if qdrant container is running and what networks it's on"
    - Example bad: "The containers_state output will list all Docker containers and their statuses. Confirmation of H1: there is no container corresponding to the vectordb service, or there is a vectordb container but it is not running or has crashed. Refutation of H1..."
    """
    planning_input: ProbePlanningInput = dspy.InputField()
    probe_plan: ProbePlan = dspy.OutputField()


probe_planner = dspy.Predict(NextProbePlan)


class EvidenceDigest(dspy.Signature):
    """Extract salient facts from probe results into a structured Finding.
    
    Create a Finding with:
    - summary: CONCISE 1-2 sentence summary (~120 chars) FOR UI DISPLAY ONLY. Focus on key headline facts.
    - detailed_summary: COMPLETE analysis with ALL relevant details for agent reasoning (no length limit).
      Include specific values, configuration details, and any context that might be relevant for diagnosis.
      This is what the agent will see in future steps, so be thorough.
    - structured: Key-value pairs of important data (container names, ports, statuses, config values, etc.)
    - severity: info (default), warning (potential issue), critical (confirmed problem)
    
    CRITICAL DISTINCTION:
    - summary: Short headline for human display ("API container running, listening on port 8080")
    - detailed_summary: Full context for agent reasoning ("API container s001_api is running with status 'running' (started 2m ago). Environment variables: QDRANT_HOST=qdrant, QDRANT_PORT=6333, QDRANT_URL=http://qdrant:6333, APP_CONFIG_PATH=/app/config/environment.yml, PYTHON_VERSION=3.12.12. The container has 9 total environment variables configured. Note: APP_CONFIG_PATH points to a YAML configuration file that may contain additional settings.")
    
    SPECIAL RULES FOR ENVIRONMENT PROBES:
    - In detailed_summary: Include ALL connection-related env vars with exact values (HOST, PORT, URL, etc.)
    - In detailed_summary: Include ALL config file paths with exact values (CONFIG_PATH, SETTINGS_FILE, etc.)
    - In detailed_summary: Note if config file env vars exist - these may override other settings
    - Example detailed_summary: "Container has QDRANT_HOST=qdrant and QDRANT_PORT=6333 from docker-compose. Also has APP_CONFIG_PATH=/app/config/environment.yml which points to a runtime config file that may override these values."
    """
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
- reasoning: CONCISE 1-2 sentence explanation (~150 chars max). Focus on the key discriminating fact.
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

