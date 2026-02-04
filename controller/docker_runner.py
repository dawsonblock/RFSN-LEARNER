"""
Docker container lifecycle management for isolated task execution.
"""
from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ContainerResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True)
class ContainerConfig:
    image: str = "python:3.12-slim"
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    network_disabled: bool = True
    workdir: str = "/workspace"


def _docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_in_container(
    command: str,
    worktree: Path,
    *,
    config: ContainerConfig | None = None,
    timeout_seconds: int = 300,
    env: Mapping[str, str] | None = None,
) -> ContainerResult:
    """
    Run a command in a disposable Docker container.
    
    The worktree is mounted read-write at /workspace.
    Network is disabled by default for safety.
    Container is automatically removed after execution.
    """
    if config is None:
        config = ContainerConfig()
    
    container_name = f"rfsn-worker-{uuid.uuid4().hex[:8]}"
    
    docker_cmd = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "-v", f"{worktree.resolve()}:{config.workdir}",
        "-w", config.workdir,
        f"--memory={config.memory_limit}",
        f"--cpus={config.cpu_limit}",
    ]
    
    if config.network_disabled:
        docker_cmd.append("--network=none")
    
    if env:
        for k, v in env.items():
            docker_cmd.extend(["-e", f"{k}={v}"])
    
    docker_cmd.extend([config.image, "sh", "-c", command])
    
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            timeout=timeout_seconds,
            text=True,
        )
        return ContainerResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        # Kill the container on timeout
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        return ContainerResult(
            exit_code=-1,
            stdout="",
            stderr="Container execution timed out",
            timed_out=True,
        )


def ensure_image(image: str) -> bool:
    """Pull Docker image if not present. Returns True if available."""
    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
    )
    if check.returncode == 0:
        return True
    
    pull = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
    )
    return pull.returncode == 0
