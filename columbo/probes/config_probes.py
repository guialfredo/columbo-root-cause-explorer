"""Configuration file detection and parsing probes for containerized applications."""

from pathlib import Path
import yaml

from columbo.schemas import ProbeResult


def detect_config_files_probe(
    root_path: str | Path,
    probe_name: str = "config_files_detection",
    max_depth: int = 3,
) -> ProbeResult:
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
            return ProbeResult(
                probe_name=probe_name,
                success=False,
                error="Root path does not exist",
                data={
                    "root_path": str(root_path),
                    "found_files": [],
                    "ok": False,
                }
            )
        
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
        
        return ProbeResult(
            probe_name=probe_name,
            success=True,
            data={
                "root_path": str(root_path),
                "found_files": found_files,
                "count": len(found_files),
                "scanned_dirs": scanned_dirs,
                "max_depth": max_depth,
                "ok": True,
            }
        )
        
    except Exception as e:
        return ProbeResult(
            probe_name=probe_name,
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            data={
                "root_path": str(root_path),
                "found_files": [],
                "ok": False,
            }
        )


def env_files_parsing_probe(found_files, probe_name: str = "env_files_parsing") -> ProbeResult:
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
            })
    
    return ProbeResult(
        probe_name=probe_name,
        success=True,
        data={
            "parsed_env_files": parsed_envs,
            "total_files": len(parsed_envs),
        }
    )


def docker_compose_parsing_probe(found_files, probe_name: str = "docker_compose_parsing") -> ProbeResult:
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
            })
    
    return ProbeResult(
        probe_name=probe_name,
        success=True,
        data={
            "parsed_compose_files": parsed_compose_files,
            "total_files": len(parsed_compose_files),
        }
    )


def generic_config_parsing_probe(found_files, probe_name: str = "generic_config_parsing") -> ProbeResult:
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
    
    return ProbeResult(
        probe_name=probe_name,
        success=True,
        data={
            "parsed_config_files": parsed_configs,
            "total_files": len(parsed_configs),
        }
    )
