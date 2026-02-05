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
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "-v",
        f"{worktree.resolve()}:{config.workdir}",
        "-w",
        config.workdir,
        f"--memory={config.memory_limit}",
        f"--cpus={config.cpu_limit}",
    ]

    if config.network_disabled:
        docker_cmd.append("--network=none")

    # Production security hardening
    docker_cmd.extend([
        # Process limits
        "--pids-limit=128",
        # Filesystem security
        "--read-only",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
        "--tmpfs=/var/tmp:rw,noexec,nosuid,size=32m",
        # Privilege escalation prevention
        "--security-opt=no-new-privileges",
        # Drop all capabilities
        "--cap-drop=ALL",
        # User namespace isolation (run as non-root)
        "--user=65534:65534",
        # Seccomp profile (default Docker seccomp)
        "--security-opt=seccomp=unconfined" if False else "",  # Use default profile
    ])

    # Remove empty strings from cmd
    docker_cmd = [c for c in docker_cmd if c]

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


def run_pytest_in_docker(
    worktree: Path,
    test_command: str = "pytest -v",
    *,
    timeout_seconds: int = 300,
    config: ContainerConfig | None = None,
) -> dict:
    """
    Run pytest in Docker container and return kernel-compatible result.

    Returns dict with keys: returncode, stdout, stderr, meta
    """
    result = run_in_container(
        test_command,
        worktree,
        config=config,
        timeout_seconds=timeout_seconds,
    )

    return {
        "returncode": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "meta": {
            "timed_out": result.timed_out,
            "docker": True,
            "image": (config or ContainerConfig()).image,
        },
    }

