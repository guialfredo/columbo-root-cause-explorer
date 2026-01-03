import json
import docker
from datetime import datetime
from typing import Optional
from columbo.modules import (
    hypothesis_gen, 
    probe_planner, 
    evidence_digest, 
    stop_decider, 
    final_diagnosis,
    EvidenceInput,
    ProbePlanningInput,
    EvidenceDigestInput,
)
from columbo.probes import probe_registry, PROBE_DEPENDENCIES, build_tools_spec, validate_probe_args, PROBE_SCHEMAS
from columbo.probes import sanitize_probe_args
from columbo.probes.runtime import invoke_with_container_resolution
from columbo.probes.spec import PROBES
from columbo.schemas import (
    DebugSession,
    ProbeCall,
    Finding,
    Hypothesis,
    ConfidenceLevel,
    Severity,
    ProbeResult,
)
from columbo.tracing import (
    trace_session,
    trace_reasoning_step,
    trace_probe_execution,
)
from pathlib import Path
import uuid
from typing import Dict, Any, Optional, List


# Derive container probe categories from metadata (single source of truth)
# Multi-container probes: container-scoped probes that take a list of containers
_MULTI_CONTAINER_PROBES = {
    name for name, spec in PROBES.items()
    if spec.scope == "container" and "container" not in spec.required_args
}

# Single-container probes: container-scoped probes that require a single container
_SINGLE_CONTAINER_PROBES = {
    name for name, spec in PROBES.items()
    if spec.scope == "container" and "container" in spec.required_args
}

# All container probes (union of both categories)
_ALL_CONTAINER_PROBES = _MULTI_CONTAINER_PROBES | _SINGLE_CONTAINER_PROBES


class DebugContext:
    """Encapsulates debug session context including verbose mode.
    
    Replaces global _VERBOSE to ensure deterministic, thread-safe behavior.
    According to project guidelines: avoid module-level globals that can be
    mutated and cause non-deterministic behavior in concurrent scenarios.
    """
    def __init__(self, verbose: bool, workspace_root: str, session: 'DebugSession'):
        self.verbose = verbose
        self.workspace_root = workspace_root
        self.session = session
        self.container_cache = ContainerCache()
        self.probe_results_cache: Dict[str, Any] = {}
        self.evidence_log: List[str] = []
    
    def vprint(self, *args, **kwargs):
        """Context-aware verbose print."""
        if self.verbose:
            print(*args, **kwargs)


class ContainerCache:
    """Cache for Docker containers to avoid repeated discovery."""
    def __init__(self):
        self.containers = None
        self.client = None
        self.discovered = False
    
    def discover(self, context: Optional['DebugContext'] = None):
        """Discover all Docker containers on the local system.
        
        Args:
            context: Optional debug context for verbose output
        """
        if self.discovered:
            return self.containers, self.client
        
        try:
            self.client = docker.from_env()
            self.containers = self.client.containers.list(all=True)
            self.discovered = True
            if context:
                context.vprint(f"Discovered {len(self.containers)} Docker containers")
        except Exception as e:
            if context:
                context.vprint(f"Error connecting to Docker: {e}")
            self.containers = []
            self.client = None
            self.discovered = True
        
        return self.containers, self.client


def parse_probe_args(probe_args_str: str) -> dict:
    """Parse probe arguments from string to dict.
    
    Args:
        probe_args_str: JSON-like string from the LLM
        
    Returns:
        dict: Parsed arguments
    """
    try:
        # Try to parse as JSON
        args = json.loads(probe_args_str)
        return args if isinstance(args, dict) else {}
    except json.JSONDecodeError:
        # If JSON parsing fails, try to extract key-value pairs
        # This handles cases where the LLM returns something like "container=api, tail=100"
        args = {}
        try:
            for part in probe_args_str.split(","):
                if "=" in part:
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Try to convert to int if possible
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                    args[key] = value
        except Exception:
            pass
        return args


