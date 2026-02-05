# controller/tools/shell.py
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller import config, docker_runner


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: Any
    error: str | None = None


BLOCKED_SUBSTRINGS = frozenset({
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "sudo",
    ":(){:|:&};:",  # fork bomb
    "mkfs",
    "dd if=/dev/zero",
    "curl | sh",
    "wget | sh",
})

ALLOWED_PREFIXES = frozenset({
    "ls", "cat", "head", "tail", "wc", "grep", "find", "echo", "pwd",
    "mkdir", "touch", "cp", "mv",
    "python", "python3", "pip", "pytest", "ruff", "mypy",
    "git", "npm", "node", "cargo", "go", "make",
})

BLOCKED_FIRST_WORDS = frozenset({"sh", "bash", "zsh", "fish", "dash", "ksh", "powershell", "pwsh", "cmd"})

# Commands that commonly accept file/dir path arguments.
PATH_TAKING = frozenset({"cat", "head", "tail", "grep", "find", "cp", "mv", "mkdir", "touch", "git"})


def _is_command_allowed(cmd: str) -> tuple[bool, str]:
    cmd_lower = cmd.lower().strip()

    for blocked in BLOCKED_SUBSTRINGS:
        if blocked in cmd_lower:
            return False, f"Blocked dangerous command pattern: {blocked}"

    parts = cmd.split()
    first_word = parts[0] if parts else ""
    if not first_word:
        return False, "Empty command"

    if first_word in BLOCKED_FIRST_WORDS:
        return False, f"Blocked shell launcher: {first_word}"

    if first_word not in ALLOWED_PREFIXES:
        return False, f"Command '{first_word}' not allowed. Allowed: {sorted(ALLOWED_PREFIXES)}"

    return True, ""


def _looks_like_path(token: str) -> bool:
    if token in ("-", "--"):
        return False
    if token.startswith("-"):
        return False
    if token.startswith("http://") or token.startswith("https://"):
        return False
    # crude but effective: contains a slash or ends with known path-ish suffix
    if "/" in token or token.startswith("."):
        return True
    return False


def _reject_unsafe_paths(argv: list[str], workdir: str) -> tuple[bool, str]:
    """
    Enforce a scoped posture:
      - no absolute paths
      - no '..' traversal
      - for PATH_TAKING commands, any path-like argument must remain within workdir

    This is not a full shell sandbox, but it prevents the common escapes.
    """
    if not argv:
        return False, "Empty argv"

    cmd = argv[0]
    if cmd not in PATH_TAKING:
        return True, ""

    wd = Path(workdir).resolve()

    # Collect candidate path tokens, including flag-values like: git -C PATH, grep -r PATH, etc.
    candidates: list[str] = []
    i = 1
    while i < len(argv):
        tok = argv[i]

        # flag-value pattern: -C PATH, --work-tree PATH, etc.
        if tok in ("-C", "--work-tree", "--git-dir", "--directory"):
            if i + 1 < len(argv):
                candidates.append(argv[i + 1])
                i += 2
                continue

        if _looks_like_path(tok):
            candidates.append(tok)

        i += 1

    for c in candidates:
        # absolute path block
        if os.path.isabs(c):
            return False, f"Absolute paths are blocked for '{cmd}': {c}"

        # traversal block
        parts = Path(c).parts
        if ".." in parts:
            return False, f"Path traversal '..' blocked for '{cmd}': {c}"

        # resolve inside workdir
        try:
            resolved = (wd / c).resolve()
            try:
                ok = resolved.is_relative_to(wd)  # py>=3.9
            except Exception:
                ok = str(resolved).startswith(str(wd))
            if not ok:
                return False, f"Path escapes working directory for '{cmd}': {c}"
        except Exception:
            return False, f"Path check failed for '{cmd}': {c}"

    return True, ""


