"""Utility functions for probe management, validation, and documentation."""

from .registry import probe_registry, PROBE_SCHEMAS


# Argument aliases for normalizing common model variations
ARG_ALIASES = {
    "container_name": "container",
    "cmd": "command",
    "tail_lines": "tail",
    "timeout_s": "timeout",
}


def build_tools_spec():
    """Build comprehensive tools specification from PROBE_SCHEMAS.
    
    Returns formatted markdown string with all probe details for LLM consumption.
    """
    lines = ["# Available Diagnostic Probes\n"]
    
    for name in probe_registry.keys():
        schema = PROBE_SCHEMAS.get(name, {})
        desc = schema.get("description", "")
        args = schema.get("args", {})
        required = sorted(list(schema.get("required_args", set())))
        example = schema.get("example", "{}")
        
        lines.append(f"## {name}")
        lines.append(f"{desc}")
        
        if args:
            lines.append("\n**Arguments:**")
            for arg_name, arg_desc in args.items():
                req_marker = " (REQUIRED)" if arg_name in required else " (optional)"
                lines.append(f"  - `{arg_name}`{req_marker}: {arg_desc}")
        else:
            lines.append("\n**Arguments:** None")
        
        lines.append(f"\n**Example:** `{example}`\n")
    
    return "\n".join(lines)


def get_required_args(probe_name: str) -> set:
    """Get required arguments for a probe.
    
    Args:
        probe_name: Name of the probe
        
    Returns:
        Set of required argument names
    """
    return PROBE_SCHEMAS.get(probe_name, {}).get("required_args", set())


def validate_probe_args(probe_name: str, args: dict) -> tuple[bool, str]:
    """Validate that required arguments are present for a probe.
    
    Args:
        probe_name: Name of the probe
        args: Dictionary of provided arguments
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if probe_name not in PROBE_SCHEMAS:
        return False, f"Unknown probe: {probe_name}"
    
    required = get_required_args(probe_name)
    provided = set(args.keys())
    missing = required - provided
    
    if missing:
        return False, f"Missing required arguments: {sorted(missing)}"
    
    return True, ""


def sanitize_probe_args(probe_name: str, args: dict) -> dict:
    """Sanitize and normalize probe arguments.
    
    - Normalizes argument aliases (e.g., container_name -> container)
    - Filters out non-allowed keys based on schema
    - Removes LLM-provided found_files for config probes (handled by dependency resolver)
    
    Args:
        probe_name: Name of the probe
        args: Dictionary of provided arguments
        
    Returns:
        Sanitized dictionary of arguments
    """
    # normalize aliases
    normalized = {}
    for k, v in (args or {}).items():
        normalized[ARG_ALIASES.get(k, k)] = v

    # keep only allowed keys (if schema exists)
    allowed = set(PROBE_SCHEMAS.get(probe_name, {}).get("args", {}).keys())
    if allowed:
        normalized = {k: v for k, v in normalized.items() if k in allowed}

    # Important: ignore LLM-provided found_files, rely on dependency resolver
    if probe_name in {"env_files_parsing", "docker_compose_parsing", "generic_config_parsing"}:
        normalized.pop("found_files", None)

    return normalized
