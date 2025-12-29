"""Deterministic probes for inspecting container states and logs.
These probes are designed to be used in debugging scenarios.
They never raise exceptions, because not being able to inspect
is not a failure of the probe itself."""

import socket
import time, requests
from pathlib import Path
import yaml
from typing import List
from docker.models.containers import Container


def containers_state_probe(containers: List[Container], probe_name: str = "containers_state"):
    evidence = []
    for container in containers:
        try:
            status = container.status
            evidence.append(
                {
                    "container": container.name,
                    "status": status,
                    "healthy": status == "running",
                    "probe_name": probe_name,
                }
            )
        except Exception as e:
            evidence.append(
                {
                    "container": getattr(container, "name", "unknown"),
                    "status": "unknown",
                    "healthy": False,
                    "probe_name": probe_name,
                    "error": str(e),
                }
            )
    return evidence


def container_logs_probe(container, tail=50, probe_name: str = "container_logs"):
    try:
        logs = container.logs(tail=tail)

        if isinstance(logs, bytes):
            logs = logs.decode("utf-8", errors="replace")

        return {
            "container": container.name,
            "tail": tail,
            "log_excerpt": logs,
            "empty": len(logs.strip()) == 0,
            "probe_name": probe_name,
        }

    except Exception as e:
        return {
            "container": getattr(container, "name", "unknown"),
            "tail": tail,
            "log_excerpt": None,
            "probe_name": probe_name,
            "error": str(e),
        }