def resolve_probe_dependencies(
    probe_name: str,
    args: dict,
    probe_results_cache: dict,
    workspace_root: Optional[str],
    context: Optional['DebugContext'] = None
) -> dict:
    """Resolve dependencies for a probe using declarative configuration.
    
    Args:
        probe_name: Name of the probe being executed
        args: Current arguments for the probe
        probe_results_cache: Cache of previous probe results
        workspace_root: Workspace root path
        context: Optional debug context for verbose output
        
    Returns:
        dict: Updated arguments with resolved dependencies
    """
    if probe_name not in PROBE_DEPENDENCIES:
        return args
    
    dep_config = PROBE_DEPENDENCIES[probe_name]
    required_probe = dep_config["requires"]
    
    # Check if dependency was already run
    if required_probe not in probe_results_cache:
        if context:
            context.vprint(f"  → Dependency '{required_probe}' not found, auto-executing...")
        
        # Auto-execute the required probe
        required_func = probe_registry[required_probe]
        if required_probe == "config_files_detection":
            result = required_func(
                root_path=workspace_root or ".",
                probe_name=required_probe,
                max_depth=3
            )
        else:
            result = required_func(probe_name=required_probe)
        
        probe_results_cache[required_probe] = result
        if context:
            context.vprint(f"  → Auto-executed '{required_probe}'")
    else:
        if context:
            context.vprint(f"  → Using cached result from '{required_probe}'")
    
    # Transform the dependency result and merge into args
    cached_result = probe_results_cache[required_probe]
    
    # Convert ProbeResult to dict if needed for transform function compatibility
    if hasattr(cached_result, 'to_dict'):
        result_dict = cached_result.to_dict()
    elif isinstance(cached_result, dict):
        result_dict = cached_result
    else:
        # Fallback: try to convert to dict via model_dump if it's a Pydantic model
        result_dict = cached_result.model_dump() if hasattr(cached_result, 'model_dump') else cached_result
    
    transformed = dep_config["transform"](result_dict)
    
    file_count = len(transformed.get("found_files", []))
    if context:
        context.vprint(f"  → Resolved to {file_count} files")
    
    # Merge transformed data into args (don't override if explicitly provided)
    for key, value in transformed.items():
        if key not in args or not args[key]:
            args[key] = value
    
    return args


def execute_probe(
    probe_name: str, 
    probe_args_str: str, 
    container_cache: ContainerCache,
    probe_results_cache: dict,
    workspace_root: Optional[str] = None,
    context: Optional['DebugContext'] = None
) -> dict:
    """Execute a probe by looking it up in the probe registry.
    
    Args:
        probe_name: Name of the probe to execute
        probe_args_str: JSON string of probe arguments
        container_cache: Cache object that discovers containers on demand
        probe_results_cache: Dictionary storing previous probe results for reference
        workspace_root: Root path of the workspace (for file-related probes)
        context: Optional debug context for verbose output
        
    Returns:
        dict: Probe result or error information
    """
    # Look up probe in registry
    if probe_name not in probe_registry:
        return {
            "error": f"Unknown probe: {probe_name}",
            "available_probes": list(probe_registry.keys()),
            "probe_name": probe_name,
        }
    
    probe_func = probe_registry[probe_name]
    
    # Parse arguments
    args = parse_probe_args(probe_args_str)
    
    # Sanitize arguments (remove LLM-provided dependencies, normalize aliases)
    args = sanitize_probe_args(probe_name, args)
    
    # Resolve dependencies using declarative configuration
    args = resolve_probe_dependencies(probe_name, args, probe_results_cache, workspace_root, context)
    
    # Validate required arguments are present
    is_valid, error_msg = validate_probe_args(probe_name, args)
    if not is_valid:
        return {
            "error": error_msg,
            "probe_name": probe_name,
            "provided_args": list(args.keys()),
        }
    
    try:
        # Discover containers if needed for container-scoped probes
        containers, client = None, None
        if probe_name in _ALL_CONTAINER_PROBES:
            containers, client = container_cache.discover(context)
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name
                }
        
        # Handle different probe types
        if probe_name in _MULTI_CONTAINER_PROBES:
            # Multi-container probes (e.g., containers_state, containers_ports)
            result = probe_func(containers, probe_name=probe_name)
        
        elif probe_name in _SINGLE_CONTAINER_PROBES:
            # Single-container probes - use runtime for resolution
            args["probe_name"] = probe_name
            probe_result = invoke_with_container_resolution(probe_func, args, client, containers)
            result = probe_result.to_dict() if isinstance(probe_result, ProbeResult) else probe_result
            
        elif probe_name in ["dns_resolution", "tcp_connection", "http_connection"]:
            # Network probes - pass args directly
            result = probe_func(**args, probe_name=probe_name)
            
        elif probe_name == "config_files_detection":
            root_path = args.get("root_path") or workspace_root or "."
            max_depth = args.get("max_depth", 3)
            result = probe_func(
                root_path=root_path,
                probe_name=probe_name,
                max_depth=max_depth,
            )
            
        elif probe_name in ["env_files_parsing", "docker_compose_parsing", "generic_config_parsing"]:
            # Parsing probes - dependencies already resolved
            found_files = args.get("found_files", [])
            result = probe_func(found_files, probe_name=probe_name)
            
        else:
            # Generic probe execution
            result = probe_func(**args, probe_name=probe_name)
            
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "probe_name": probe_name,
            "args": args,
        }


