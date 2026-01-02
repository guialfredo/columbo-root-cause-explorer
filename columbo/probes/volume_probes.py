"""Volume-related probes for inspecting Docker volumes and their contents."""

from columbo.schemas import ProbeResult
from .spec import probe


@probe(
    name="list_volumes",
    description="List all Docker volumes on the system. Useful for discovering named volumes that may contain stale state.",
    scope="volume",
    tags={"discovery", "list"},
    args={},
    required_args=set(),
    example="{}"
)
def list_volumes_probe(probe_name: str = "list_volumes") -> ProbeResult:
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

        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "volume_count": len(volume_names),
                "volumes": volume_names,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "volume_count": 0,
                "volumes": [],
            }
        )


@probe(
    name="volume_metadata",
    description="Retrieve volume metadata including creation time, labels, driver, and mountpoint. Critical for detecting stale volumes. Requires actual Docker volume name.",
    scope="volume",
    tags={"metadata", "state"},
    args={
        "volume_name": "Name of the volume to inspect (required)"
    },
    required_args={"volume_name"},
    example='{"volume_name": "s003_data"}'
)
def volume_metadata_probe(volume_name: str, probe_name: str = "volume_metadata") -> ProbeResult:
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

        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "volume_name": volume_name,
                "created_at": created_at,
                "labels": labels,
                "driver": driver,
                "mountpoint": mountpoint,
                "volume_attrs": volume_attrs,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "volume_name": volume_name,
                "volume_attrs": None,
            }
        )


@probe(
    name="volume_data_inspection",
    description="List files in a volume directory using a temporary read-only container. Shows file sizes and modification times. Requires actual Docker volume name.",
    scope="volume",
    tags={"inspection", "files"},
    args={
        "volume_name": "Name of the volume to inspect (required)",
        "sample_path": "Path within the volume to list (default: /)",
        "max_items": "Maximum number of items to list (default: 10)"
    },
    required_args={"volume_name"},
    example='{"volume_name": "s003_data", "sample_path": "/", "max_items": 20}'
)
def volume_data_inspection_probe(
    volume_name: str,
    sample_path: str = "/",
    max_items: int = 10,
    probe_name: str = "volume_data_inspection",
) -> ProbeResult:
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
        
        # Ensure alpine image is available locally
        image_name = "alpine:latest"
        try:
            client.images.pull(image_name)
        except Exception as pull_error:
            return ProbeResult(
                probe_name=probe_name,
                success=False,
                error=f"Failed to pull {image_name}: {str(pull_error)}",
                data={
                    "volume_name": volume_name,
                    "sample_path": sample_path,
                    "file_listing": None,
                }
            )
        
        volume = client.volumes.get(volume_name)

        # Create a temporary container to inspect the volume's contents
        temp_container = client.containers.create(
            image=image_name,
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

        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "volume_name": volume_name,
                "sample_path": sample_path,
                "file_listing": output,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "volume_name": volume_name,
                "sample_path": sample_path,
                "file_listing": None,
            }
        )
    finally:
        # Ensure cleanup even on error
        if temp_container:
            try:
                temp_container.stop(timeout=1)
                temp_container.remove()
            except Exception:
                pass  # Best effort cleanup


@probe(
    name="volume_file_read",
    description="Read the contents of a specific file from a volume using a temporary read-only container. More constrained than container_exec for file reading. Requires actual Docker volume name.",
    scope="volume",
    tags={"files", "read"},
    args={
        "volume_name": "Name of the volume containing the file (required)",
        "file_path": "Path to the file within the volume, e.g., /schema_version.txt (required)",
        "max_bytes": "Maximum bytes to read from the file (default: 4000)"
    },
    required_args={"volume_name", "file_path"},
    example='{"volume_name": "s003_data", "file_path": "/schema_version.txt"}'
)
def volume_file_read_probe(
    volume_name: str,
    file_path: str,
    max_bytes: int = 4000,
    probe_name: str = "volume_file_read",
) -> ProbeResult:
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
        
        # Ensure alpine image is available locally
        image_name = "alpine:latest"
        try:
            client.images.pull(image_name)
        except Exception as pull_error:
            return ProbeResult(
                probe_name=probe_name,
                success=False,
                error=f"Failed to pull {image_name}: {str(pull_error)}",
                data={
                    "volume_name": volume_name,
                    "file_path": file_path,
                    "exists": False,
                    "file_contents": None,
                    "file_size": None,
                }
            )
        
        volume = client.volumes.get(volume_name)

        # Create a temporary container to read the volume's file
        temp_container = client.containers.create(
            image=image_name,
            command="sleep 10",
            volumes={volume.name: {"bind": "/mnt", "mode": "ro"}},
        )
        temp_container.start()

        # Check if file exists first (use test command with argument list)
        check_log = temp_container.exec_run(["test", "-f", f"/mnt{file_path}"])
        # test returns 0 if file exists, non-zero otherwise
        exists_check = "exists" if check_log.exit_code == 0 else "missing"
        
        if exists_check != "exists":
            return ProbeResult(
                probe_name=probe_name,
                success=True,
                data={
                    "volume_name": volume_name,
                    "file_path": file_path,
                    "exists": False,
                    "file_contents": None,
                    "file_size": None,
                }
            )

        # Get file size using argument list to prevent shell injection
        size_log = temp_container.exec_run(["wc", "-c", f"/mnt{file_path}"])
        # wc outputs "count filename", extract just the count
        size_output = size_log.output.decode("utf-8", errors="replace").strip()
        file_size = int(size_output.split()[0])

        # Read file contents (with size limit) using argument list
        exec_log = temp_container.exec_run(["head", "-c", str(max_bytes), f"/mnt{file_path}"])
        contents = exec_log.output.decode("utf-8", errors="replace")
        
        truncated = file_size > max_bytes

        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "volume_name": volume_name,
                "file_path": file_path,
                "exists": True,
                "file_contents": contents,
                "file_size": file_size,
                "truncated": truncated,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "volume_name": volume_name,
                "file_path": file_path,
                "exists": False,
                "file_contents": None,
                "file_size": None,
            }
        )
    finally:
        # Ensure cleanup even on error
        if temp_container:
            try:
                temp_container.stop(timeout=1)
                temp_container.remove()
            except Exception:
                pass  # Best effort cleanup


