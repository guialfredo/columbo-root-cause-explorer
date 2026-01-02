"""Probe registry and schemas - declarative definitions of all available probes.

This module now maintains backward compatibility while transitioning to ProbeSpec.
New code should use PROBES from spec.py, but probe_registry and PROBE_SCHEMAS
are maintained for compatibility.
"""

from .spec import PROBES
from .container_probes import (
    containers_state_probe,
    container_logs_probe,
    container_exec_probe,
    container_mounts_probe,
    containers_ports_probe,
    container_inspect_probe,
    inspect_container_runtime_uid,
)
from .volume_probes import (
    list_volumes_probe,
    volume_metadata_probe,
    volume_data_inspection_probe,
    volume_file_read_probe,
    inspect_volume_file_permissions,
)
from .network_probes import (
    dns_resolution_probe,
    tcp_connection_probe,
    http_connection_probe,
)
from .config_probes import (
    detect_config_files_probe,
    env_files_parsing_probe,
    docker_compose_parsing_probe,
    generic_config_parsing_probe,
)


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
