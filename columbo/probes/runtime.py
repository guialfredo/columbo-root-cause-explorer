"""Runtime utilities for probe execution.

This module provides centralized logic for resolving container references
and invoking probes with proper type conversions. This keeps individual
probes clean and focused on their diagnostic logic.
"""

from typing import Any, Callable, Dict, List, Optional
from docker import DockerClient
from docker.models.containers import Container
from docker.errors import NotFound, APIError

from columbo.schemas import ProbeResult


def resolve_container(
    client: DockerClient,
    containers: List[Container],
    container_ref: str
) -> Optional[Container]:
    """Resolve a container name or ID to a Container object.
    
    This centralizes container lookup logic that was previously duplicated
    across multiple probes. Handles both container names and IDs.
    
    Args:
        client: Docker client instance
        containers: List of available containers (from cache)
        container_ref: Container name or ID to resolve
        
    Returns:
        Container object if found, None otherwise
    """
    # First try direct lookup by name in cached containers
    for container in containers:
        container_id = container.id or ""
        if container.name == container_ref or container_id.startswith(container_ref):
            return container
    
    # Fallback: try client.containers.get() for short IDs or edge cases
    try:
        return client.containers.get(container_ref)
    except (NotFound, APIError):
        return None


def invoke_with_container_resolution(
    probe_func: Callable[..., Any],
    args: Dict[str, Any],
    client: Optional[DockerClient] = None,
    containers: Optional[List[Container]] = None
) -> ProbeResult:
    """Invoke a probe with automatic container resolution.
    
    If the probe expects a Container object but receives a string name/ID,
    this function resolves it automatically. This keeps probe implementations
    clean while allowing the agent to work with strings.
    
    Args:
        probe_func: The probe function to invoke
        args: Dictionary of arguments to pass to the probe
        client: Docker client for container resolution
        containers: List of available containers for resolution
        
    Returns:
        ProbeResult object. If an error occurs (container not found,
        missing client/containers), returns a ProbeResult with success=False
        and error message, consistent with probe guidelines.
    """
    # Make a copy to avoid mutating the original args
    resolved_args = args.copy()
    
    # Check if we need to resolve a container reference
    container_ref = resolved_args.get("container")
    
    if container_ref and isinstance(container_ref, str):
        if client is None or containers is None:
            # Return ProbeResult with error instead of raising exception
            return ProbeResult(
                probe_name=args.get("probe_name", "unknown"),
                success=False,
                error="Container resolution requested but client or containers not provided",
                data={}
            )
        
        resolved_container = resolve_container(client, containers, container_ref)
        if not resolved_container:
            # Return ProbeResult with error instead of raising exception
            return ProbeResult(
                probe_name=args.get("probe_name", "unknown"),
                success=False,
                error=f"Container '{container_ref}' not found",
                data={"available_containers": [c.name for c in containers]}
            )
        
        resolved_args["container"] = resolved_container
    
    # Invoke the probe with resolved arguments
    result = probe_func(**resolved_args)
    
    # If already a ProbeResult, return as-is
    if isinstance(result, ProbeResult):
        return result
    
    # Handle plain dict returns (shouldn't happen with proper probes, but be defensive)
    if isinstance(result, dict):
        return ProbeResult(
            probe_name=result.get("probe_name", args.get("probe_name", "unknown")),
            success=result.get("success", True),
            error=result.get("error"),
            data={k: v for k, v in result.items() if k not in {"probe_name", "success", "error"}}
        )
    
    # Unexpected return type - wrap in error ProbeResult to maintain type contract
    return ProbeResult(
        probe_name=args.get("probe_name", "unknown"),
        success=False,
        error=f"Probe returned unexpected type: {type(result).__name__}. Expected ProbeResult.",
        data={"unexpected_result": str(result)[:200]}
    )
