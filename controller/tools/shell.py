# controller/tools/shell.py
"""
Shell execution tools - run commands in subprocess.
"""
from __future__ import annotations

import os
import subprocess
import shlex
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: Any
    error: str | None = None


# Commands that are always blocked (security)
BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "sudo",
    "chmod 777",
    ":(){:|:&};:",  # fork bomb
    "mkfs",
    "dd if=/dev/zero",
    "curl | sh",
    "wget | sh",
})

# Allowed command prefixes (whitelist approach for safety)
ALLOWED_PREFIXES = frozenset({
    "ls", "cat", "head", "tail", "wc", "grep", "find", "echo",
    "pwd", "cd", "mkdir", "touch", "cp", "mv",
    "python", "python3", "pip", "pytest", "ruff", "mypy",
    "git", "npm", "node", "cargo", "go", "make",
})


def _is_command_allowed(cmd: str) -> tuple[bool, str]:
    """Check if command is allowed to run."""
    cmd_lower = cmd.lower().strip()

    # Block dangerous patterns
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked dangerous command pattern: {blocked}"

    # Check if starts with allowed prefix
    first_word = cmd.split()[0] if cmd.split() else ""
    if first_word not in ALLOWED_PREFIXES:
        return False, f"Command '{first_word}' not in allowed list: {sorted(ALLOWED_PREFIXES)}"

    return True, ""


def run_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    max_output: int = 50_000,
) -> ToolResult:
    """
    Execute a shell command with safety checks.

    Args:
        command: The command to execute
        cwd: Working directory (defaults to current)
        timeout: Max execution time in seconds
        max_output: Max bytes to capture from stdout/stderr

    Returns:
        ToolResult with stdout, stderr, exit code
    """
    # Security check
    ok, err = _is_command_allowed(command)
    if not ok:
        return ToolResult(False, None, err)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout = result.stdout[:max_output] if result.stdout else ""
        stderr = result.stderr[:max_output] if result.stderr else ""

        # Truncation notice
        if result.stdout and len(result.stdout) > max_output:
            stdout += f"\n... (truncated, {len(result.stdout)} total bytes)"
        if result.stderr and len(result.stderr) > max_output:
            stderr += f"\n... (truncated, {len(result.stderr)} total bytes)"

        output = {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

        return ToolResult(
            success=result.returncode == 0,
            output=output,
            error=stderr if result.returncode != 0 else None,
        )

    except subprocess.TimeoutExpired:
        return ToolResult(False, None, f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, None, f"Command execution failed: {e}")


def run_python(
    code: str,
    *,
    timeout: int = 30,
    max_output: int = 50_000,
) -> ToolResult:
    """
    Execute Python code in a subprocess.

    Args:
        code: Python code to execute
        timeout: Max execution time
        max_output: Max output bytes

    Returns:
        ToolResult with execution output
    """
    # Wrap code to be executed via python -c
    escaped_code = code.replace("'", "'\"'\"'")
    cmd = f"python3 -c '{escaped_code}'"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout[:max_output] if result.stdout else ""
        stderr = result.stderr[:max_output] if result.stderr else ""

        return ToolResult(
            success=result.returncode == 0,
            output={"stdout": stdout, "stderr": stderr, "exit_code": result.returncode},
            error=stderr if result.returncode != 0 else None,
        )

    except subprocess.TimeoutExpired:
        return ToolResult(False, None, f"Python execution timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, None, f"Python execution failed: {e}")


# Tool registry
SHELL_TOOLS = {
    "run_command": run_command,
    "run_python": run_python,
}
