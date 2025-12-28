from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Sequence

from pydantic import BaseModel, Field, field_validator


class ComposeSpec(BaseModel):
    """Specification for a Docker Compose project."""
    
    project_name: str = Field(..., description="Unique project name per run")
    compose_file: Path = Field(..., description="Path to compose.yaml file")
    workdir: Path = Field(..., description="Working directory (scenario folder)")
    env_file: Optional[Path] = Field(None, description="Optional scenario env file")
    profiles: tuple[str, ...] = Field(default_factory=tuple, description="Compose profiles to activate")
    
    class Config:
        frozen = True
        arbitrary_types_allowed = True
    
    @field_validator('compose_file', 'workdir')
    @classmethod
    def validate_path_exists(cls, v: Path, info) -> Path:
        if not v.exists():
            raise ValueError(f"{info.field_name} does not exist: {v}")
        return v
    
    @field_validator('env_file')
    @classmethod
    def validate_env_file(cls, v: Optional[Path]) -> Optional[Path]:
        if v is not None and not v.exists():
            raise ValueError(f"env_file does not exist: {v}")
        return v


def _run(cmd: Sequence[str], cwd: Path, env: dict[str, str], check: bool = True) -> str:
    p = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    out = p.stdout or ""
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{out}")
    return out


def _base_env(extra_env: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = os.environ.copy()
    # Nice defaults for deterministic output and fewer surprises
    env.setdefault("COMPOSE_DOCKER_CLI_BUILD", "1")
    env.setdefault("DOCKER_BUILDKIT", "1")
    if extra_env:
        env.update(extra_env)
    return env


def compose_up(spec: ComposeSpec, *, detach: bool = True, build: bool = True, check: bool = True) -> str:
    cmd = ["docker", "compose", "-p", spec.project_name, "-f", str(spec.compose_file)]
    if spec.env_file:
        cmd += ["--env-file", str(spec.env_file)]
    for prof in spec.profiles:
        cmd += ["--profile", prof]
    cmd += ["up"]
    if detach:
        cmd += ["-d"]
    if build:
        cmd += ["--build"]
    return _run(cmd, cwd=spec.workdir, env=_base_env(), check=check)


def compose_down(spec: ComposeSpec, *, volumes: bool = True) -> str:
    cmd = ["docker", "compose", "-p", spec.project_name, "-f", str(spec.compose_file)]
    if spec.env_file:
        cmd += ["--env-file", str(spec.env_file)]
    for prof in spec.profiles:
        cmd += ["--profile", prof]
    cmd += ["down"]
    if volumes:
        cmd += ["-v"]
    return _run(cmd, cwd=spec.workdir, env=_base_env())


def compose_ps(spec: ComposeSpec) -> str:
    cmd = ["docker", "compose", "-p", spec.project_name, "-f", str(spec.compose_file)]
    if spec.env_file:
        cmd += ["--env-file", str(spec.env_file)]
    cmd += ["ps"]
    return _run(cmd, cwd=spec.workdir, env=_base_env())


def compose_logs(spec: ComposeSpec, *, tail: int = 200) -> str:
    cmd = ["docker", "compose", "-p", spec.project_name, "-f", str(spec.compose_file)]
    if spec.env_file:
        cmd += ["--env-file", str(spec.env_file)]
    cmd += ["logs", "--no-color", "--tail", str(tail)]
    return _run(cmd, cwd=spec.workdir, env=_base_env())
