"""Probe registry - backward compatibility layer.

This module ensures all probe modules are imported (triggering @probe decorators)
and provides backward-compatible exports derived from the canonical PROBES registry.

New code should import from spec.py (PROBES) directly.
This module exists solely for backward compatibility.
"""

# Import probe modules to trigger @probe decorator registration
# This populates the PROBES dict in spec.py
# NOTE: Must use relative imports to avoid circular dependency with __init__.py
from . import container_probes  # noqa: F401
from . import volume_probes  # noqa: F401
from . import network_probes  # noqa: F401
from . import config_probes  # noqa: F401

# Import the canonical registry
from .spec import PROBES


# Backward compatible probe registry mapping names to functions
# Built from the new PROBES registry
probe_registry = {name: spec.fn for name, spec in PROBES.items()}


# Backward compatible probe schemas
# Built from the new PROBES registry
PROBE_SCHEMAS = {
    name: {
        "description": spec.description,
        "args": spec.args,
        "required_args": spec.required_args,
        "example": spec.example,
    }
    for name, spec in PROBES.items()
}


# Backward compatible probe dependencies
# Built from the new PROBES registry
PROBE_DEPENDENCIES = {
    name: {
        "requires": spec.requires,
        "transform": spec.transform,
        "description": f"Requires {spec.requires} to be executed first",
    }
    for name, spec in PROBES.items()
    if spec.requires is not None
}
