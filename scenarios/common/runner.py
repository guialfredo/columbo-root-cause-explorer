from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
import docker

from scenarios.common.docker_compose_utils import ComposeSpec, compose_up, compose_down, compose_ps


class ScenarioManifest(BaseModel):
    """Parsed manifest.json for a scenario."""
    
    scenario_id: str
    name: str
    title: str
    description: str
    difficulty: str
    category: str
    tags: list[str] = Field(default_factory=list)
    services: dict[str, Any] = Field(default_factory=dict)
    expected_root_cause: dict[str, Any] = Field(default_factory=dict)
    debugging_hints: list[str] = Field(default_factory=list)
    expected_solution: str = ""
    max_debug_steps: int = 10
    estimated_time_minutes: int = 15
    learning_objectives: list[str] = Field(default_factory=list)
    initial_evidence: str = ""  # Initial problem description for the debugging agent
    
    class Config:
        frozen = True


class ScenarioRef(BaseModel):
    """Reference to a scenario with paths to key files."""
    
    scenario_id: str = Field(..., description="Scenario identifier (e.g., s001_env_override)")
    scenario_dir: Path = Field(..., description="Root directory of the scenario")
    compose_file: Path = Field(..., description="Path to compose file (compose.yaml or docker-compose.yml)")
    manifest_file: Path = Field(..., description="Path to manifest.json")
    
    class Config:
        frozen = True
        arbitrary_types_allowed = True
    
    @field_validator('scenario_dir', 'compose_file', 'manifest_file')
    @classmethod
    def validate_path_exists(cls, v: Path, info) -> Path:
        if not v.exists():
            raise ValueError(f"{info.field_name} does not exist: {v}")
        return v
    
    def load_manifest(self) -> ScenarioManifest:
        """Load and parse the manifest.json file."""
        data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
        return ScenarioManifest(**data)


def load_scenario(scenarios_root: Path, scenario_id: str) -> ScenarioRef:
    """Load a scenario by ID from the scenarios root directory.
    
    Looks for compose.yaml (preferred) or docker-compose.yml (fallback).
    """
    d = scenarios_root / scenario_id
    if not d.is_dir():
        raise FileNotFoundError(f"Scenario folder not found: {d}")

    # Try both compose.yaml (preferred) and docker-compose.yml (legacy)
    compose_file = d / "compose.yaml"
    if not compose_file.exists():
        compose_file = d / "docker-compose.yml"
        if not compose_file.exists():
            raise FileNotFoundError(
                f"Neither compose.yaml nor docker-compose.yml found in: {d}"
            )

    manifest_file = d / "manifest.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"manifest.json not found for scenario: {manifest_file}")

    return ScenarioRef(
        scenario_id=scenario_id,
        scenario_dir=d,
        compose_file=compose_file,
        manifest_file=manifest_file,
    )


def make_project_name(scenario_id: str) -> str:
    # unique enough; keep it short for docker
    return f"columbo_{scenario_id.lower()}_{int(time.time())}"


def spin_up_scenario(sref: ScenarioRef, *, profiles: tuple[str, ...] = ()) -> ComposeSpec:
    project_name = make_project_name(sref.scenario_id)
    spec = ComposeSpec(
        project_name=project_name,
        compose_file=sref.compose_file,
        workdir=sref.scenario_dir,
        env_file=None,
        profiles=profiles,
    )
    compose_up(spec, detach=True, build=True)
    return spec


def tear_down_scenario(spec: ComposeSpec) -> None:
    compose_down(spec, volumes=True)


def check_port_conflicts(manifest: ScenarioManifest) -> list[dict]:
    """Check if any ports required by the scenario are already in use.
    
    Args:
        manifest: Scenario manifest containing service definitions
        
    Returns:
        List of conflict details with container info and port numbers
    """
    conflicts = []
    
    try:
        client = docker.from_env()
        running_containers = client.containers.list()
        
        # Extract ports from manifest
        required_ports = set()
        for service_name, service_info in manifest.services.items():
            ports = service_info.get("ports", [])
            for port in ports:
                # Handle "6333:6333" or just "6333"
                port_str = str(port).split(":")[0]
                required_ports.add(port_str)
        
        # Check running containers
        for container in running_containers:
            container_ports = container.ports
            for port_binding in container_ports.values():
                if port_binding:
                    for binding in port_binding:
                        host_port = binding.get("HostPort")
                        if host_port in required_ports:
                            conflicts.append({
                                "container_name": container.name,
                                "container_id": container.short_id,
                                "port": host_port,
                                "status": container.status,
                            })
        
    except Exception as e:
        print(f"Warning: Could not check for port conflicts: {e}")
    
    return conflicts