def format_probe_result(result) -> str:
    """Format probe result as readable text for the LLM."""
    try:
        return json.dumps(result, indent=2, default=str)
    except Exception:
        return str(result)


def debug_loop(
    initial_evidence: str, 
    max_steps: int = 10, 
    workspace_root: Optional[str] = None,
    ui_callback: Optional[Any] = None,
    verbose: Optional[bool] = None
) -> dict:
    """Main debugging loop with hypothesis generation, probing,
    probe planning, execution, and evidence digestion.
    
    Args:
        initial_evidence: Initial problem description or error message
        max_steps: Maximum number of probing steps (default 10)
        workspace_root: Root path of the workspace for file operations
        ui_callback: Optional UI handler for live updates (e.g., ColumboUI instance)
        verbose: Show verbose print statements (default: False if ui_callback, True otherwise)
        
    Returns:
        dict: Final debugging results including evidence, hypotheses, and probes executed
    """
    # Auto-detect verbose mode based on UI presence
    if verbose is None:
        verbose = ui_callback is None
    
    if workspace_root is None:
        workspace_root = str(Path.cwd())
    
    # Initialize structured session
    session = DebugSession(
        session_id=str(uuid.uuid4())[:8],
        initial_problem=initial_evidence,
        workspace_root=workspace_root,
        max_steps=max_steps,
        current_step=0
    )
    
    # Initialize debug context (replaces global _VERBOSE)
    context = DebugContext(verbose=verbose, workspace_root=workspace_root, session=session)
    
    # Legacy compatibility - keep these for now
    evidence = initial_evidence
    
    context.vprint(f"Starting debug loop (max {max_steps} steps)...")
    context.vprint(f"Session ID: {session.session_id}")
    context.vprint(f"Workspace: {workspace_root}\n")
    
    # Start MLflow tracing for the entire session
    with trace_session(session.session_id, initial_evidence, max_steps):
        return _debug_loop_impl(context, session, evidence, ui_callback)


