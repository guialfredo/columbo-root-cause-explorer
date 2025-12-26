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
    title: str
    difficulty: str
    category: str
    grading: dict[str, Any] = Field(default_factory=dict)
    budgets: dict[str, int] = Field(default_factory=dict)
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








def cleanup_scenario_containers(
    scenario_id: str,
    force: bool = False,
    timeout: int = 5
) -> tuple[list[str], list[str]]:
    """Stop and remove containers from previous runs of a scenario.
    
    Args:
        scenario_id: The scenario identifier to cleanup
        force: If True, force kill containers instead of graceful stop
        timeout: Seconds to wait for graceful stop before forcing
        
    Returns:
        Tuple of (successfully_removed, failed_to_remove) container names
    """
    success = []
    failed = []
    
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        # Find containers with the scenario label or name pattern
        scenario_containers = [
            c for c in all_containers 
            if scenario_id.lower() in c.name.lower() or 
               c.labels.get('com.docker.compose.project', '').startswith(f'columbo_{scenario_id.lower()}')
        ]
        
        for container in scenario_containers:
            try:
                if container.status == "running":
                    if force:
                        print(f"  Killing {container.name}...")
                        container.kill()
                    else:
                        print(f"  Stopping {container.name}...")
                        container.stop(timeout=timeout)
                
                print(f"  Removing {container.name}...")
                container.remove()
                success.append(container.name)
                print(f"  ✓ Removed {container.name}")
                
            except docker.errors.NotFound:
                success.append(container.name)
            except Exception as e:
                failed.append(container.name)
                print(f"  ✗ Failed to remove {container.name}: {e}")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
    
    return success, failed


def check_and_resolve_conflicts(
    scenario_id: str,
    auto_cleanup: bool = False,
    force: bool = False
) -> bool:
    """Check for existing scenario containers and optionally clean them up.
    
    Args:
        scenario_id: Scenario identifier to check
        auto_cleanup: If True, automatically cleanup existing containers
        force: If True, force kill containers during cleanup
        
    Returns:
        True if no conflicts or resolved successfully, False otherwise
    """
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        # Find containers from previous scenario runs
        existing = [
            c for c in all_containers
            if scenario_id.lower() in c.name.lower() or
               c.labels.get('com.docker.compose.project', '').startswith(f'columbo_{scenario_id.lower()}')
        ]
        
        if not existing:
            return True
        
        # Report existing containers
        print(f"\n⚠️  Found {len(existing)} existing container(s) from previous runs:")
        for container in existing:
            print(f"   - {container.name} ({container.status})")
        
        # Cleanup if requested
        if auto_cleanup:
            print("\n🧹 Cleaning up existing containers...")
            success, failed = cleanup_scenario_containers(
                scenario_id,
                force=force
            )
            
            if failed:
                print(f"\n❌ Failed to cleanup: {', '.join(failed)}")
                return False
            
            print("✓ Cleanup complete")
            return True
        
        # Provide manual instructions
        print("\n❌ Cannot proceed with existing containers")
        print("\nOptions:")
        print("  1. Run with --cleanup to automatically remove existing containers")
        print("  2. Manually remove the containers:")
        for container in existing:
            print(f"     docker rm -f {container.name}")
        
        return False
        
    except Exception as e:
        print(f"Warning: Could not check for conflicts: {e}")
        return True  # Proceed anyway