def check_container_name_conflicts(manifest: ScenarioManifest) -> list[dict]:
    """Check if containers with the same names already exist.
    
    Args:
        manifest: Scenario manifest containing service definitions
        
    Returns:
        List of conflict details with container info
    """
    conflicts = []
    
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        # Extract container names from manifest
        required_names = set()
        for service_name, service_info in manifest.services.items():
            container_name = service_info.get("container_name")
            if container_name:
                required_names.add(container_name)
        
        # Check existing containers
        for container in all_containers:
            if container.name in required_names:
                conflicts.append({
                    "container_name": container.name,
                    "container_id": container.short_id,
                    "status": container.status,
                    "created": container.attrs.get("Created", "unknown"),
                })
        
    except Exception as e:
        print(f"Warning: Could not check for container name conflicts: {e}")
    
    return conflicts


def cleanup_conflicting_containers(
    port_conflicts: list[dict],
    name_conflicts: list[dict],
    force: bool = False,
    timeout: int = 5
) -> tuple[list[str], list[str]]:
    """Stop and remove conflicting containers.
    
    Args:
        port_conflicts: List of port conflicts from check_port_conflicts
        name_conflicts: List of name conflicts from check_container_name_conflicts
        force: If True, force kill containers instead of graceful stop
        timeout: Seconds to wait for graceful stop before forcing
        
    Returns:
        Tuple of (successfully_removed, failed_to_remove) container names
    """
    success = []
    failed = []
    
    try:
        client = docker.from_env()
        
        # Collect unique container names
        container_names = set()
        for conflict in port_conflicts + name_conflicts:
            container_names.add(conflict["container_name"])
        
        for container_name in container_names:
            try:
                container = client.containers.get(container_name)
                
                if container.status == "running":
                    if force:
                        print(f"  Killing {container_name}...")
                        container.kill()
                    else:
                        print(f"  Stopping {container_name}...")
                        container.stop(timeout=timeout)
                
                print(f"  Removing {container_name}...")
                container.remove()
                success.append(container_name)
                print(f"  ✓ Removed {container_name}")
                
            except docker.errors.NotFound:
                # Container already gone
                success.append(container_name)
            except Exception as e:
                failed.append(container_name)
                print(f"  ✗ Failed to remove {container_name}: {e}")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
    
    return success, failed


def check_and_resolve_conflicts(
    manifest: ScenarioManifest,
    auto_cleanup: bool = False,
    force: bool = False
) -> bool:
    """Check for conflicts and optionally resolve them.
    
    Args:
        manifest: Scenario manifest to check
        auto_cleanup: If True, automatically cleanup conflicts
        force: If True, force kill containers during cleanup
        
    Returns:
        True if no conflicts or resolved successfully, False otherwise
    """
    port_conflicts = check_port_conflicts(manifest)
    name_conflicts = check_container_name_conflicts(manifest)
    
    if not port_conflicts and not name_conflicts:
        return True
    
    # Report conflicts
    if port_conflicts:
        print("\n⚠️  Port conflicts detected:")
        for conflict in port_conflicts:
            print(f"   - Port {conflict['port']} used by {conflict['container_name']} ({conflict['status']})")
    
    if name_conflicts:
        print("\n⚠️  Container name conflicts detected:")
        for conflict in name_conflicts:
            print(f"   - {conflict['container_name']} ({conflict['status']})")
    
    # Resolve if requested
    if auto_cleanup:
        print("\n🧹 Cleaning up conflicting containers...")
        success, failed = cleanup_conflicting_containers(
            port_conflicts,
            name_conflicts,
            force=force
        )
        
        if failed:
            print(f"\n❌ Failed to cleanup: {', '.join(failed)}")
            return False
        
        print("✓ Cleanup complete")
        return True
    
    # Provide manual instructions
    print("\n❌ Cannot proceed with conflicting containers")
    print("\nOptions:")
    print("  1. Run with auto_cleanup=True to automatically remove conflicts")
    print("  2. Manually stop/remove the conflicting containers:")
    
    unique_names = set()
    for conflict in name_conflicts + port_conflicts:
        unique_names.add(conflict['container_name'])
    
    for name in unique_names:
        print(f"     docker rm -f {name}")
    
    return False
