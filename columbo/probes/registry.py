"""Probe registry and schemas - declarative definitions of all available probes."""

from .container_probes import (
    containers_state_probe,
    container_logs_probe,
    container_exec_probe,
    container_mounts_probe,
    containers_ports_probe,
    container_inspect_probe,
)
from .volume_probes import (
    list_volumes_probe,
    volume_metadata_probe,
    volume_data_inspection_probe,
    volume_file_read_probe,
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


# Probe registry mapping names to functions
probe_registry = {
    "containers_state": containers_state_probe,
    "container_logs": container_logs_probe,
    "container_exec": container_exec_probe,
    "containers_ports": containers_ports_probe,
    "container_inspect": container_inspect_probe,
    "dns_resolution": dns_resolution_probe,
    "tcp_connection": tcp_connection_probe,
    "http_connection": http_connection_probe,
    "config_files_detection": detect_config_files_probe,
    "env_files_parsing": env_files_parsing_probe,
    "docker_compose_parsing": docker_compose_parsing_probe,
    "generic_config_parsing": generic_config_parsing_probe,
    "list_volumes": list_volumes_probe,
    "volume_metadata": volume_metadata_probe,
    "container_mounts": container_mounts_probe,
    "volume_data_inspection": volume_data_inspection_probe,
    "volume_file_read": volume_file_read_probe,
}


# Declarative probe schemas - documents arguments for each probe
PROBE_SCHEMAS = {
    "containers_state": {
        "description": "Check status of all Docker containers (running, stopped, etc.)",
        "args": {},
        "required_args": set(),
        "example": "{}",
    },
    "containers_ports": {
        "description": "Show port mappings for all containers. Critical for identifying port conflicts - reveals which containers are binding to host ports, including containers outside the current project.",
        "args": {},
        "required_args": set(),
        "example": "{}",
    },
    "container_inspect": {
        "description": "Get detailed inspection data for a specific container including state, exit code, error messages, labels, and configuration.",
        "args": {
            "container": "Name of the container to inspect (required)",
        },
        "required_args": {"container"},
        "example": '{"container": "data_processor_dev"}',
    },
    "container_logs": {
        "description": "Retrieve logs from a specific container",
        "args": {
            "container": "Name of the container (required)",
            "tail": "Number of log lines to retrieve (default: 50)",
        },
        "required_args": {"container"},
        "example": '{"container": "api_tests-rag_agent-1", "tail": 100}',
    },
    "container_exec": {
        "description": "Execute a command inside a running container and capture output.",
        "args": {
            "container": "Name of the container (required)",
            "command": "Shell command to run (required). Should be read-only or diagnostic in nature.",
            "tail_chars": "Max characters to keep from stdout/stderr (default: 4000)",
        },
        "required_args": {"container", "command"},
        "example": '{"container": "container_name", "command": "ps aux"}',
    },
    "dns_resolution": {
        "description": "Resolve a hostname to IP addresses",
        "args": {
            "hostname": "Hostname to resolve (required)",
        },
        "required_args": {"hostname"},
        "example": '{"hostname": "localhost"}',
    },
    "tcp_connection": {
        "description": "Test TCP connection to a host and port",
        "args": {
            "host": "Target host (required)",
            "port": "Target port number (required)",
            "timeout": "Connection timeout in seconds (default: 5.0)",
        },
        "required_args": {"host", "port"},
        "example": '{"host": "localhost", "port": 8000}',
    },
    "http_connection": {
        "description": "Test HTTP connection to a URL",
        "args": {
            "url": "Full URL to test (required)",
            "timeout": "Request timeout in seconds (default: 5.0)",
        },
        "required_args": {"url"},
        "example": '{"url": "http://localhost:8000/health"}',
    },
    "config_files_detection": {
        "description": "Scan workspace for configuration files (docker-compose, .env, etc.)",
        "args": {
            "root_path": "Root directory to scan (optional, defaults to workspace root)",
            "max_depth": "Maximum directory depth to scan (default: 3)",
        },
        "required_args": set(),
        "example": '{"max_depth": 3}',
    },
    "env_files_parsing": {
        "description": "Parse .env files to extract environment variables. Auto-discovers config files if needed.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "required_args": set(),
        "example": "{}",
    },
    "docker_compose_parsing": {
        "description": "Parse docker-compose files to extract service definitions. Auto-discovers config files if needed. Note: Volume names are logical and may differ from actual Docker volume names.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "required_args": set(),
        "example": "{}",
    },
    "generic_config_parsing": {
        "description": "Parse generic YAML/JSON config files. Auto-discovers config files if needed.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "required_args": set(),
        "example": "{}",
    },
    "list_volumes": {
        "description": "List all Docker volumes on the system. Useful for discovering named volumes that may contain stale state.",
        "args": {},
        "required_args": set(),
        "example": "{}",
    },
    "volume_metadata": {
        "description": "Retrieve volume metadata including creation time, labels, driver, and mountpoint. Critical for detecting stale volumes. Requires actual Docker volume name.",
        "args": {
            "volume_name": "Name of the volume to inspect (required)",
        },
        "required_args": {"volume_name"},
        "example": '{"volume_name": "s003_data"}',
    },
    "container_mounts": {
        "description": "Show which volumes and bind mounts are attached to a container, including mount paths and read/write status. Returns actual Docker volume names in Source field, which may include project prefixes.",
        "args": {
            "container": "Name of the container to inspect (required)",
        },
        "required_args": {"container"},
        "example": '{"container": "s003_app"}',
    },
    "volume_data_inspection": {
        "description": "List files in a volume directory using a temporary read-only container. Shows file sizes and modification times. Requires actual Docker volume name.",
        "args": {
            "volume_name": "Name of the volume to inspect (required)",
            "sample_path": "Path within the volume to list (default: /)",
            "max_items": "Maximum number of items to list (default: 10)",
        },
        "required_args": {"volume_name"},
        "example": '{"volume_name": "s003_data", "sample_path": "/", "max_items": 20}',
    },
    "volume_file_read": {
        "description": "Read the contents of a specific file from a volume using a temporary read-only container. More constrained than container_exec for file reading. Requires actual Docker volume name.",
        "args": {
            "volume_name": "Name of the volume containing the file (required)",
            "file_path": "Path to the file within the volume, e.g., /schema_version.txt (required)",
            "max_bytes": "Maximum bytes to read from the file (default: 4000)",
        },
        "required_args": {"volume_name", "file_path"},
        "example": '{"volume_name": "s003_data", "file_path": "/schema_version.txt"}',
    },
}


# Declarative probe dependencies - defines prerequisite probes and transformations
PROBE_DEPENDENCIES = {
    "docker_compose_parsing": {
        "requires": "config_files_detection",
        "transform": lambda result: {
            "found_files": [f for f in result.get("found_files", []) 
                           if f.get("type") == "docker_compose"]
        },
        "description": "Requires config files to be detected first, filters to docker-compose files",
    },
    "env_files_parsing": {
        "requires": "config_files_detection",
        "transform": lambda result: {
            "found_files": [f for f in result.get("found_files", []) 
                           if f.get("type") == "environment_variables"]
        },
        "description": "Requires config files to be detected first, filters to .env files",
    },
    "generic_config_parsing": {
        "requires": "config_files_detection",
        "transform": lambda result: {
            "found_files": [f for f in result.get("found_files", []) 
                           if f.get("type") == "generic_config"]
        },
        "description": "Requires config files to be detected first, filters to generic config files",
    },
}
