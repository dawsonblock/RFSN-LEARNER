# controller/tools/sandbox_exec.py
"""
Docker-backed execution tool.

This is the canonical execution path for the agent.
workdir is a HOST path, but the ROUTER MUST force it to context.working_directory.
Do not accept arbitrary mounts here.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from controller.docker_runner import ContainerConfig, ensure_image, run_in_container


def _make_result(success: bool, output: Any, error: str | None = None) -> dict:
    """Create a ToolResult-compatible dict."""
    return {"success": success, "output": output, "error": error}


def sandbox_exec(
    command: str,
    *,
    workdir: str,
    timeout_seconds: int = 300,
    image: str = "python:3.12-slim",
    memory_limit: str = "2g",
    cpu_limit: float = 2.0,
    network_disabled: bool = True,
    env: Mapping[str, str] | None = None,
    max_output: int = 100_000,
) -> dict:
    """
    Docker-backed exec. workdir is a HOST path, but the ROUTER MUST force it
    to context.working_directory. Do not accept arbitrary mounts here.
    """
    host_workdir = Path(workdir).resolve()

    cfg = ContainerConfig(
        image=image,
        memory_limit=memory_limit,
        cpu_limit=float(cpu_limit),
        network_disabled=bool(network_disabled),
        workdir="/workspace",
    )

    try:
        ensure_image(image)
    except Exception:
        pass

    res = run_in_container(
        command,
        host_workdir,
        config=cfg,
        timeout_seconds=int(timeout_seconds),
        env=dict(env) if isinstance(env, dict) else None,
    )

    stdout = res.stdout or ""
    stderr = res.stderr or ""
    if len(stdout) > int(max_output):
        stdout = stdout[: int(max_output)] + "\n... (truncated)"
    if len(stderr) > int(max_output):
        stderr = stderr[: int(max_output)] + "\n... (truncated)"

    out: dict[str, Any] = {
        "returncode": res.exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "meta": {
            "docker": True,
            "timed_out": bool(res.timed_out),
            "config": asdict(cfg),
            "mounted_workdir": str(host_workdir),
        },
    }

    ok = (res.exit_code == 0) and (not res.timed_out)
    err = None
    if not ok:
        err = stderr if stderr else ("Container execution timed out" if res.timed_out else "Container command failed")

    return _make_result(success=ok, output=out, error=err)


SANDBOX_TOOLS = {
    "sandbox_exec": sandbox_exec,
}
