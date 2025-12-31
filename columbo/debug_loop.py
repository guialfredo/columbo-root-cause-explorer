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
from columbo.schemas import (
    DebugSession,
    ProbeCall,
    Finding,
    Hypothesis,
    ConfidenceLevel,
    Severity,
)
from pathlib import Path
import uuid
from typing import Dict, Any, Optional, List


# Module-level verbose flag and print function
_VERBOSE = True

def vprint(*args, **kwargs):
    """Verbose print - only prints if verbose mode is enabled."""
    if _VERBOSE:
        print(*args, **kwargs)


class ContainerCache:
    """Cache for Docker containers to avoid repeated discovery."""
    def __init__(self):
        self.containers = None
        self.client = None
        self.discovered = False
    
    def discover(self):
        """Discover all Docker containers on the local system."""
        if self.discovered:
            return self.containers, self.client
        
        try:
            self.client = docker.from_env()
            self.containers = self.client.containers.list(all=True)
            self.discovered = True
            vprint(f"Discovered {len(self.containers)} Docker containers")
        except Exception as e:
            vprint(f"Error connecting to Docker: {e}")
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
    workspace_root: Optional[str]
) -> dict:
    """Resolve dependencies for a probe using declarative configuration.
    
    Args:
        probe_name: Name of the probe being executed
        args: Current arguments for the probe
        probe_results_cache: Cache of previous probe results
        workspace_root: Workspace root path
        
    Returns:
        dict: Updated arguments with resolved dependencies
    """
    if probe_name not in PROBE_DEPENDENCIES:
        return args
    
    dep_config = PROBE_DEPENDENCIES[probe_name]
    required_probe = dep_config["requires"]
    
    # Check if dependency was already run
    if required_probe not in probe_results_cache:
        vprint(f"  → Dependency '{required_probe}' not found, auto-executing...")
        
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
        vprint(f"  → Auto-executed '{required_probe}'")
    else:
        vprint(f"  → Using cached result from '{required_probe}'")
    
    # Transform the dependency result and merge into args
    cached_result = probe_results_cache[required_probe]
    transformed = dep_config["transform"](cached_result)
    
    file_count = len(transformed.get("found_files", []))
    vprint(f"  → Resolved to {file_count} files")
    
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
    workspace_root: Optional[str] = None
) -> dict:
    """Execute a probe by looking it up in the probe registry.
    
    Args:
        probe_name: Name of the probe to execute
        probe_args_str: JSON string of probe arguments
        container_cache: Cache object that discovers containers on demand
        probe_results_cache: Dictionary storing previous probe results for reference
        workspace_root: Root path of the workspace (for file-related probes)
        
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
    args = resolve_probe_dependencies(probe_name, args, probe_results_cache, workspace_root)
    
    # Validate required arguments are present
    is_valid, error_msg = validate_probe_args(probe_name, args)
    if not is_valid:
        return {
            "error": error_msg,
            "probe_name": probe_name,
            "provided_args": list(args.keys()),
        }
    
    try:
        # Handle different probe types
        if probe_name == "containers_state":
            # Discover containers on demand when this probe is called
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name
                }
            result = probe_func(containers, probe_name=probe_name)
        
        elif probe_name == "containers_ports":
            # Discover containers on demand for port inspection
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name
                }
            result = probe_func(containers, probe_name=probe_name)
        
        elif probe_name == "container_inspect":
            container_name = args.get("container") or args.get("container_name")
            
            if not container_name:
                return {
                    "error": "Missing container name argument",
                    "probe_name": probe_name,
                }
            
            # Discover containers on demand
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name,
                }
            
            # Find the container by name
            target_container = None
            for c in containers:
                if c.name == container_name:
                    target_container = c
                    break
            
            if not target_container:
                return {
                    "error": f"Container '{container_name}' not found",
                    "available_containers": [c.name for c in containers],
                    "probe_name": probe_name,
                }
            
            result = probe_func(target_container, probe_name=probe_name)
            
        elif probe_name == "container_logs":
            container_name = args.get("container") or args.get("container_name")
            tail = args.get("tail", 50)
            
            if not container_name:
                return {
                    "error": "Missing container name argument",
                    "probe_name": probe_name,
                }
            
            # Discover containers on demand
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name,
                }
            
            # Find the container by name
            target_container = None
            for c in containers:
                if c.name == container_name:
                    target_container = c
                    break
            
            if not target_container:
                return {
                    "error": f"Container '{container_name}' not found",
                    "available_containers": [c.name for c in containers],
                    "probe_name": probe_name,
                }
            
            result = probe_func(target_container, tail=tail, probe_name=probe_name)
            
        elif probe_name == "container_exec":
            container_name = args.get("container") or args.get("container_name")
            command = args.get("command")
            
            if not container_name:
                return {
                    "error": "Missing container name argument",
                    "probe_name": probe_name,
                }
            
            if not command:
                return {
                    "error": "Missing command argument",
                    "probe_name": probe_name,
                }
            
            # Discover containers on demand
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name,
                }
            
            # Find the container by name
            target_container = None
            for c in containers:
                if c.name == container_name:
                    target_container = c
                    break
            
            if not target_container:
                return {
                    "error": f"Container '{container_name}' not found",
                    "available_containers": [c.name for c in containers],
                    "probe_name": probe_name,
                }
            
            result = probe_func(target_container, command=command, probe_name=probe_name)
            
        elif probe_name == "container_mounts":
            container_name = args.get("container") or args.get("container_name")
            
            if not container_name:
                return {
                    "error": "Missing container name argument",
                    "probe_name": probe_name,
                }
            
            # Discover containers on demand
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name,
                }
            
            # Find the container by name
            target_container = None
            for c in containers:
                if c.name == container_name:
                    target_container = c
                    break
            
            if not target_container:
                return {
                    "error": f"Container '{container_name}' not found",
                    "available_containers": [c.name for c in containers],
                    "probe_name": probe_name,
                }
            
            result = probe_func(target_container, probe_name=probe_name)
            
        elif probe_name == "inspect_container_runtime_uid":
            container_name = args.get("container") or args.get("container_name")
            
            if not container_name:
                return {
                    "error": "Missing container name argument",
                    "probe_name": probe_name,
                }
            
            # Discover containers on demand
            containers, _ = container_cache.discover()
            if not containers:
                return {
                    "error": "No containers available or failed to connect to Docker",
                    "probe_name": probe_name,
                }
            
            # Find the container by name
            target_container = None
            for c in containers:
                if c.name == container_name:
                    target_container = c
                    break
            
            if not target_container:
                return {
                    "error": f"Container '{container_name}' not found",
                    "available_containers": [c.name for c in containers],
                    "probe_name": probe_name,
                }
            
            result = probe_func(target_container, probe_name=probe_name)
            
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
    verbose: bool = None
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
    global _VERBOSE
    
    # Initialize
    container_cache = ContainerCache()
    
    # Auto-detect verbose mode based on UI presence
    if verbose is None:
        verbose = ui_callback is None
    
    # Set module-level verbose flag
    _VERBOSE = verbose
    
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
    
    # Legacy compatibility - keep these for now
    evidence = initial_evidence
    evidence_log = []  # Keep detailed log of all findings
    probe_results_cache = {}  # Store structured probe results for inter-probe dependencies
    
    vprint(f"Starting debug loop (max {max_steps} steps)...")
    vprint(f"Session ID: {session.session_id}")
    vprint(f"Workspace: {workspace_root}\n")
    
    for step in range(max_steps):
        vprint(f"\n{'='*60}")
        vprint(f"Step {step + 1}/{max_steps}")
        vprint(f"{'='*60}")
        
        # Update UI - new step
        if ui_callback:
            ui_callback.update_step(step + 1)
        
        try:
            # Generate hypotheses
            vprint("\nGenerating hypotheses...")
            if ui_callback:
                ui_callback.update_activity("Generating hypotheses...")
            
            evidence_input = EvidenceInput(evidence=evidence)
            hypotheses_result = hypothesis_gen(evidence_input=evidence_input)
            hypotheses = hypotheses_result.hypotheses_output.hypotheses
            key_unknowns = hypotheses_result.hypotheses_output.key_unknowns
            
            vprint(f"\nHypotheses:\n{hypotheses}")
            vprint(f"\nKey unknowns:\n{key_unknowns}")
            
            # Parse and send hypotheses to UI
            if ui_callback:
                # Parse the hypotheses string into structured data
                hypothesis_list = []
                for line in hypotheses.split('\n'):
                    line = line.strip()
                    if line and (line.startswith('H') or line.startswith('-')):
                        # Try to extract hypothesis parts
                        parts = line.split('|')
                        desc = parts[0].strip()
                        conf = "medium"
                        reason = ""
                        
                        for part in parts[1:]:
                            if 'confidence:' in part.lower():
                                conf = part.split(':')[1].strip()
                            elif 'why:' in part.lower():
                                reason = part.split(':')[1].strip()
                        
                        hypothesis_list.append({
                            "description": desc,
                            "confidence": conf,
                            "reasoning": reason
                        })
                
                ui_callback.update_hypotheses(hypothesis_list)
            
            # Plan next probe
            vprint("\nPlanning next probe...")
            if ui_callback:
                ui_callback.update_activity("Planning diagnostic probe...")
            
            tools_spec = build_tools_spec()
            planning_input = ProbePlanningInput(
                evidence=evidence,
                hypotheses=hypotheses,
                tools_spec=tools_spec
            )
            probe_plan_result = probe_planner(planning_input=planning_input)
            
            probe_name = probe_plan_result.probe_plan.probe_name
            probe_args = probe_plan_result.probe_plan.probe_args
            expected_signal = probe_plan_result.probe_plan.expected_signal
            stop_condition = probe_plan_result.probe_plan.stop_if
            
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
                vprint(f"\n⚠ WARNING: This exact probe has already been executed!")
                vprint(f"   Probe: {probe_name}")
                vprint(f"   Args: {probe_args}")
                vprint(f"   Skipping duplicate and moving to next iteration...\n")
                # Add a note to evidence that the agent tried to repeat
                evidence_log.append(f"[Step {step + 1}] Agent attempted to repeat {probe_name} with same args - skipped")
                continue
            
            vprint(f"\nProbe: {probe_name}")
            vprint(f"Args: {probe_args}")
            vprint(f"Expected signal: {expected_signal}")
            
            # Execute probe
            vprint(f"\nExecuting probe '{probe_name}'...")
            if ui_callback:
                ui_callback.update_activity(f"Executing: {probe_name}")
            
            probe_start = datetime.utcnow()
            
            raw_probe_result = execute_probe(
                probe_name=probe_name,
                probe_args_str=probe_args,
                container_cache=container_cache,
                probe_results_cache=probe_results_cache,
                workspace_root=workspace_root
            )
            
            probe_end = datetime.utcnow()
            
            # Store result in cache for future probes to reference
            probe_results_cache[probe_name] = raw_probe_result
            
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
            
            # Update UI with probe execution
            if ui_callback:
                success = probe_call.error is None
                ui_callback.add_probe_execution(step + 1, probe_name, success)
            
            probe_result_str = format_probe_result(raw_probe_result)
            vprint(f"\nProbe result:\n{probe_result_str[:500]}...")
            if probe_call.duration_seconds:
                vprint(f"Execution time: {probe_call.duration_seconds:.2f}s")
            
            # Digest evidence - create a compact summary of this probe's findings
            vprint("\nDigesting evidence...")
            if ui_callback:
                ui_callback.update_activity("Digesting evidence...")
            prior_evidence_text = "\n".join(evidence_log)
            digest_input = EvidenceDigestInput(
                raw_probe_result=probe_result_str,
                prior_evidence_digest=prior_evidence_text
            )
            evidence_digest_result = evidence_digest(digest_input=digest_input)
            new_finding = evidence_digest_result.digest_output.updated_evidence_digest
            
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
            evidence_log.append(finding_entry)
            
            vprint(f"\nNew finding:\n{new_info}")
            
            # Update UI with latest finding
            if ui_callback:
                ui_callback.update_finding({
                    "summary": new_info,
                    "significance": expected_signal if expected_signal else "N/A"
                })
            
            # Reconstruct full evidence from initial problem + all findings
            all_findings = "\n\n".join(evidence_log)
            
            # Build list of previously executed probes for LLM visibility
            executed_list = []
            for i, exec_probe in enumerate(session.probe_history, 1):
                executed_list.append(f"{i}. {exec_probe.probe_name} - {exec_probe.probe_args}")
            
            probes_summary = "\n".join(executed_list) if executed_list else "None yet"
            
            # Calculate remaining steps for agent awareness
            steps_used = step + 1
            steps_remaining = max_steps - steps_used
            
            evidence = (
                f"{initial_evidence}\n\n"
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
            vprint(f"\nEvaluating whether to stop debugging...")
            if ui_callback:
                ui_callback.update_activity("Evaluating confidence...")
            
            stop_result = stop_decider(
                evidence=evidence,
                hypotheses=hypotheses,
                steps_used=steps_used,
                steps_remaining=steps_remaining
            )
            
            # Access structured output directly
            stop_decision = stop_result.stop_decision
            should_stop = stop_decision.should_stop == "yes"
            
            session.should_stop = should_stop
            session.stop_reason = stop_decision.reasoning
            
            vprint(f"Stop decision: {stop_decision.should_stop}")
            vprint(f"Confidence: {stop_decision.confidence}")
            vprint(f"Reasoning: {stop_decision.reasoning}")
            
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
                vprint("\n✓ Agent decided to stop debugging!")
                break
            
            # Also check if error appears in evidence
            if "error" in raw_probe_result and "Unknown probe" in str(raw_probe_result.get("error", "")):
                vprint(f"\n⚠ Probe execution error, but continuing...")
                
        except Exception as e:
            vprint(f"\n✗ Error in debug loop step {step + 1}: {e}")
            evidence += f"\n\nError in step {step + 1}: {str(e)}"
            # Continue to next iteration
    
    vprint(f"\n\n{'='*60}")
    vprint("Debug loop completed")
    vprint(f"{'='*60}")
    
    # Generate final diagnosis and recommendations
    vprint("\n\nGenerating final diagnosis...")
    probes_summary = "\n".join([
        f"{i}. {p.probe_name} - {p.probe_args}" 
        for i, p in enumerate(session.probe_history, 1)
    ])
    
    diagnosis_result = final_diagnosis(
        initial_problem=initial_evidence,
        evidence=evidence,
        probes_summary=probes_summary
    )
    diagnosis = diagnosis_result.diagnosis_result
    
    # Print formatted diagnosis
    vprint("\n" + "="*60)
    vprint("FINAL DIAGNOSIS")
    vprint("="*60)
    vprint(f"\nRoot Cause:\n{diagnosis.root_cause}")
    vprint(f"\nConfidence: {diagnosis.confidence}")
    vprint(f"\nRecommended Fixes:\n{diagnosis.recommended_fixes}")
    if diagnosis.additional_notes:
        vprint(f"\nAdditional Notes:\n{diagnosis.additional_notes}")
    vprint("\n" + "="*60)
    
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
            "initial_problem": initial_evidence,
            "total_steps": session.current_step,
            "probes_executed": [p.model_dump() for p in session.probe_history],
            "evidence_log": evidence_log,
            "final_evidence": evidence,
            "started_at": session.started_at.isoformat(),
            "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        },
        "session_model": session,  # Include the full Pydantic model for advanced use
    }