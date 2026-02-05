# controller/tools/shell.py
"""
Shell execution tools - run commands in subprocess.

Security Hardening:
- No shell=True - uses shlex.split for safe argument parsing
- Command allowlist with explicit whitelist
- Blocked dangerous patterns and shell launchers
- Environment variable sanitization
- Structured output {exit_code, stdout, stderr, meta}
- Execution timing and resource metrics
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None


# =============================================================================
# SECURITY POLICIES
# =============================================================================

# Dangerous command patterns that are always blocked
BLOCKED_PATTERNS = frozenset(
    {
        "rm -rf /",
        "rm -rf ~",
        "rm -rf .",
        "sudo",
        "chmod 777",
        ":(){:|:&};:",  # fork bomb
        "mkfs",
        "dd if=/dev/zero",
        "dd of=/dev",
        "curl | sh",
        "wget | sh",
        "curl | bash",
        "wget | bash",
        "> /dev/sda",
        "shutdown",
        "reboot",
        "init 0",
        "init 6",
        "kill -9 -1",
        "pkill -9",
        ":(){ :|:& };:",
    }
)

# Blocked regex patterns for more sophisticated detection
BLOCKED_REGEXES = [
    re.compile(r"rm\s+-[rf]+\s+[/~.]", re.IGNORECASE),
    re.compile(r">\s*/dev/", re.IGNORECASE),
    re.compile(r"\|\s*(ba)?sh", re.IGNORECASE),
    re.compile(r"eval\s+", re.IGNORECASE),
    re.compile(r"`.*`"),  # command substitution
    re.compile(r"\$\(.*\)"),  # command substitution
]

# Command allowlist - only these commands are permitted
ALLOWED_COMMANDS = frozenset(
    {
        # Filesystem inspection
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "grep",
        "find",
        "echo",
        "pwd",
        "stat",
        "file",
        "du",
        "df",
        "tree",
        "less",
        "more",
        "diff",
        "sort",
        "uniq",
        "cut",
        "tr",
        "sed",
        "awk",
        # Safe filesystem operations
        "mkdir",
        "touch",
        "cp",
        "mv",
        "ln",
        "rm",
        # Python ecosystem
        "python",
        "python3",
        "pip",
        "pip3",
        "pytest",
        "ruff",
        "mypy",
        "black",
        "isort",
        "flake8",
        "pylint",
        "uv",
        "poetry",
        "pdm",
        # Version control
        "git",
        # Node.js ecosystem
        "npm",
        "npx",
        "node",
        "yarn",
        "pnpm",
        "bun",
        # Other languages
        "cargo",
        "rustc",
        "go",
        "make",
        "cmake",
        # Utilities
        "date",
        "env",
        "printenv",
        "which",
        "whereis",
        "type",
        "tar",
        "gzip",
        "gunzip",
        "zip",
        "unzip",
        "curl",
        "wget",
        "jq",
        "yq",
    }
)

# Shell launchers that are always blocked (even if in allowlist)
BLOCKED_EXECUTABLES = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "fish",
        "dash",
        "ksh",
        "csh",
        "tcsh",
        "powershell",
        "pwsh",
        "cmd",
        "cmd.exe",
        "exec",
        "eval",
        "source",
    }
)

# Environment variables to strip for security
SENSITIVE_ENV_VARS = frozenset(
    {
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GITLAB_TOKEN",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "DATABASE_URL",
        "DB_PASSWORD",
        "SECRET_KEY",
        "API_KEY",
        "PRIVATE_KEY",
        "SSH_PRIVATE_KEY",
        "SSH_AUTH_SOCK",
    }
)


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def _sanitize_environment() -> dict[str, str]:
    """Create a sanitized environment for subprocess execution."""
    env = dict(os.environ)

    # Remove sensitive variables
    for var in SENSITIVE_ENV_VARS:
        env.pop(var, None)

    # Also remove any variable containing these patterns
    sensitive_patterns = ["PASSWORD", "SECRET", "TOKEN", "PRIVATE", "CREDENTIAL"]
    keys_to_remove = [k for k in env if any(p in k.upper() for p in sensitive_patterns)]
    for key in keys_to_remove:
        env.pop(key, None)

    # Set safe defaults
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"

    return env


def _validate_command(cmd: str) -> tuple[bool, str]:
    """
    Validate a command string against security policies.

    Returns:
        (is_valid, error_message)
    """
    if not cmd or not cmd.strip():
        return False, "Empty command"

    cmd_lower = cmd.lower().strip()

    # Check blocked patterns
    for blocked in BLOCKED_PATTERNS:
        if blocked in cmd_lower:
            return False, f"Blocked dangerous pattern: {blocked}"

    # Check blocked regex patterns
    for pattern in BLOCKED_REGEXES:
        if pattern.search(cmd):
            return False, f"Blocked pattern detected: {pattern.pattern}"

    # Parse command to get first word
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return False, f"Invalid command syntax: {e}"

    if not parts:
        return False, "Empty command after parsing"

    # Extract executable name (handle paths like /usr/bin/python)
    first_word = parts[0]
    executable = Path(first_word).name if "/" in first_word else first_word

    # Check if it's a blocked shell launcher
    if executable.lower() in BLOCKED_EXECUTABLES:
        return False, f"Blocked shell launcher: {executable}"

    # Check against allowlist
    if executable not in ALLOWED_COMMANDS:
        return False, (
            f"Command '{executable}' not in allowlist. "
            f"Allowed commands: {sorted(ALLOWED_COMMANDS)[:20]}..."
        )

    # Additional validation for rm command
    if executable == "rm":
        if "-r" in parts and "-f" in parts:
            # Check if targeting dangerous paths
            for arg in parts:
                if arg in ("/", "~", ".", ".."):
                    return False, f"Blocked: rm -rf on dangerous path: {arg}"
                if arg.startswith("/") and arg.count("/") <= 2:
                    return False, f"Blocked: rm -rf on system path: {arg}"

    # Validate git commands
    if executable == "git":
        if len(parts) > 1 and parts[1] in ("push", "remote"):
            # Still allowed but could add additional restrictions
            pass

    return True, ""


def _compute_output_hash(stdout: bytes, stderr: bytes) -> str:
    """Compute a hash of command output for replay verification."""
    content = stdout + b"---STDERR---" + stderr
    return hashlib.sha256(content).hexdigest()[:16]


# =============================================================================
# COMMAND EXECUTION
# =============================================================================


def run_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    max_output: int = 50_000,
    env_override: dict[str, str] | None = None,
) -> ToolResult:
    """
    Execute a command safely in a subprocess.

    Security features:
    - No shell=True (prevents shell injection)
    - Command parsed via shlex.split
    - Only allowlisted commands permitted
    - Dangerous patterns blocked
    - Environment sanitized
    - Output truncated to prevent memory issues

    Args:
        command: Command string to execute (will be parsed via shlex)
        cwd: Working directory (enforced by router to be within workdir)
        timeout: Maximum execution time in seconds
        max_output: Maximum bytes for stdout/stderr (each)
        env_override: Additional environment variables to set

    Returns:
        ToolResult with structured output:
        {
            "exit_code": int,
            "stdout": str,
            "stderr": str,
            "meta": {
                "elapsed_ms": int,
                "output_hash": str,
                "truncated": bool,
                "command_parsed": list[str]
            }
        }
    """
    # Validate command
    ok, err = _validate_command(command)
    if not ok:
        return ToolResult(False, None, err)

    # Parse command
    try:
        argv = shlex.split(command)
    except Exception as e:
        return ToolResult(False, None, f"Command parse failed: {e}")

    if not argv:
        return ToolResult(False, None, "Empty command after parsing")

    # Build environment
    env = _sanitize_environment()
    if env_override:
        env.update(env_override)

    # Execute
    start_time = time.perf_counter()
    truncated = False

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            env=env,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        stdout_b = result.stdout or b""
        stderr_b = result.stderr or b""

        # Compute hash before truncation
        output_hash = _compute_output_hash(stdout_b, stderr_b)

        # Truncate if necessary
        if len(stdout_b) > max_output:
            stdout_b = stdout_b[:max_output] + b"\n... (truncated)"
            truncated = True
        if len(stderr_b) > max_output:
            stderr_b = stderr_b[:max_output] + b"\n... (truncated)"
            truncated = True

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        output = {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "meta": {
                "elapsed_ms": elapsed_ms,
                "output_hash": output_hash,
                "truncated": truncated,
                "command_parsed": argv,
            },
        }

        return ToolResult(
            success=(result.returncode == 0),
            output=output,
            error=(stderr if result.returncode != 0 else None),
        )

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ToolResult(
            False,
            {
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "meta": {"elapsed_ms": elapsed_ms, "timeout": True},
            },
            f"Command timed out after {timeout}s",
        )
    except FileNotFoundError:
        return ToolResult(False, None, f"Command not found: {argv[0]}")
    except PermissionError:
        return ToolResult(False, None, f"Permission denied: {argv[0]}")
    except Exception as e:
        return ToolResult(False, None, f"Command execution failed: {type(e).__name__}: {e}")


def run_python(
    code: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    max_output: int = 50_000,
) -> ToolResult:
    """
    Execute Python code safely in a subprocess.

    The code runs via `python3 -c <code>` with a sanitized environment.
    This is safer than eval() but still allows arbitrary Python execution.

    Security features:
    - No shell=True
    - Sanitized environment (sensitive vars removed)
    - Output truncated
    - Timeout enforced

    Args:
        code: Python code string to execute
        cwd: Working directory (enforced by router)
        timeout: Maximum execution time in seconds
        max_output: Maximum bytes for stdout/stderr

    Returns:
        ToolResult with structured output (same format as run_command)
    """
    if not code or not code.strip():
        return ToolResult(False, None, "Empty code")

    # Basic code validation - block obviously dangerous imports
    dangerous_patterns = [
        re.compile(r"import\s+subprocess", re.IGNORECASE),
        re.compile(r"from\s+subprocess\s+import", re.IGNORECASE),
        re.compile(r"import\s+os\s*;?\s*os\.system", re.IGNORECASE),
        re.compile(r"os\.exec", re.IGNORECASE),
        re.compile(r"os\.spawn", re.IGNORECASE),
        re.compile(r"__import__\s*\(", re.IGNORECASE),
        re.compile(r"eval\s*\(", re.IGNORECASE),
        re.compile(r"exec\s*\(", re.IGNORECASE),
        re.compile(r"compile\s*\(", re.IGNORECASE),
    ]

    for pattern in dangerous_patterns:
        if pattern.search(code):
            return ToolResult(False, None, f"Blocked dangerous pattern in code: {pattern.pattern}")

    argv = ["python3", "-c", code]
    env = _sanitize_environment()

    start_time = time.perf_counter()
    truncated = False

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            env=env,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        stdout_b = result.stdout or b""
        stderr_b = result.stderr or b""

        output_hash = _compute_output_hash(stdout_b, stderr_b)

        if len(stdout_b) > max_output:
            stdout_b = stdout_b[:max_output] + b"\n... (truncated)"
            truncated = True
        if len(stderr_b) > max_output:
            stderr_b = stderr_b[:max_output] + b"\n... (truncated)"
            truncated = True

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        output = {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "meta": {
                "elapsed_ms": elapsed_ms,
                "output_hash": output_hash,
                "truncated": truncated,
                "code_lines": code.count("\n") + 1,
            },
        }

        return ToolResult(
            success=(result.returncode == 0),
            output=output,
            error=(stderr if result.returncode != 0 else None),
        )

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ToolResult(
            False,
            {
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "meta": {"elapsed_ms": elapsed_ms, "timeout": True},
            },
            f"Python execution timed out after {timeout}s",
        )
    except Exception as e:
        return ToolResult(False, None, f"Python execution failed: {type(e).__name__}: {e}")


# =============================================================================
# EXPORTS
# =============================================================================


SHELL_TOOLS = {
    "run_command": run_command,
    "run_python": run_python,
}

# Expose validation for testing
validate_command = _validate_command
sanitize_environment = _sanitize_environment

# Backward compatibility alias
ALLOWED_PREFIXES = ALLOWED_COMMANDS
