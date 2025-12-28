from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import re
import subprocess
import os
import stat


from pydantic import BaseModel, Field, field_validator
import docker

from scenarios.common.docker_compose_utils import ComposeSpec, compose_up, compose_down


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
    setup_script: Path | None = Field(None, description="Optional setup script (setup.sh) to run before compose up")
    
    class Config:
        frozen = True
        arbitrary_types_allowed = True
    
    @field_validator('scenario_dir', 'compose_file', 'manifest_file')
    @classmethod
    def validate_path_exists(cls, v: Path, info) -> Path:
        if not v.exists():
            raise ValueError(f"{info.field_name} does not exist: {v}")
        return v
    
    @field_validator('setup_script')
    @classmethod
    def validate_setup_script(cls, v: Path | None) -> Path | None:
        if v is not None and not v.exists():
            raise ValueError(f"setup_script does not exist: {v}")
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

    # Check for optional setup script
    setup_script = d / "setup.sh"
    if not setup_script.exists():
        setup_script = None

    return ScenarioRef(
        scenario_id=scenario_id,
        scenario_dir=d,
        compose_file=compose_file,
        manifest_file=manifest_file,
        setup_script=setup_script,
    )


def make_project_name(scenario_id: str) -> str:
    # unique enough; keep it short for docker
    return f"columbo_{scenario_id.lower()}_{int(time.time())}"


