# controller/tools/sandbox_exec.py
"""
Unified Docker execution tool.

This is the canonical execution path for the agent.
No host execution should be required for normal operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller.docker_runner import ContainerConfig, run_in_container


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: Any
    error: str | None = None


def sandbox_exec(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = 60,
    memory_mb: int = 512,
    cpu_shares: float = 1.0,
) -> ToolResult:
    """
    Execute command inside Docker sandbox.

    This is the canonical execution path for the agent.
    No host execution should be required for normal operation.

    Args:
        command: Shell command to execute
        cwd: Working directory (mounted to container)
        timeout: Execution timeout in seconds
        memory_mb: Memory limit in MB
        cpu_shares: CPU limit (float)

    Returns:
        ToolResult with exit_code, stdout, stderr
    """
    workdir = Path(cwd) if cwd else Path.cwd()

    config = ContainerConfig(
        image="python:3.12-slim",
        memory_limit=f"{memory_mb}m",
        cpu_limit=cpu_shares,
        network_disabled=True,
    )

    try:
        result = run_in_container(
            command=command,
            worktree=workdir,
            config=config,
            timeout_seconds=timeout,
        )

        return ToolResult(
            success=result.exit_code == 0,
            output={
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": result.timed_out,
                "docker": True,
            },
            error=result.stderr if result.exit_code != 0 else None,
        )

    except Exception as e:
        return ToolResult(False, None, f"sandbox_exec failed: {e}")


SANDBOX_TOOLS = {
    "sandbox_exec": sandbox_exec,
}
