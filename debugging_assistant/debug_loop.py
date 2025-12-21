import json
import docker
from debugging_assistant.modules import hypothesis_gen, probe_planner, evidence_digest, stop_decider, final_diagnosis
from debugging_assistant.probes import probe_registry, PROBE_DEPENDENCIES
from pathlib import Path


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
            print(f"Discovered {len(self.containers)} Docker containers")
        except Exception as e:
            print(f"Error connecting to Docker: {e}")
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
    workspace_root: str
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
        print(f"  → Dependency '{required_probe}' not found, auto-executing...")
        
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
        print(f"  → Auto-executed '{required_probe}'")
    else:
        print(f"  → Using cached result from '{required_probe}'")
    
    # Transform the dependency result and merge into args
    cached_result = probe_results_cache[required_probe]
    transformed = dep_config["transform"](cached_result)
    
    file_count = len(transformed.get("found_files", []))
    print(f"  → Resolved to {file_count} files")
    
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
    workspace_root: str = None
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
    
    # Resolve dependencies using declarative configuration
    args = resolve_probe_dependencies(probe_name, args, probe_results_cache, workspace_root)
    
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


def debug_loop(initial_evidence: str, max_steps: int = 10, workspace_root: str = None):
    """Main debugging loop that iterates through hypothesis generation,
    probe planning, execution, and evidence digestion.
    
    Args:
        initial_evidence: Initial problem description or error message
        max_steps: Maximum number of probing steps (default 10)
        workspace_root: Root path of the workspace for file operations
        
    Returns:
        dict: Final debugging results including evidence, hypotheses, and probes executed
    """
    # Initialize
    container_cache = ContainerCache()
    
    if workspace_root is None:
        workspace_root = str(Path.cwd())
    
    # Start with just the initial evidence - no automatic container discovery
    evidence = initial_evidence
    evidence_log = []  # Keep detailed log of all findings
    probes_executed = []
    probe_results_cache = {}  # Store structured probe results for inter-probe dependencies
    executed_probe_signatures = set()  # Track probe+args to prevent repetition
    
    print(f"Starting debug loop (max {max_steps} steps)...")
    print(f"Workspace: {workspace_root}\n")
    
    for step in range(max_steps):
        print(f"\n{'='*60}")
        print(f"Step {step + 1}/{max_steps}")
        print(f"{'='*60}")
        
        try:
            # Generate hypotheses
            print("\nGenerating hypotheses...")
            hypotheses_result = hypothesis_gen(evidence=evidence)
            hypotheses = hypotheses_result.hypotheses
            key_unknowns = getattr(hypotheses_result, 'key_unknowns', 'N/A')
            
            print(f"\nHypotheses:\n{hypotheses}")
            print(f"\nKey unknowns:\n{key_unknowns}")
            
            # Plan next probe
            print("\nPlanning next probe...")
            probe_plan_result = probe_planner(
                evidence=evidence,
                hypotheses=hypotheses
            )
            
            probe_name = probe_plan_result.probe_name
            probe_args = probe_plan_result.probe_args
            expected_signal = probe_plan_result.expected_signal
            stop_condition = probe_plan_result.stop_if
            
            # Check if this exact probe+args combination has been executed before
            probe_signature = f"{probe_name}:{probe_args}"
            if probe_signature in executed_probe_signatures:
                print(f"\n⚠ WARNING: This exact probe has already been executed!")
                print(f"   Probe: {probe_name}")
                print(f"   Args: {probe_args}")
                print(f"   Skipping duplicate and moving to next iteration...\n")
                # Add a note to evidence that the agent tried to repeat
                evidence_log.append(f"[Step {step + 1}] Agent attempted to repeat {probe_name} with same args - skipped")
                continue
            
            # Mark this probe+args as executed
            executed_probe_signatures.add(probe_signature)
            
            print(f"\nProbe: {probe_name}")
            print(f"Args: {probe_args}")
            print(f"Expected signal: {expected_signal}")
            
            # Execute probe
            print(f"\nExecuting probe '{probe_name}'...")
            raw_probe_result = execute_probe(
                probe_name=probe_name,
                probe_args_str=probe_args,
                container_cache=container_cache,
                probe_results_cache=probe_results_cache,
                workspace_root=workspace_root
            )
            
            # Store result in cache for future probes to reference
            probe_results_cache[probe_name] = raw_probe_result
            
            probe_result_str = format_probe_result(raw_probe_result)
            print(f"\nProbe result:\n{probe_result_str[:500]}...")
            
            probes_executed.append({
                "step": step + 1,
                "probe_name": probe_name,
                "probe_args": probe_args,
                "result": raw_probe_result,
            })
            
            # Digest evidence - create a compact summary of this probe's findings
            print("\nDigesting evidence...")
            prior_evidence_text = "\n".join(evidence_log)
            evidence_digest_result = evidence_digest(
                raw_probe_result=probe_result_str,
                prior_evidence_digest=prior_evidence_text
            )
            new_finding = evidence_digest_result.updated_evidence_digest
            
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
            
            print(f"\nNew finding:\n{new_info}")
            
            # Reconstruct full evidence from initial problem + all findings
            all_findings = "\n\n".join(evidence_log)
            
            # Build list of previously executed probes for LLM visibility
            executed_list = []
            for i, exec_probe in enumerate(probes_executed, 1):
                executed_list.append(f"{i}. {exec_probe['probe_name']} - {exec_probe['probe_args']}")
            
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
            print(f"\nEvaluating whether to stop debugging...")
            stop_decision = stop_decider(
                evidence=evidence,
                hypotheses=hypotheses,
                steps_used=steps_used,
                steps_remaining=steps_remaining
            )
            
            should_stop = stop_decision.should_stop.strip().lower()
            reasoning = stop_decision.reasoning
            
            print(f"Stop decision: {should_stop}")
            print(f"Reasoning: {reasoning}")
            
            if should_stop == "yes":
                print("\n✓ Agent decided to stop debugging!")
                break
            
            # Also check if error appears in evidence
            if "error" in raw_probe_result and "Unknown probe" in str(raw_probe_result.get("error", "")):
                print(f"\n⚠ Probe execution error, but continuing...")
                
        except Exception as e:
            print(f"\n✗ Error in debug loop step {step + 1}: {e}")
            evidence += f"\n\nError in step {step + 1}: {str(e)}"
            # Continue to next iteration
    
    print(f"\n\n{'='*60}")
    print("Debug loop completed")
    print(f"{'='*60}")
    
    # Generate final diagnosis and recommendations
    print("\n\nGenerating final diagnosis...")
    probes_summary = "\n".join([
        f"{i}. {p['probe_name']} - {p['probe_args']}" 
        for i, p in enumerate(probes_executed, 1)
    ])
    
    diagnosis = final_diagnosis(
        initial_problem=initial_evidence,
        evidence=evidence,
        probes_summary=probes_summary
    )
    
    # Print formatted diagnosis
    print("\n" + "="*60)
    print("FINAL DIAGNOSIS")
    print("="*60)
    print(f"\nRoot Cause:\n{diagnosis.root_cause}")
    print(f"\nConfidence: {diagnosis.confidence}")
    print(f"\nRecommended Fixes:\n{diagnosis.recommended_fixes}")
    if diagnosis.additional_notes:
        print(f"\nAdditional Notes:\n{diagnosis.additional_notes}")
    print("\n" + "="*60)
    
    return {
        "diagnosis": {
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "recommended_fixes": diagnosis.recommended_fixes,
            "additional_notes": diagnosis.additional_notes,
        },
        "debug_session": {
            "initial_problem": initial_evidence,
            "total_steps": len(probes_executed),
            "probes_executed": probes_executed,
            "evidence_log": evidence_log,
            "final_evidence": evidence,
        }
    }