def run_scenario_setup(sref: ScenarioRef) -> None:
    """Execute the scenario's setup script if one exists.
    
    The setup script runs from the scenario directory.
    Ensures script permissions are set before execution.
    Raises RuntimeError if the setup script fails.
    """
    if sref.setup_script is None:
        return
    
    print(f"Running setup script: {sref.setup_script.name}")
    
    # Ensure the setup script is executable
    current_permissions = os.stat(sref.setup_script).st_mode
    if not (current_permissions & stat.S_IXUSR):
        os.chmod(sref.setup_script, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    
    # Also ensure any .sh files in the scenario directory are executable
    for sh_file in sref.scenario_dir.glob("*.sh"):
        current_permissions = os.stat(sh_file).st_mode
        if not (current_permissions & stat.S_IXUSR):
            os.chmod(sh_file, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    
    try:
        result = subprocess.run(
            ["bash", str(sref.setup_script)],
            cwd=sref.scenario_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout)
        print(f"✓ Setup script completed successfully")
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Setup script failed with exit code {e.returncode}"
        if e.stderr:
            error_msg += f"\n{e.stderr}"
        raise RuntimeError(error_msg) from e


def spin_up_scenario(sref: ScenarioRef, *, profiles: tuple[str, ...] = ()) -> ComposeSpec:
    # Run setup script if present (e.g., seeding volumes)
    run_scenario_setup(sref)
    
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


def cleanup_all_columbo_containers(
    force: bool = False,
    timeout: int = 5
) -> tuple[list[str], list[str]]:
    """Stop and remove ALL containers from any Columbo scenario.
    
    Args:
        force: If True, force kill containers instead of graceful stop
        timeout: Seconds to wait for graceful stop before forcing
        
    Returns:
        Tuple of (successfully_removed, failed_to_remove) container names
    """    
    success = []
    failed = []
    
    # Pattern for scenario containers: s001_app, s002_web, s003_app, etc.
    scenario_pattern = re.compile(r'^s\d{3}_')
    
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        # Find all Columbo scenario containers
        columbo_containers = [
            c for c in all_containers 
            if c.labels.get('com.docker.compose.project', '').startswith('columbo_') or
               scenario_pattern.match(c.name.lower())
        ]
        
        if not columbo_containers:
            return success, failed
        
        for container in columbo_containers:
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


def cleanup_columbo_volumes() -> tuple[list[str], list[str]]:
    """Remove all volumes associated with Columbo scenarios.
    
    Removes:
    - Volumes with 'columbo_' prefix (from runner-managed scenarios)
    - Volumes matching pattern 's###_*' (from manual compose runs)
    
    Returns:
        Tuple of (successfully_removed, failed_to_remove) volume names
    """
    import re
    
    success = []
    failed = []
    
    # Pattern for scenario volumes: s001_data, s002_cache, s003_data, etc.
    scenario_pattern = re.compile(r'^s\d{3}_')
    
    try:
        client = docker.from_env()
        all_volumes = client.volumes.list()
        
        # Find Columbo-related volumes
        columbo_volumes = [
            v for v in all_volumes
            if v.name.startswith('columbo_') or scenario_pattern.match(v.name)
        ]
        
        if not columbo_volumes:
            return success, failed
        
        for volume in columbo_volumes:
            try:
                print(f"  Removing volume {volume.name}...")
                volume.remove()
                success.append(volume.name)
                print(f"  ✓ Removed volume {volume.name}")
            except Exception as e:
                failed.append(volume.name)
                print(f"  ✗ Failed to remove volume {volume.name}: {e}")
        
    except Exception as e:
        print(f"Error during volume cleanup: {e}")
    
    return success, failed


def check_and_resolve_conflicts(
    scenario_id: str,
    auto_cleanup: bool = False,
    force: bool = False
) -> bool:
    """Check for existing scenario containers and optionally clean them up.
    
    When auto_cleanup is True, cleans up ALL Columbo scenario containers,
    not just the current scenario.
    
    Args:
        scenario_id: Scenario identifier to check
        auto_cleanup: If True, automatically cleanup ALL existing Columbo containers
        force: If True, force kill containers during cleanup
        
    Returns:
        True if no conflicts or resolved successfully, False otherwise
    """
    import re
    
    # Pattern for scenario containers: s001_app, s002_web, s003_app, etc.
    scenario_pattern = re.compile(r'^s\d{3}_')
    
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)
        
        # Find ALL Columbo scenario containers (not just current scenario)
        all_columbo = [
            c for c in all_containers
            if c.labels.get('com.docker.compose.project', '').startswith('columbo_') or
               scenario_pattern.match(c.name.lower())
        ]
        
        # Find containers specific to this scenario
        current_scenario = [
            c for c in all_columbo
            if scenario_id.lower() in c.name.lower() or
               c.labels.get('com.docker.compose.project', '').startswith(f'columbo_{scenario_id.lower()}')
        ]
        
        # Other scenario containers
        other_scenarios = [c for c in all_columbo if c not in current_scenario]
        
        if not all_columbo:
            return True
        
        # Report existing containers
        if current_scenario:
            print(f"\n⚠️  Found {len(current_scenario)} container(s) from previous runs of {scenario_id}:")
            for container in current_scenario:
                print(f"   - {container.name} ({container.status})")
        
        if other_scenarios:
            print(f"\n⚠️  Found {len(other_scenarios)} container(s) from other scenarios:")
            for container in other_scenarios:
                print(f"   - {container.name} ({container.status})")
        
        # Check for existing volumes
        all_volumes = client.volumes.list()
        volume_pattern = re.compile(r'^s\d{3}_')
        columbo_volumes = [
            v for v in all_volumes
            if v.name.startswith('columbo_') or volume_pattern.match(v.name)
        ]
        
        if columbo_volumes:
            print(f"\n⚠️  Found {len(columbo_volumes)} volume(s) from previous runs:")
            for volume in columbo_volumes:
                print(f"   - {volume.name}")
        
        # Cleanup if requested
        if auto_cleanup:
            print("\n🧹 Cleaning up ALL Columbo scenario containers...")
            success, failed = cleanup_all_columbo_containers(force=force)
            
            if failed:
                print(f"\n❌ Failed to cleanup containers: {', '.join(failed)}")
                return False
            
            print("✓ Container cleanup complete")
            
            # Also cleanup volumes
            if columbo_volumes:
                print("\n🧹 Cleaning up ALL Columbo scenario volumes...")
                vol_success, vol_failed = cleanup_columbo_volumes()
                
                if vol_failed:
                    print(f"\n⚠️  Failed to cleanup some volumes: {', '.join(vol_failed)}")
                    print("Note: Volumes may be in use. Try stopping all containers first.")
                else:
                    print("✓ Volume cleanup complete")
            
            return True
        
        # Provide manual instructions
        print("\n❌ Cannot proceed with existing containers")
        print("\nOptions:")
        print("  1. Run with --cleanup to automatically remove ALL existing scenario containers and volumes")
        print("  2. Manually remove the containers:")
        for container in all_columbo:
            print(f"     docker rm -f {container.name}")
        if columbo_volumes:
            print("  3. Manually remove the volumes:")
            for volume in columbo_volumes:
                print(f"     docker volume rm {volume.name}")
        
        return False
        
    except Exception as e:
        print(f"Warning: Could not check for conflicts: {e}")
        return True  # Proceed anyway