def list_volumes_probe(probe_name: str = "list_volumes"):
    """List all Docker volumes on the local system.
    
    Use this probe to discover what volumes exist, which can help identify:
    - Named volumes that may contain stale state
    - Volumes that should be deleted and recreated
    - Orphaned volumes from previous deployments
    
    Args:
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains volume_count and list of volume names. Returns empty list on error.
    """
    try:
        import docker

        client = docker.from_env()
        volumes = client.volumes.list()
        volume_names = [vol.name for vol in volumes]

        return {
            "volume_count": len(volume_names),
            "volumes": volume_names,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "volume_count": 0,
            "volumes": [],
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def volume_metadata_probe(volume_name: str, probe_name: str = "volume_metadata"):
    """Retrieve detailed metadata for a specific Docker volume.
    
    Critical for diagnosing stale volume issues. Returns:
    - Creation timestamp (to detect old volumes persisting across deployments)
    - Labels (may contain schema version, app version, environment info)
    - Mountpoint, driver, and configuration options
    - Scope and other metadata
    
    Args:
        volume_name: Name of the volume to inspect (required)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains full volume attributes dict plus extracted key fields for easy parsing.
              Returns None for volume_attrs on error (e.g., volume not found).
    """
    try:
        import docker

        client = docker.from_env()
        volume = client.volumes.get(volume_name)
        volume_attrs = volume.attrs
        
        # Extract key fields for easier LLM parsing
        created_at = volume_attrs.get("CreatedAt", "unknown")
        labels = volume_attrs.get("Labels") or {}
        driver = volume_attrs.get("Driver", "unknown")
        mountpoint = volume_attrs.get("Mountpoint", "unknown")

        return {
            "volume_name": volume_name,
            "created_at": created_at,
            "labels": labels,
            "driver": driver,
            "mountpoint": mountpoint,
            "volume_attrs": volume_attrs,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "volume_name": volume_name,
            "volume_attrs": None,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    

def container_mounts_probe(container, probe_name: str = "container_mounts"):
    """Inspect volume and bind mounts attached to a container.
    
    Essential for understanding which volumes a container is using and where they're mounted.
    Helps answer:
    - Which named volume is this container using?
    - Where is the volume mounted inside the container?
    - Is the mount read-only or read-write?
    - Are there bind mounts that might override volume data?
    
    Use this when investigating issues like:
    - Stale volume state causing crashes
    - Configuration files being read from unexpected locations
    - Permission issues with mounted directories
    
    Args:
        container: Docker container object to inspect (required)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains list of mount info with Type, Source, Destination, Mode, RW status.
              Returns empty list on error.
    """
    try:
        mounts = container.attrs.get("Mounts", [])
        mount_info = []
        for m in mounts:
            mount_info.append(
                {
                    "Type": m.get("Type"),  # "volume" or "bind"
                    "Source": m.get("Source"),  # Volume name or host path
                    "Destination": m.get("Destination"),  # Path inside container
                    "Mode": m.get("Mode"),  # e.g., "rw" or "ro"
                    "RW": m.get("RW"),  # Boolean: read-write?
                    "Propagation": m.get("Propagation"),
                }
            )

        return {
            "container": container.name,
            "mounts": mount_info,
            "mount_count": len(mount_info),
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "container": getattr(container, "name", "unknown"),
            "mounts": [],
            "mount_count": 0,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    

def volume_data_inspection_probe(
    volume_name: str,
    sample_path: str = "/",
    max_items: int = 10,
    probe_name: str = "volume_data_inspection",
):
    """Safely inspect the contents of a Docker volume without modifying it.
    
    Creates a temporary read-only Alpine container to peek into volume contents.
    Useful for detecting:
    - Stale schema files from previous app versions
    - Database files with incompatible formats
    - Configuration files with old values
    - File modification times indicating staleness
    
    The inspection is non-destructive (read-only mount) and the temporary
    container is cleaned up automatically.
    
    Args:
        volume_name: Name of the volume to inspect (required)
        sample_path: Path within the volume to list (default: "/" for root)
        max_items: Maximum number of items to list (default: 10)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains file_listing output from ls -lh (includes timestamps, sizes).
              Returns None for file_listing on error.
    """
    temp_container = None
    try:
        import docker

        client = docker.from_env()
        volume = client.volumes.get(volume_name)

        # Create a temporary container to inspect the volume's contents
        temp_container = client.containers.create(
            image="alpine:latest",
            command="sleep 10",
            volumes={volume.name: {"bind": "/mnt", "mode": "ro"}},
        )
        temp_container.start()

        # List files with human-readable sizes and timestamps to detect staleness
        # Use argument list to prevent shell injection via sample_path
        exec_log = temp_container.exec_run(["ls", "-lh", f"/mnt{sample_path}"])
        raw_output = exec_log.output.decode("utf-8", errors="replace")
        
        # Apply max_items limit in Python instead of shell pipe
        lines = raw_output.splitlines()
        output = "\n".join(lines[:max_items]) if max_items > 0 else raw_output

        return {
            "volume_name": volume_name,
            "sample_path": sample_path,
            "file_listing": output,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "volume_name": volume_name,
            "sample_path": sample_path,
            "file_listing": None,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    finally:
        # Ensure cleanup even on error
        if temp_container:
            try:
                temp_container.stop(timeout=1)
                temp_container.remove()
            except Exception:
                pass  # Best effort cleanup


def volume_file_read_probe(
    volume_name: str,
    file_path: str,
    max_bytes: int = 4000,
    probe_name: str = "volume_file_read",
):
    """Read the contents of a specific file from a Docker volume.
    
    Creates a temporary read-only Alpine container to safely read file contents
    from a volume without requiring a running application container. This is more
    constrained and safer than using container_exec for file reading.
    
    Critical for scenarios like:
    - Reading schema version files to detect incompatibility (s003)
    - Reading config files to verify values
    - Reading logs or state files persisted in volumes
    - Confirming file contents match/mismatch application expectations
    
    The operation is non-destructive (read-only mount) and the temporary
    container is cleaned up automatically.
    
    Args:
        volume_name: Name of the volume containing the file (required)
        file_path: Path to the file within the volume, e.g., "/schema_version.txt" (required)
        max_bytes: Maximum bytes to read from the file (default: 4000)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains file_contents as string, file_size, and exists flag.
              Returns None for file_contents if file doesn't exist or on error.
    """
    temp_container = None
    try:
        import docker

        client = docker.from_env()
        volume = client.volumes.get(volume_name)

        # Create a temporary container to read the volume's file
        temp_container = client.containers.create(
            image="alpine:latest",
            command="sleep 10",
            volumes={volume.name: {"bind": "/mnt", "mode": "ro"}},
        )
        temp_container.start()

        # Check if file exists first (use test command with argument list)
        check_log = temp_container.exec_run(["test", "-f", f"/mnt{file_path}"])
        # test returns 0 if file exists, non-zero otherwise
        exists_check = "exists" if check_log.exit_code == 0 else "missing"
        
        if exists_check != "exists":
            return {
                "volume_name": volume_name,
                "file_path": file_path,
                "exists": False,
                "file_contents": None,
                "file_size": None,
                "probe_name": probe_name,
            }

        # Get file size using argument list to prevent shell injection
        size_log = temp_container.exec_run(["wc", "-c", f"/mnt{file_path}"])
        # wc outputs "count filename", extract just the count
        size_output = size_log.output.decode("utf-8", errors="replace").strip()
        file_size = int(size_output.split()[0])

        # Read file contents (with size limit) using argument list
        exec_log = temp_container.exec_run(["head", "-c", str(max_bytes), f"/mnt{file_path}"])
        contents = exec_log.output.decode("utf-8", errors="replace")
        
        truncated = file_size > max_bytes

        return {
            "volume_name": volume_name,
            "file_path": file_path,
            "exists": True,
            "file_contents": contents,
            "file_size": file_size,
            "truncated": truncated,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "volume_name": volume_name,
            "file_path": file_path,
            "exists": False,
            "file_contents": None,
            "file_size": None,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }
    finally:
        # Ensure cleanup even on error
        if temp_container:
            try:
                temp_container.stop(timeout=1)
                temp_container.remove()
            except Exception:
                pass  # Best effort cleanup


def container_exec_probe(
    container,
    command: str,
    tail_chars: int = 4000,
    probe_name: str = "container_exec",
):
    try:
        # Execute with shell to support pipes, redirects, and other shell operators
        # Escape single quotes in the command by replacing ' with '\''
        escaped_command = command.replace("'", "'\\''")
        exec_log = container.exec_run(
            f"sh -c '{escaped_command}'",
            demux=True
        )  # (stdout, stderr)
        stdout_b, stderr_b = exec_log.output if exec_log.output else (b"", b"")

        def _dec(b):
            if not b:
                return ""
            return b.decode("utf-8", errors="replace") if isinstance(b, (bytes, bytearray)) else str(b)

        stdout = _dec(stdout_b)
        stderr = _dec(stderr_b)

        # truncate to keep evidence small
        if len(stdout) > tail_chars:
            stdout = stdout[:tail_chars] + "\n...[truncated]"
        if len(stderr) > tail_chars:
            stderr = stderr[:tail_chars] + "\n...[truncated]"

        return {
            "container": container.name,
            "command": command,
            "exit_code": exec_log.exit_code,
            "success": exec_log.exit_code == 0,
            "stdout_excerpt": stdout,
            "stderr_excerpt": stderr,
            "probe_name": probe_name,
        }

    except Exception as e:
        return {
            "container": getattr(container, "name", "unknown"),
            "command": command,
            "exit_code": None,
            "success": False,
            "stdout_excerpt": "",
            "stderr_excerpt": "",
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def dns_resolution_probe(hostname: str, probe_name: str = "dns_resolution"):
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = sorted({info[4][0] for info in infos})
        return {
            "hostname": hostname,
            "resolved_ips": ips,
            "ok": True,
            "probe_name": probe_name,
        }
    except Exception as e:
        return {
            "hostname": hostname,
            "resolved_ips": [],
            "ok": False,
            "probe_name": probe_name,
            "error": str(e),
        }


def tcp_connection_probe(
    host: str, port: int, timeout: float = 5.0, probe_name: str = "tcp_connection"
):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "ok": True, "probe_name": probe_name}
    except Exception as e:
        return {
            "host": host,
            "port": port,
            "ok": False,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def http_connection_probe(
    url: str, timeout: float = 5.0, probe_name: str = "http_connection"
):
    start = time.time()
    try:
        r = requests.get(url, timeout=timeout)
        elapsed_ms = int((time.time() - start) * 1000)
        text = (r.text or "")[:300]
        ok = 200 <= r.status_code < 300
        return {
            "url": url,
            "status_code": r.status_code,
            "ok": ok,
            "latency_ms": elapsed_ms,
            "body_excerpt": text,
            "probe_name": probe_name,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "url": url,
            "status_code": None,
            "ok": False,
            "latency_ms": elapsed_ms,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def detect_config_files_probe(
    root_path: str | Path,
    probe_name: str = "config_files_detection",
    max_depth: int = 3,
):
    """Detect configuration files commonly used in containerized applications.
    
    Args:
        root_path: Root directory to scan for config files
        probe_name: Name of the probe for identification
        max_depth: Maximum directory depth to scan (default 3)
    
    Returns:
        dict: Contains list of found config files with their paths and types
    """
    # Common config file patterns for containers and environment configuration
    config_patterns = {
        ".env": "environment_variables",
        ".env.*": "environment_variables",
        "environment.yaml": "environment_variables",
        "environment.yml": "environment_variables",
        "docker-compose.yaml": "docker_compose",
        "docker-compose.yml": "docker_compose",
        "docker-compose.*.yaml": "docker_compose",
        "docker-compose.*.yml": "docker_compose",
        "config.yaml": "generic_config",
        "config.yml": "generic_config",
        "config.json": "generic_config",
    }
    
    try:
        root = Path(root_path)
        if not root.exists():
            return {
                "root_path": str(root_path),
                "found_files": [],
                "ok": False,
                "probe_name": probe_name,
                "error": "Root path does not exist",
            }
        
        found_files = []
        scanned_dirs = 0
        
        # Scan directory recursively up to max_depth
        for item in root.rglob("*"):
            try:
                # Calculate depth relative to root
                depth = len(item.relative_to(root).parts) - 1
                if depth > max_depth:
                    continue
                
                if item.is_dir():
                    scanned_dirs += 1
                    continue
                
                # Check if file matches any config pattern
                for pattern, file_type in config_patterns.items():
                    if "*" in pattern:
                        # Handle wildcard patterns
                        if item.match(pattern):
                            found_files.append({
                                "path": str(item.relative_to(root)),
                                "absolute_path": str(item),
                                "type": file_type,
                                "size_bytes": item.stat().st_size,
                                "exists": True,
                            })
                            break
                    else:
                        # Exact filename match
                        if item.name == pattern:
                            found_files.append({
                                "path": str(item.relative_to(root)),
                                "absolute_path": str(item),
                                "type": file_type,
                                "size_bytes": item.stat().st_size,
                                "exists": True,
                            })
                            break
            except (PermissionError, OSError):
                # Skip files/dirs we can't access
                continue
        
        return {
            "root_path": str(root_path),
            "found_files": found_files,
            "count": len(found_files),
            "scanned_dirs": scanned_dirs,
            "max_depth": max_depth,
            "ok": True,
            "probe_name": probe_name,
        }
        
    except Exception as e:
        return {
            "root_path": str(root_path),
            "found_files": [],
            "ok": False,
            "probe_name": probe_name,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def env_files_parsing_probe(found_files, probe_name: str = "env_files_parsing"):
    """Parse environment variable files (.env, environment.yml/yaml) to extract variables.
    
    Args:
        found_files: List of dicts with 'absolute_path' keys pointing to env files
        probe_name: Name of the probe for identification
    
    Returns:
        dict: Contains parsed environment variables from each file
    """
    parsed_envs = []
    
    for file_info in found_files:
        path = file_info.get("absolute_path")
        if not path or not Path(path).is_file():
            continue
        
        env_vars = {}
        file_format = "unknown"
        try:
            file_path = Path(path)
            
            # Determine file format and parse accordingly
            if file_path.suffix in [".yml", ".yaml"]:
                # Parse as YAML
                file_format = "yaml"
                with open(path, "r") as f:
                    content = yaml.safe_load(f)
                    if isinstance(content, dict):
                        # Flatten nested dict to simple key-value pairs
                        env_vars = {str(k): str(v) for k, v in content.items()}
            else:
                # Parse as .env format (KEY=value lines)
                file_format = "dotenv"
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key.strip()] = value.strip().strip('"').strip("'")
            
            parsed_envs.append({
                "file_path": path,
                "file_format": file_format,
                "variables": env_vars,
                "variable_count": len(env_vars),
                "parsed": True,
            })
        
        except Exception as e:
            parsed_envs.append({
                "file_path": path,
                "file_format": file_format,
                "variables": {},
                "variable_count": 0,
                "parsed": False,
                "error": str(e),
                "error_type": type(e).__name__,
            })
    
    return {
        "parsed_env_files": parsed_envs,
        "total_files": len(parsed_envs),
        "probe_name": probe_name,
    }


def docker_compose_parsing_probe(found_files, probe_name: str = "docker_compose_parsing"):
    """Parse docker-compose files to extract service definitions.
    
    Args:
        found_files: List of dicts with 'absolute_path' keys pointing to docker-compose files
        probe_name: Name of the probe for identification
    Returns:
        dict: Contains parsed service definitions from each docker-compose file
    """
    parsed_compose_files = []
    
    for file_info in found_files:
        path = file_info.get("absolute_path")
        if not path or not Path(path).is_file():
            continue
        
        services = {}
        try:
            with open(path, "r") as f:
                content = yaml.safe_load(f)
                services = content.get("services", {})
            
            parsed_compose_files.append({
                "file_path": path,
                "services": services,
                "service_count": len(services),
                "parsed": True,
            })
        
        except Exception as e:
            parsed_compose_files.append({
                "file_path": path,
                "services": {},
                "service_count": 0,
                "parsed": False,
                "error": str(e),
                "error_type": type(e).__name__,
            })
    
    return {
        "parsed_compose_files": parsed_compose_files,
        "total_files": len(parsed_compose_files),
        "probe_name": probe_name,
    }


def generic_config_parsing_probe(found_files, probe_name: str = "generic_config_parsing"):
    """Parse generic configuration files (YAML/JSON) to extract settings.
    
    Args:
        found_files: List of dicts with 'absolute_path' keys pointing to config files
        probe_name: Name of the probe for identification
    
    Returns:
        dict: Contains parsed settings from each config file
    """
    parsed_configs = []
    
    for file_info in found_files:
        path = file_info.get("absolute_path")
        if not path or not Path(path).is_file():
            continue
        
        config_data = None
        parsed = False
        error = None
        
        try:
            with open(path, "r") as f:
                if path.endswith((".yaml", ".yml")):
                    config_data = yaml.safe_load(f)
                elif path.endswith(".json"):
                    import json
                    config_data = json.load(f)
                parsed = True
        
        except Exception as e:
            error = str(e)
        
        parsed_configs.append({
            "file_path": path,
            "config_data": config_data,
            "parsed": parsed,
            "error": error,
        })
    
    return {
        "parsed_config_files": parsed_configs,
        "total_files": len(parsed_configs),
        "probe_name": probe_name,
    }


# Probe registry mapping names to functions
probe_registry = {
    "containers_state": containers_state_probe,
    "container_logs": container_logs_probe,
    "container_exec": container_exec_probe,
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


ARG_ALIASES = {
    # normalize common model variations
    "container_name": "container",
    "cmd": "command",
    "tail_lines": "tail",
    "timeout_s": "timeout",
}

def sanitize_probe_args(probe_name: str, args: dict) -> dict:
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
