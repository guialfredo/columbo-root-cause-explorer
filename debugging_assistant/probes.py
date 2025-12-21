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
        "environment.yaml": "generic_config",
        "environment.yml": "generic_config",
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
    """Parse .env files to extract environment variables.
    
    Args:
        found_files: List of dicts with 'absolute_path' keys pointing to .env files
        probe_name: Name of the probe for identification
    
    Returns:
        dict: Contains parsed environment variables from each .env file
    """
    parsed_envs = []
    
    for file_info in found_files:
        path = file_info.get("absolute_path")
        if not path or not Path(path).is_file():
            continue
        
        env_vars = {}
        try:
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
                "variables": env_vars,
                "variable_count": len(env_vars),
                "parsed": True,
            })
        
        except Exception as e:
            parsed_envs.append({
                "file_path": path,
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
}


# Declarative probe schemas - documents arguments for each probe
PROBE_SCHEMAS = {
    "containers_state": {
        "description": "Check status of all Docker containers (running, stopped, etc.)",
        "args": {},
        "example": "{}",
    },
    "container_logs": {
        "description": "Retrieve logs from a specific container",
        "args": {
            "container": "Name of the container (required)",
            "tail": "Number of log lines to retrieve (default: 50)",
        },
        "example": '{"container": "api_tests-rag_agent-1", "tail": 100}',
    },
    "container_exec": {
        "description": "Execute a command inside a running container and capture output.",
        "args": {
            "container": "Name of the container (required)",
            "command": "Shell command to run (required). Should be read-only or diagnostic in nature.",
            "tail_chars": "Max characters to keep from stdout/stderr (default: 4000)",
        },
        "example": '{"container": "container_name", "command": "ps aux"}',
    },
    "dns_resolution": {
        "description": "Resolve a hostname to IP addresses",
        "args": {
            "hostname": "Hostname to resolve (required)",
        },
        "example": '{"hostname": "localhost"}',
    },
    "tcp_connection": {
        "description": "Test TCP connection to a host and port",
        "args": {
            "host": "Target host (required)",
            "port": "Target port number (required)",
            "timeout": "Connection timeout in seconds (default: 5.0)",
        },
        "example": '{"host": "localhost", "port": 8000}',
    },
    "http_connection": {
        "description": "Test HTTP connection to a URL",
        "args": {
            "url": "Full URL to test (required)",
            "timeout": "Request timeout in seconds (default: 5.0)",
        },
        "example": '{"url": "http://localhost:8000/health"}',
    },
    "config_files_detection": {
        "description": "Scan workspace for configuration files (docker-compose, .env, etc.)",
        "args": {
            "root_path": "Root directory to scan (optional, defaults to workspace root)",
            "max_depth": "Maximum directory depth to scan (default: 3)",
        },
        "example": '{"max_depth": 3}',
    },
    "env_files_parsing": {
        "description": "Parse .env files to extract environment variables. Auto-discovers config files if needed.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "example": "{}",
    },
    "docker_compose_parsing": {
        "description": "Parse docker-compose files to extract service definitions. Auto-discovers config files if needed.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "example": "{}",
    },
    "generic_config_parsing": {
        "description": "Parse generic YAML/JSON config files. Auto-discovers config files if needed.",
        "args": {
            "found_files": "Optional: list from config_files_detection. Will auto-discover if not provided.",
        },
        "example": "{}",
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