"""Container-related probes for inspecting Docker container states, logs, and execution."""

from typing import List
from docker.models.containers import Container


def containers_state_probe(containers: List[Container], probe_name: str = "containers_state"):
    """Check the status of multiple containers.
    
    Args:
        containers: List of Docker container objects to inspect
        probe_name: Identifier for this probe execution
        
    Returns:
        list: Status information for each container including health status
    """
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
    """Retrieve recent logs from a container.
    
    Args:
        container: Docker container object
        tail: Number of log lines to retrieve (default: 50)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Log excerpt with metadata
    """
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
    """Execute a command inside a running container and capture output.
    
    Args:
        container: Docker container object
        command: Shell command to run (supports pipes and shell operators)
        tail_chars: Maximum characters to keep from stdout/stderr (default: 4000)
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Execution results including exit code, stdout, and stderr
    """
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