def _debug_loop_impl(
    context: DebugContext,
    session: DebugSession,
    evidence: str,
    ui_callback: Optional[Any]
) -> dict:
    """Implementation of the debug loop (wrapped by trace_session).
    
    Args:
        context: Debug context with verbose mode and caches
        session: Debug session object
        evidence: Current evidence string
        ui_callback: Optional UI handler
        
    Returns:
        dict: Final debugging results
    """
    max_steps = session.max_steps
    
    for step in range(max_steps):
        context.vprint(f"\n{'='*60}")
        context.vprint(f"Step {step + 1}/{max_steps}")
        context.vprint(f"{'='*60}")
        
        # Update UI - new step
        if ui_callback:
            ui_callback.update_step(step + 1)
        
        try:
            # Generate hypotheses
            context.vprint("\nGenerating hypotheses...")
            if ui_callback:
                ui_callback.update_activity("Generating hypotheses...")
            
            evidence_input = EvidenceInput(evidence=evidence)
            hypotheses_result = hypothesis_gen(evidence_input=evidence_input)
            structured_hypotheses = hypotheses_result.hypotheses_output.hypotheses  # List[Hypothesis]
            key_unknowns = hypotheses_result.hypotheses_output.key_unknowns
            
            # Update session with structured hypotheses
            session.active_hypotheses = structured_hypotheses
            
            # Create string representation for LLM and logging
            hypotheses_str = "\n".join([
                f"{h.id}: {h.statement} | confidence: {h.confidence.value}" + 
                (f" | why: {h.rationale}" if h.rationale else "")
                for h in structured_hypotheses
            ])
            
            # Trace hypothesis generation
            trace_reasoning_step(
                step_type="hypothesis_generation",
                step_num=step + 1,
                inputs={"evidence": evidence[:500]},
                outputs={
                    "hypotheses": hypotheses_str[:500],
                    "key_unknowns": key_unknowns[:300],
                    "num_hypotheses": len(structured_hypotheses)
                }
            )
            
            context.vprint(f"\nHypotheses:\n{hypotheses_str}")
            context.vprint(f"\nKey unknowns:\n{key_unknowns}")
            
            # Send structured hypotheses to UI
            if ui_callback:
                hypothesis_list = [
                    {
                        "description": f"{h.id}: {h.statement}",
                        "confidence": h.confidence.value,
                        "reasoning": h.rationale or ""
                    }
                    for h in structured_hypotheses
                ]
                ui_callback.update_hypotheses(hypothesis_list)
            
            # Plan next probe
            context.vprint("\nPlanning next probe...")
            if ui_callback:
                ui_callback.update_activity("Planning diagnostic probe...")
            
            tools_spec = build_tools_spec()
            planning_input = ProbePlanningInput(
                evidence=evidence,
                hypotheses=hypotheses_str,  # Use string representation for LLM
                tools_spec=tools_spec
            )
            probe_plan_result = probe_planner(planning_input=planning_input)
            
            probe_name = probe_plan_result.probe_plan.probe_name
            probe_args = probe_plan_result.probe_plan.probe_args
            expected_signal = probe_plan_result.probe_plan.expected_signal
            stop_condition = probe_plan_result.probe_plan.stop_if
            
            # Trace probe planning
            trace_reasoning_step(
                step_type="probe_planning",
                step_num=step + 1,
                inputs={
                    "hypotheses": hypotheses_str[:300],
                    "evidence": evidence[:300]
                },
                outputs={
                    "probe_name": probe_name,
                    "probe_args": probe_args[:200],
                    "expected_signal": expected_signal[:200]
                },
                metadata={"stop_condition": stop_condition[:100]}
            )
            
            # Update UI with probe selection
            if ui_callback:
                args_preview = str(probe_args)[:50] + "..." if len(str(probe_args)) > 50 else str(probe_args)
                ui_callback.update_activity(f"Selected probe: {probe_name}")
                ui_callback.update_probe_plan(probe_name, probe_args, expected_signal)
            
            # Check if this exact probe+args combination has been executed before
            # Create temporary ProbeCall to compute signature
            temp_probe = ProbeCall(
                step=step + 1,
                probe_name=probe_name,
                probe_args=parse_probe_args(probe_args)
            )
            probe_signature = temp_probe.compute_signature()
            
            if probe_signature in session.get_executed_probe_signatures():
                context.vprint(f"\n⚠ WARNING: This exact probe has already been executed!")
                context.vprint(f"   Probe: {probe_name}")
                context.vprint(f"   Args: {probe_args}")
                context.vprint(f"   Skipping duplicate and moving to next iteration...\n")
                # Add a note to evidence that the agent tried to repeat
                context.evidence_log.append(f"[Step {step + 1}] Agent attempted to repeat {probe_name} with same args - skipped")
                continue
            
            context.vprint(f"\nProbe: {probe_name}")
            context.vprint(f"Args: {probe_args}")
            context.vprint(f"Expected signal: {expected_signal}")
            
            # Execute probe
            context.vprint(f"\nExecuting probe '{probe_name}'...")
            if ui_callback:
                ui_callback.update_activity(f"Executing: {probe_name}")
            
            probe_start = datetime.utcnow()
            
            raw_probe_result = execute_probe(
                probe_name=probe_name,
                probe_args_str=probe_args,
                container_cache=context.container_cache,
                probe_results_cache=context.probe_results_cache,
                workspace_root=context.workspace_root,
                context=context
            )
            
            probe_end = datetime.utcnow()
            
            # Store result in cache for future probes to reference
            context.probe_results_cache[probe_name] = raw_probe_result
            
            # Normalize result: wrap lists in dict for consistency
            normalized_result = raw_probe_result
            if isinstance(raw_probe_result, list):
                normalized_result = {"items": raw_probe_result}
            
            # Create structured ProbeCall
            probe_call = ProbeCall(
                step=step + 1,
                probe_name=probe_name,
                probe_args=parse_probe_args(probe_args),
                started_at=probe_start,
                finished_at=probe_end,
                result=normalized_result,
                error=str(normalized_result.get("error")) if isinstance(normalized_result, dict) and normalized_result.get("error") else None,
            )
            probe_call.signature = probe_call.compute_signature()
            
            # Add to session
            session.probe_history.append(probe_call)
            session.current_step = step + 1
            
            # Trace probe execution
            trace_probe_execution(
                probe_name=probe_name,
                probe_args=probe_call.probe_args,
                result=normalized_result,
                error=probe_call.error
            )
            
            # Update UI with probe execution
            if ui_callback:
                success = probe_call.error is None
                ui_callback.add_probe_execution(step + 1, probe_name, success)
            
            probe_result_str = format_probe_result(raw_probe_result)
            context.vprint(f"\nProbe result:\n{probe_result_str[:500]}...")
            if probe_call.duration_seconds:
                context.vprint(f"Execution time: {probe_call.duration_seconds:.2f}s")
            
            # Digest evidence - create a compact summary of this probe's findings
            context.vprint("\nDigesting evidence...")
            if ui_callback:
                ui_callback.update_activity("Digesting evidence...")
            prior_evidence_text = "\n".join(context.evidence_log)
            digest_input = EvidenceDigestInput(
                raw_probe_result=probe_result_str,
                prior_evidence_digest=prior_evidence_text
            )
            evidence_digest_result = evidence_digest(digest_input=digest_input)
            new_finding = evidence_digest_result.digest_output.updated_evidence_digest
            
            # Trace evidence digestion
            trace_reasoning_step(
                step_type="evidence_digestion",
                step_num=step + 1,
                inputs={
                    "raw_probe_result": probe_result_str[:500],
                    "prior_evidence": prior_evidence_text[:300]
                },
                outputs={"new_finding": new_finding[:500]}
            )
            
            # Extract just the NEW information (not the full cumulative digest)
            # by looking at what was added beyond the prior evidence
            if prior_evidence_text and new_finding.startswith(prior_evidence_text):
                # The digest returned the full cumulative text
                new_info = new_finding[len(prior_evidence_text):].strip()
            else:
                # The digest returned incremental info or completely rewritten
                new_info = new_finding
            
            # Add this finding to our evidence log with step marker
            finding_entry = f"[Step {step + 1} - {probe_name}] {new_info}"
            context.evidence_log.append(finding_entry)
            
            context.vprint(f"\nNew finding:\n{new_info}")
            
            # Update UI with latest finding
            if ui_callback:
                ui_callback.update_finding({
                    "summary": new_info,
                    "significance": expected_signal if expected_signal else "N/A"
                })
            
            # Reconstruct full evidence from initial problem + all findings
            all_findings = "\n\n".join(context.evidence_log)
            
            # Build list of previously executed probes for LLM visibility
            executed_list = []
            for i, exec_probe in enumerate(session.probe_history, 1):
                executed_list.append(f"{i}. {exec_probe.probe_name} - {exec_probe.probe_args}")
            
            probes_summary = "\n".join(executed_list) if executed_list else "None yet"
            
            # Calculate remaining steps for agent awareness
            steps_used = step + 1
            steps_remaining = max_steps - steps_used
            
            evidence = (
                f"{session.initial_problem}\n\n"
                f"--- Debug Session Info ---\n"
                f"Steps used: {steps_used}/{max_steps}\n"
                f"Steps remaining: {steps_remaining}\n"
                f"Note: {'Focus on concluding and proposing fixes.' if steps_remaining <= 2 else 'Continue investigating systematically.'}\n\n"
                f"--- Previously Executed Probes ---\n"
                f"{probes_summary}\n\n"
                f"--- Evidence Gathered ---\n\n"
                f"{all_findings}"
            )
            
            # Agent-driven stopping decision
            context.vprint(f"\nEvaluating whether to stop debugging...")
            if ui_callback:
                ui_callback.update_activity("Evaluating confidence...")
            
            stop_result = stop_decider(
                evidence=evidence,
                hypotheses=hypotheses_str,  # Use string representation for LLM
                steps_used=steps_used,
                steps_remaining=steps_remaining
            )
            
            # Access structured output directly
            stop_decision = stop_result.stop_decision
            should_stop = stop_decision.should_stop == "yes"
            
            # Trace stop decision
            trace_reasoning_step(
                step_type="stop_decision",
                step_num=step + 1,
                inputs={
                    "evidence": evidence[:500],
                    "hypotheses": hypotheses_str[:300],
                    "steps_used": steps_used,
                    "steps_remaining": steps_remaining
                },
                outputs={
                    "should_stop": stop_decision.should_stop,
                    "confidence": stop_decision.confidence,
                    "reasoning": stop_decision.reasoning
                }
            )
            
            session.should_stop = should_stop
            session.stop_reason = stop_decision.reasoning
            
            context.vprint(f"Stop decision: {stop_decision.should_stop}")
            context.vprint(f"Confidence: {stop_decision.confidence}")
            context.vprint(f"Reasoning: {stop_decision.reasoning}")
            
            # Update UI with stop decision
            if ui_callback:
                ui_callback.update_confidence(stop_decision.confidence)
                # Update stop decision display with full information
                if hasattr(ui_callback, 'update_stop_decision'):
                    ui_callback.update_stop_decision(
                        should_stop, 
                        stop_decision.reasoning,
                        stop_decision.confidence
                    )
                if should_stop:
                    ui_callback.update_activity(f"✓ Stopping: {stop_decision.reasoning[:60]}...")
                else:
                    ui_callback.update_activity(f"Continuing investigation...")
            
            if should_stop:
                context.vprint("\n✓ Agent decided to stop debugging!")
                break
            
            # Also check if error appears in evidence
            if "error" in raw_probe_result and "Unknown probe" in str(raw_probe_result.get("error", "")):
                context.vprint(f"\n⚠ Probe execution error, but continuing...")
                
        except Exception as e:
            context.vprint(f"\n✗ Error in debug loop step {step + 1}: {e}")
            evidence += f"\n\nError in step {step + 1}: {str(e)}"
            # Continue to next iteration
    
    context.vprint(f"\n\n{'='*60}")
    context.vprint("Debug loop completed")
    context.vprint(f"{'='*60}")
    
    # Generate final diagnosis and recommendations
    context.vprint("\n\nGenerating final diagnosis...")
    probes_summary = "\n".join([
        f"{i}. {p.probe_name} - {p.probe_args}" 
        for i, p in enumerate(session.probe_history, 1)
    ])
    
    diagnosis_result = final_diagnosis(
        initial_problem=session.initial_problem,
        evidence=evidence,
        probes_summary=probes_summary
    )
    diagnosis = diagnosis_result.diagnosis_result
    
    # Trace final diagnosis
    trace_reasoning_step(
        step_type="final_diagnosis",
        step_num=session.current_step + 1,  # Use current step + 1 for final diagnosis
        inputs={
            "initial_problem": session.initial_problem[:300],
            "evidence": evidence[:500],
            "probes_summary": probes_summary[:300]
        },
        outputs={
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "recommended_fixes": diagnosis.recommended_fixes[:300]
        }
    )
    
    # Print formatted diagnosis
    context.vprint("\n" + "="*60)
    context.vprint("FINAL DIAGNOSIS")
    context.vprint("="*60)
    context.vprint(f"\nRoot Cause:\n{diagnosis.root_cause}")
    context.vprint(f"\nConfidence: {diagnosis.confidence}")
    context.vprint(f"\nRecommended Fixes:\n{diagnosis.recommended_fixes}")
    if diagnosis.additional_notes:
        context.vprint(f"\nAdditional Notes:\n{diagnosis.additional_notes}")
    context.vprint("\n" + "="*60)
    
    # Mark session as finished
    session.finished_at = datetime.utcnow()
    
    return {
        "diagnosis": {
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "recommended_fixes": diagnosis.recommended_fixes,
            "additional_notes": diagnosis.additional_notes,
        },
        "debug_session": {
            "session_id": session.session_id,
            "initial_problem": session.initial_problem,
            "total_steps": session.current_step,
            "probes_executed": [p.model_dump() for p in session.probe_history],
            "evidence_log": context.evidence_log,
            "final_evidence": evidence,
            "started_at": session.started_at.isoformat(),
            "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        },
        "session_model": session,  # Include the full Pydantic model for advanced use
    }