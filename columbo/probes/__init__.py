"""Columbo probes package - deterministic container inspection toolkit.

This package provides a modular structure for container, volume, network,
and configuration probes used in debugging containerized systems.
"""

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
from .registry import (
    probe_registry,
    PROBE_SCHEMAS,
    PROBE_DEPENDENCIES,
)
from .utils import (
    build_tools_spec,
    get_required_args,
    validate_probe_args,
    sanitize_probe_args,
    ARG_ALIASES,
)

__all__ = [
    # Container probes
    "containers_state_probe",
    "container_logs_probe",
    "container_exec_probe",
    "container_mounts_probe",
    "containers_ports_probe",
    "container_inspect_probe",
    "inspect_container_runtime_uid",
    # Volume probes
    "list_volumes_probe",
    "volume_metadata_probe",
    "volume_data_inspection_probe",
    "volume_file_read_probe",
    "inspect_volume_file_permissions",
    # Network probes
    "dns_resolution_probe",
    "tcp_connection_probe",
    "http_connection_probe",
    # Config probes
    "detect_config_files_probe",
    "env_files_parsing_probe",
    "docker_compose_parsing_probe",
    "generic_config_parsing_probe",
    # Registry
    "probe_registry",
    "PROBE_SCHEMAS",
    "PROBE_DEPENDENCIES",
    # Utils
    "build_tools_spec",
    "get_required_args",
    "validate_probe_args",
    "sanitize_probe_args",
    "ARG_ALIASES",
]
