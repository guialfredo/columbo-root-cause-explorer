"""Volume-related probes for inspecting Docker volumes and their contents."""


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
        
        # Ensure alpine image is available locally
        image_name = "alpine:latest"
        try:
            client.images.pull(image_name)
        except Exception as pull_error:
            return {
                "volume_name": volume_name,
                "sample_path": sample_path,
                "file_listing": None,
                "probe_name": probe_name,
                "error": f"Failed to pull {image_name}: {str(pull_error)}",
                "error_type": "image_pull_error",
            }
        
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
        
        # Ensure alpine image is available locally
        image_name = "alpine:latest"
        try:
            client.images.pull(image_name)
        except Exception as pull_error:
            return {
                "volume_name": volume_name,
                "file_path": file_path,
                "exists": False,
                "file_contents": None,
                "file_size": None,
                "probe_name": probe_name,
                "error": f"Failed to pull {image_name}: {str(pull_error)}",
                "error_type": "image_pull_error",
            }
        
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
