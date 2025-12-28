"""Example utilities showing how to use the structured Pydantic models.

This demonstrates the benefits of the schema integration:
- Type-safe access to debugging data
- Easy serialization to JSON/files
- Validation and computed properties
"""

from pathlib import Path
import json
from datetime import datetime
from typing import Optional
from columbo.schemas import (
    DebugSession,
    FinalArtifact,
    InvestigationMetadata,
    RootCause,
    ConfidenceLevel,
)


def save_session_to_file(session: DebugSession, output_dir: str = "."):
    """Save a debug session to a JSON file.
    
    Args:
        session: The DebugSession instance
        output_dir: Directory to save the file
    """
    output_path = Path(output_dir) / f"debug_session_{session.session_id}.json"
    
    # Use Pydantic's model_dump for JSON serialization
    session_data = session.model_dump(mode='json')
    
    with open(output_path, 'w') as f:
        json.dump(session_data, f, indent=2, default=str)
    
    print(f"Session saved to: {output_path}")
    return output_path


def load_session_from_file(file_path: str) -> DebugSession:
    """Load a debug session from JSON file.
    
    Args:
        file_path: Path to the saved session file
        
    Returns:
        Reconstructed DebugSession instance
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    # Pydantic handles validation and type conversion
    return DebugSession.model_validate(data)


def generate_session_report(session: DebugSession) -> str:
    """Generate a human-readable report from a session.
    
    Args:
        session: The DebugSession instance
        
    Returns:
        Formatted markdown report
    """
    report = []
    report.append(f"# Debug Session Report: {session.session_id}")
    report.append(f"\n**Session Started:** {session.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    if session.finished_at:
        duration = (session.finished_at - session.started_at).total_seconds()
        report.append(f"**Session Ended:** {session.finished_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        report.append(f"**Total Duration:** {duration:.1f} seconds")
    
    report.append(f"**Steps Used:** {session.current_step}/{session.max_steps}")
    report.append(f"\n## Initial Problem\n\n{session.initial_problem}")
    
    # Probes section
    report.append(f"\n## Probes Executed ({len(session.probe_history)})")
    
    for probe in session.probe_history:
        report.append(f"\n### Step {probe.step}: {probe.probe_name}")
        report.append(f"- **Arguments:** {probe.probe_args}")
        if probe.duration_seconds:
            report.append(f"- **Duration:** {probe.duration_seconds:.2f}s")
        report.append(f"- **Status:** {'✓ Success' if probe.success else '✗ Failed'}")
        
        if probe.error:
            report.append(f"- **Error:** {probe.error}")
        
        # Include probe results for infrastructure debugging
        if probe.result:
            report.append(f"\n**Results:**")
            
            # Handle different probe result types
            if probe.probe_name == "containers_state" and isinstance(probe.result, dict) and "items" in probe.result:
                report.append("\n| Container | Status | Healthy |")
                report.append("|-----------|--------|---------|")
                for item in probe.result.get("items", []):
                    container = item.get("container", "unknown")
                    status = item.get("status", "unknown")
                    healthy = "✓" if item.get("healthy", False) else "✗"
                    report.append(f"| {container} | {status} | {healthy} |")
            
            elif probe.probe_name == "container_logs" and isinstance(probe.result, dict):
                container = probe.result.get("container", "unknown")
                logs = probe.result.get("log_excerpt", "")
                if logs and not probe.result.get("empty", True):
                    report.append(f"\n**Container:** {container}")
                    report.append(f"```\n{logs}\n```")
                else:
                    report.append(f"\n**Container:** {container} - No logs available")
            
            elif probe.probe_name == "container_exec" and isinstance(probe.result, dict):
                container = probe.result.get("container", "unknown")
                command = probe.result.get("command", "")
                exit_code = probe.result.get("exit_code", -1)
                stdout = probe.result.get("stdout_excerpt", "")
                stderr = probe.result.get("stderr_excerpt", "")
                
                report.append(f"\n**Container:** {container}")
                report.append(f"**Command:** `{command}`")
                report.append(f"**Exit Code:** {exit_code}")
                
                if stdout:
                    report.append(f"\n**stdout:**\n```\n{stdout}\n```")
                if stderr:
                    report.append(f"\n**stderr:**\n```\n{stderr}\n```")
            
            elif probe.probe_name == "network_info" and isinstance(probe.result, dict):
                for key, value in probe.result.items():
                    if isinstance(value, (str, int, bool)):
                        report.append(f"- **{key}:** {value}")
                    elif isinstance(value, list):
                        report.append(f"- **{key}:** {', '.join(str(v) for v in value)}")
            
            else:
                # Generic fallback for other probe types
                result_str = json.dumps(probe.result, indent=2)
                # Truncate if too long
                if len(result_str) > 1000:
                    result_str = result_str[:1000] + "\n... [truncated]"
                report.append(f"```json\n{result_str}\n```")
    
    # Findings section
    if session.findings_log:
        report.append(f"\n## Findings ({len(session.findings_log)})")
        
        for finding in session.findings_log:
            icon = "🔴" if finding.severity.value == "critical" else "🟡" if finding.severity.value == "warning" else "🔵"
            report.append(f"\n{icon} **[Step {finding.step}]** {finding.summary}")
            
            if finding.references:
                report.append(f"  - References: {', '.join(finding.references)}")
    
    # Hypotheses section
    if session.active_hypotheses:
        report.append(f"\n## Hypotheses ({len(session.active_hypotheses)})")
        
        for hyp in session.active_hypotheses:
            report.append(f"\n**{hyp.id}** ({hyp.confidence.value} confidence): {hyp.statement}")
            
            if hyp.rationale:
                report.append(f"  - Rationale: {hyp.rationale}")
            
            if hyp.supported_by:
                report.append(f"  - Supported by: {', '.join(hyp.supported_by)}")
            
            if hyp.contradicted_by:
                report.append(f"  - Contradicted by: {', '.join(hyp.contradicted_by)}")
    
    # Root cause section
    if session.final_root_cause:
        report.append(f"\n## Root Cause")
        report.append(f"\n**Confidence:** {session.final_root_cause.confidence.value}")
        report.append(f"\n{session.final_root_cause.statement}")
        
        if session.final_root_cause.proven_by:
            report.append(f"\n**Proven by:**")
            for evidence in session.final_root_cause.proven_by:
                report.append(f"- {evidence}")
        
        if session.final_root_cause.causal_chain:
            report.append(f"\n**Causal Chain:**")
            for i, link in enumerate(session.final_root_cause.causal_chain, 1):
                report.append(f"{i}. {link}")
    
    # Diagnosis section (from stop_reason if no formal root cause)
    elif session.stop_reason:
        report.append(f"\n## Diagnosis")
        report.append(f"\n{session.stop_reason}")
    
    # Session outcome
    report.append(f"\n## Session Outcome")
    if session.is_complete:
        if session.should_stop:
            report.append("- **Status:** ✓ Investigation completed")
            if session.stop_reason:
                report.append(f"- **Reason:** {session.stop_reason}")
        else:
            report.append("- **Status:** ⚠ Investigation incomplete")
    else:
        report.append("- **Status:** ⏸ Investigation in progress")
    
    report.append(f"- **Steps Used:** {session.current_step}/{session.max_steps}")
    report.append(f"- **Steps Remaining:** {session.steps_remaining}")
    
    return "\n".join(report)


def create_final_artifact(
    session: DebugSession,
    root_cause: Optional[RootCause] = None,
    summary: Optional[str] = None
) -> FinalArtifact:
    """Convert a DebugSession into a FinalArtifact for export.
    
    Args:
        session: The DebugSession instance
        root_cause: Optional RootCause (uses session's if not provided)
        summary: Optional human summary
        
    Returns:
        FinalArtifact ready for export
    """
    metadata = InvestigationMetadata(
        run_id=session.session_id,
        created_at=session.started_at,
        tool_version="1.0.0",  # You can make this dynamic
        workspace_root=session.workspace_root,
        agent_backend="dspy + gpt-4",  # Make this configurable
        max_steps=session.max_steps,
        steps_used=session.current_step
    )
    
    artifact = FinalArtifact(
        metadata=metadata,
        initial_problem=session.initial_problem,
        hypotheses=session.active_hypotheses,
        probes=session.probe_history,
        findings=session.findings_log,
        root_cause=root_cause or session.final_root_cause,
        summary=summary
    )
    
    return artifact


def analyze_probe_performance(session: DebugSession) -> dict:
    """Analyze probe execution performance from a session.
    
    Args:
        session: The DebugSession instance
        
    Returns:
        Dictionary with performance metrics
    """
    probes_with_duration = [p for p in session.probe_history if p.duration_seconds]
    
    if not probes_with_duration:
        return {"error": "No timing data available"}
    
    # Filter out None values for safe aggregation
    durations = [p.duration_seconds for p in probes_with_duration if p.duration_seconds is not None]
    
    if not durations:
        return {"error": "No valid timing data available"}
    
    probe_stats = {}
    for probe in session.probe_history:
        name = probe.probe_name
        if name not in probe_stats:
            probe_stats[name] = {
                "count": 0,
                "total_time": 0.0,
                "successes": 0,
                "failures": 0
            }
        
        probe_stats[name]["count"] += 1
        if probe.duration_seconds:
            probe_stats[name]["total_time"] += probe.duration_seconds
        
        if probe.success:
            probe_stats[name]["successes"] += 1
        else:
            probe_stats[name]["failures"] += 1
    
    # Calculate averages
    for stats in probe_stats.values():
        if stats["count"] > 0:
            stats["avg_time"] = stats["total_time"] / stats["count"]
    
    return {
        "total_probes": len(session.probe_history),
        "total_time": sum(durations),
        "avg_time_per_probe": sum(durations) / len(durations),
        "min_time": min(durations),
        "max_time": max(durations),
        "success_rate": len([p for p in session.probe_history if p.success]) / len(session.probe_history),
        "by_probe_type": probe_stats
    }


def find_duplicate_probes(session: DebugSession) -> list:
    """Find any duplicate probe executions (shouldn't happen with signature checking).
    
    Args:
        session: The DebugSession instance
        
    Returns:
        List of duplicate probe groups
    """
    signature_map = {}
    
    for probe in session.probe_history:
        sig = probe.signature or probe.compute_signature()
        
        if sig not in signature_map:
            signature_map[sig] = []
        
        signature_map[sig].append({
            "step": probe.step,
            "probe_name": probe.probe_name,
            "probe_args": probe.probe_args
        })
    
    # Return only signatures that appear more than once
    duplicates = [
        {"signature": sig, "occurrences": probes}
        for sig, probes in signature_map.items() 
        if len(probes) > 1
    ]
    
    return duplicates
