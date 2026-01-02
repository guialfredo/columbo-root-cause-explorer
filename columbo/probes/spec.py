"""Unified probe specification - combines registry, schema, and metadata.

This module defines ProbeSpec, a Pydantic model that unifies:
- Function reference (what to execute)
- Metadata for selection (scope, tags)
- IO contract (arguments, requirements, examples)

The agent reasons about ProbeSpecs, not Python signatures.
"""

from typing import Any, Callable, Dict, Literal, Optional, Set
from pydantic import BaseModel, Field, ConfigDict


class ProbeSpec(BaseModel):
    """Complete specification for a diagnostic probe.
    
    Attributes:
        name: Unique identifier for the probe
        description: Human-readable description of what the probe does
        fn: The actual probe function to execute
        scope: What aspect of the system this probe inspects
        args: Descriptions of each argument (for documentation)
        required_args: Set of argument names that must be provided
        example: Example JSON showing how to call the probe
        tags: Additional categorization tags for probe selection
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)
    
    name: str = Field(..., description="Unique probe identifier")
    description: str = Field(..., description="What this probe does")
    fn: Callable[..., Any] = Field(..., description="The probe function itself")
    
    # Selection metadata
    scope: Literal["container", "volume", "network", "config", "host"] = Field(
        "container",
        description="Primary system aspect this probe inspects"
    )
    tags: Set[str] = Field(
        default_factory=set,
        description="Additional tags for probe selection (e.g., 'logs', 'permissions', 'state')"
    )
    
    # IO contract
    args: Dict[str, str] = Field(
        default_factory=dict,
        description="Argument names mapped to human descriptions"
    )
    required_args: Set[str] = Field(
        default_factory=set,
        description="Set of required argument names"
    )
    example: str = Field(
        default="{}",
        description="JSON example of how to call this probe"
    )
    
    # Optional dependency specification
    requires: Optional[str] = Field(
        None,
        description="Name of probe that must be executed first"
    )
    transform: Optional[Callable[[Dict], Dict]] = Field(
        None,
        description="Function to transform prerequisite probe results into args"
    )


# Global probe registry - populated by @probe decorator
PROBES: Dict[str, ProbeSpec] = {}


def probe(
    name: str,
    description: str,
    scope: Literal["container", "volume", "network", "config", "host"] = "container",
    tags: Optional[Set[str]] = None,
    args: Optional[Dict[str, str]] = None,
    required_args: Optional[Set[str]] = None,
    example: str = "{}",
    requires: Optional[str] = None,
    transform: Optional[Callable[[Dict], Dict]] = None,
):
    """Decorator to register a probe function with its specification.
    
    Usage:
        @probe(
            name="container_logs",
            description="Retrieve logs from a specific container",
            scope="container",
            tags={"logs"},
            args={
                "container": "Name of the container (required)",
                "tail": "Number of log lines to retrieve (default: 50)"
            },
            required_args={"container"},
            example='{"container": "api_tests-rag_agent-1", "tail": 100}'
        )
        def container_logs_probe(container, tail=50, probe_name="container_logs"):
            ...
    
    Args:
        name: Unique probe identifier
        description: Human-readable description
        scope: System aspect this probe inspects
        tags: Additional categorization tags
        args: Argument descriptions
        required_args: Set of required argument names
        example: JSON example
        requires: Optional prerequisite probe name
        transform: Optional transformation function for chaining
    """
    def _register(fn: Callable) -> Callable:
        spec = ProbeSpec(
            name=name,
            description=description,
            fn=fn,
            scope=scope,
            tags=tags or set(),
            args=args or {},
            required_args=required_args or set(),
            example=example,
            requires=requires,
            transform=transform,
        )
        PROBES[name] = spec
        return fn
    return _register