def run_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    max_output: int = 50_000,
) -> ToolResult:
    """
    Execute an allowlisted command.
    Checks config.RFSN_SHELL_MODE to determine if host (subprocess) or docker execution is used.
    """
    ok, err = _is_command_allowed(command)
    if not ok:
        return ToolResult(False, None, err)

    workdir = cwd or os.getcwd()

    # If in Docker mode, delegate to docker_runner
    if config.get_shell_mode() == config.TestMode.DOCKER:
        # NOTE: path scoping checks (_reject_unsafe_paths) are still good to run
        # but technically Docker provides isolation. We'll run them to enforce hygiene
        # and match host behavior.
        try:
            argv = shlex.split(command)
            ok2, err2 = _reject_unsafe_paths(argv, workdir=workdir)
            if not ok2:
                return ToolResult(False, None, err2)
        except Exception as e:
            return ToolResult(False, None, f"Command parse failed: {e}")

        c_res = docker_runner.run_in_container(
            command,
            worktree=Path(workdir),
            config=config.get_docker_config(),
            timeout_seconds=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}, 
        )
        return ToolResult(
            success=(c_res.exit_code == 0),
            output={
                "exit_code": c_res.exit_code,
                "stdout": c_res.stdout,
                "stderr": c_res.stderr,
                "meta": {
                    "docker": True, 
                    "timed_out": c_res.timed_out
                }
            },
            error=(c_res.stderr if c_res.exit_code != 0 else None)
        )

    # Host execution path
    try:
        argv = shlex.split(command)
    except Exception as e:
        return ToolResult(False, None, f"Command parse failed: {e}")

    if not argv:
        return ToolResult(False, None, "Empty command after parsing")

    ok2, err2 = _reject_unsafe_paths(argv, workdir=workdir)
    if not ok2:
        return ToolResult(False, None, err2)

    try:
        result = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout_b = result.stdout or b""
        stderr_b = result.stderr or b""
        if len(stdout_b) > max_output:
            stdout_b = stdout_b[:max_output] + b"\n... (truncated)"
        if len(stderr_b) > max_output:
            stderr_b = stderr_b[:max_output] + b"\n... (truncated)"

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        output = {"exit_code": result.returncode, "stdout": stdout, "stderr": stderr}
        return ToolResult(success=(result.returncode == 0), output=output, error=(stderr if result.returncode != 0 else None))

    except subprocess.TimeoutExpired:
        return ToolResult(False, None, f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, None, f"Command execution failed: {e}")


def run_python(
    code: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    max_output: int = 50_000,
) -> ToolResult:
    """
    Execute Python code.
    If RFSN_SHELL_MODE=docker, executes inside container.
    """
    workdir = cwd or os.getcwd()

    if config.get_shell_mode() == config.TestMode.DOCKER:
        # Construct command: python3 -c <code>
        # We must carefully quote the code for 'sh -c ...' usage in run_in_container
        # docker_runner effectively does: docker run ... image sh -c command
        # command = python3 -c 'code'
        cmd_str = f"python3 -c {shlex.quote(code)}"
        
        c_res = docker_runner.run_in_container(
            cmd_str,
            worktree=Path(workdir),
            config=config.get_docker_config(),
            timeout_seconds=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        return ToolResult(
            success=(c_res.exit_code == 0),
            output={
                "exit_code": c_res.exit_code,
                "stdout": c_res.stdout,
                "stderr": c_res.stderr,
                "meta": {"docker": True, "timed_out": c_res.timed_out}
            },
            error=(c_res.stderr if c_res.exit_code != 0 else None)
        )

    # Host execution
    argv = ["python3", "-c", code]

    try:
        result = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout_b = result.stdout or b""
        stderr_b = result.stderr or b""
        if len(stdout_b) > max_output:
            stdout_b = stdout_b[:max_output] + b"\n... (truncated)"
        if len(stderr_b) > max_output:
            stderr_b = stderr_b[:max_output] + b"\n... (truncated)"

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        output = {"exit_code": result.returncode, "stdout": stdout, "stderr": stderr}
        return ToolResult(success=(result.returncode == 0), output=output, error=(stderr if result.returncode != 0 else None))

    except subprocess.TimeoutExpired:
        return ToolResult(False, None, f"Python execution timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, None, f"Python execution failed: {e}")


SHELL_TOOLS = {
    "run_command": run_command,
    "run_python": run_python,
}