@probe(
    name="inspect_volume_file_permissions",
    description="Inspect file ownership (UID/GID) and permissions in a volume. Critical for diagnosing permission mismatches between volume initialization and container runtime user. Uses ls -ln to show numeric UIDs/GIDs. Volume is inspected at its root - use path_in_volume='/' for volume root, or '/subdir' for subdirectories. Requires actual Docker volume name.",
    scope="volume",
    tags={"permissions", "uid", "security"},
    args={
        "volume_name": "Name of the volume to inspect (required)",
        "path_in_volume": "Path within the volume root to inspect. Use '/' for volume root, '/config' for config subdir, etc. (default: /)"
    },
    required_args={"volume_name"},
    example='{"volume_name": "s005_permission_denied_s005_data", "path_in_volume": "/"}'
)
def inspect_volume_file_permissions(
    volume_name: str,
    path_in_volume: str = "/",
    probe_name: str = "inspect_volume_file_permissions",
) -> ProbeResult:
    """Inspect file ownership and permissions within a Docker volume.
    
    Creates a temporary read-only Alpine container to examine the UID/GID
    ownership and permission bits of files/directories in a volume.
    
    Critical for diagnosing permission-related issues like:
    - Volume files owned by root (UID 0) but container runs as non-root user
    - Mismatched UID/GID between volume initialization and runtime
    - Write permission denied on directories that appear accessible
    
    Uses `ls -ln` to show numeric UIDs/GIDs rather than symbolic names,
    which is essential for cross-container permission analysis.
    
    IMPORTANT: The volume is mounted at its root. If a container mounts the volume
    at /data, you should use path_in_volume="/" to see the volume root contents,
    or path_in_volume="/subdir" to see a subdirectory within the volume.
    
    Args:
        volume_name: Name of the volume to inspect (required)
        path_in_volume: Path within the volume root to inspect (default: "/" for root).
                       Use "/" to see volume root, "/config" for config subdir, etc.
        probe_name: Identifier for this probe execution
        
    Returns:
        dict: Contains permissions_listing with detailed ownership info (UID, GID, perms).
              Returns None for permissions_listing on error.
    """
    temp_container = None
    try:
        import docker

        client = docker.from_env()
        
        # Ensure alpine image is available locally
        image_name = "alpine:latest"
        try:
            client.images.pull(image_name)
        except Exception as pull_error:
            return ProbeResult(
                probe_name=probe_name,
                success=False,
                error=f"Failed to pull {image_name}: {str(pull_error)}",
                data={
                    "volume_name": volume_name,
                    "path_in_volume": path_in_volume,
                    "permissions_listing": None,
                }
            )
        
        volume = client.volumes.get(volume_name)

        # Create a temporary container to inspect permissions
        temp_container = client.containers.create(
            image=image_name,
            command="sleep 10",
            volumes={volume.name: {"bind": "/mnt", "mode": "ro"}},
        )
        temp_container.start()

        # Use ls -ln to show numeric UIDs/GIDs (critical for permission diagnosis)
        # -l: long format, -n: numeric IDs, -a: show hidden files
        exec_log = temp_container.exec_run(["ls", "-lna", f"/mnt{path_in_volume}"])
        permissions_output = exec_log.output.decode("utf-8", errors="replace")

        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "volume_name": volume_name,
                "path_in_volume": path_in_volume,
                "permissions_listing": permissions_output,
            }
        )
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "volume_name": volume_name,
                "path_in_volume": path_in_volume,
                "permissions_listing": None,
            }
        )
    finally:
        # Ensure cleanup even on error
        if temp_container:
            try:
                temp_container.stop(timeout=1)
                temp_container.remove()
            except Exception:
                pass  # Best effort cleanup


