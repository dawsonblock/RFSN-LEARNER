# controller/tool_registry.py
"""
Single authoritative tool registry with schemas, budgets, and permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from .tools.browser import BROWSER_TOOLS
from .tools.code import CODE_TOOLS
from .tools.filesystem import FILESYSTEM_TOOLS
from .tools.memory import MEMORY_TOOLS
from .tools.reasoning import REASONING_TOOLS
from .tools.sandbox_exec import SANDBOX_TOOLS
from .tools.shell import SHELL_TOOLS


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Field:
    """Schema field definition."""

    name: str
    required: bool = True
    kind: str = "any"  # "str" | "int" | "bool" | "dict" | "list" | "any"


def _is_kind(v: Any, kind: str) -> bool:
    if kind == "any":
        return True
    if kind == "str":
        return isinstance(v, str)
    if kind == "int":
        return isinstance(v, int)
    if kind == "bool":
        return isinstance(v, bool)
    if kind == "dict":
        return isinstance(v, dict)
    if kind == "list":
        return isinstance(v, list)
    return False


@dataclass(frozen=True)
class Budget:
    """Per-turn budget limits for a tool."""

    calls_per_turn: int
    max_bytes: int | None = None
    max_results: int | None = None


@dataclass(frozen=True)
class PermissionRule:
    """
    Permission controls for tools.
    - restrict_paths_to_workdir: file paths must be within working_directory
    - require_explicit_grant: tool blocked unless caller grants permission
    - deny_in_replay: tool blocked during replay mode (for write/destructive ops)
    - mutates: tool has side effects (writes, executes, deletes)
    """

    restrict_paths_to_workdir: bool = False
    require_explicit_grant: bool = False
    deny_in_replay: bool = False
    mutates: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Complete specification for a tool."""

    name: str
    handler: Callable[..., Any]
    schema: tuple[Field, ...]
    risk: Risk
    budget: Budget
    permission: PermissionRule


def build_tool_registry() -> dict[str, ToolSpec]:
    """Build the single authoritative registry for all exposed tools."""
    from .config import ALLOW_HOST_EXEC

    handlers: dict[str, Callable[..., Any]] = {}
    handlers.update(FILESYSTEM_TOOLS)
    handlers.update(MEMORY_TOOLS)
    handlers.update(BROWSER_TOOLS)
    handlers.update(CODE_TOOLS)
    handlers.update(REASONING_TOOLS)
    handlers.update(SANDBOX_TOOLS)

    # Host exec tools only in DEV_MODE
    if ALLOW_HOST_EXEC:
        handlers.update(SHELL_TOOLS)

    def spec(
        name: str,
        schema: list[Field],
        risk: Risk,
        budget: Budget,
        permission: PermissionRule,
    ) -> ToolSpec:
        if name not in handlers:
            raise KeyError(f"Tool handler not found: {name}")
        return ToolSpec(
            name=name,
            handler=handlers[name],
            schema=tuple(schema),
            risk=risk,
            budget=budget,
            permission=permission,
        )

    tools = {
        # --- filesystem ---
        "read_file": spec(
            "read_file",
            [
                Field("path", True, "str"),
                Field("max_bytes", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=20, max_bytes=200_000),
            permission=PermissionRule(restrict_paths_to_workdir=True),
        ),
        "write_file": spec(
            "write_file",
            [
                Field("path", True, "str"),
                Field("content", True, "str"),
                Field("max_bytes", False, "int"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=10, max_bytes=200_000),
            permission=PermissionRule(
                restrict_paths_to_workdir=True, require_explicit_grant=True, deny_in_replay=True, mutates=True
            ),
        ),
        "list_dir": spec(
            "list_dir",
            [
                Field("path", True, "str"),
                Field("max_items", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=20, max_results=2000),
            permission=PermissionRule(restrict_paths_to_workdir=True),
        ),
        "search_files": spec(
            "search_files",
            [
                Field("directory", True, "str"),
                Field("pattern", True, "str"),
                Field("max_results", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=10, max_results=500),
            permission=PermissionRule(restrict_paths_to_workdir=True),
        ),
        # --- memory ---
        "memory_store": spec(
            "memory_store",
            [
                Field("key", True, "str"),
                Field("value", True, "str"),
                Field("tags", False, "list"),
                Field("db_path", False, "str"),
            ],
            risk=Risk.MEDIUM,
            budget=Budget(calls_per_turn=30),
            permission=PermissionRule(require_explicit_grant=False, mutates=True),
        ),
        "memory_retrieve": spec(
            "memory_retrieve",
            [
                Field("key", True, "str"),
                Field("db_path", False, "str"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=40),
            permission=PermissionRule(),
        ),
        "memory_search": spec(
            "memory_search",
            [
                Field("query", True, "str"),
                Field("max_results", False, "int"),
                Field("db_path", False, "str"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=40, max_results=50),
            permission=PermissionRule(),
        ),
        "memory_delete": spec(
            "memory_delete",
            [
                Field("key", True, "str"),
                Field("db_path", False, "str"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=10),
            permission=PermissionRule(require_explicit_grant=True, deny_in_replay=True, mutates=True),
        ),
        # --- browser/network ---
        "fetch_url": spec(
            "fetch_url",
            [
                Field("url", True, "str"),
                Field("max_bytes", False, "int"),
                Field("timeout", False, "int"),
            ],
            risk=Risk.MEDIUM,
            budget=Budget(calls_per_turn=10, max_bytes=200_000),
            permission=PermissionRule(require_explicit_grant=False),
        ),
        "search_web": spec(
            "search_web",
            [
                Field("query", True, "str"),
                Field("max_results", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=10, max_results=10),
            permission=PermissionRule(),
        ),
        # --- sandbox execution (Docker-backed) ---
        "sandbox_exec": spec(
            "sandbox_exec",
            [
                Field("command", True, "str"),
                Field("workdir", False, "str"),
                Field("timeout_seconds", False, "int"),
                Field("image", False, "str"),
                Field("memory_limit", False, "str"),
                Field("cpu_limit", False, "int"),
                Field("network_disabled", False, "bool"),
                Field("env", False, "dict"),
                Field("max_output", False, "int"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=8, max_bytes=200_000),
            permission=PermissionRule(
                require_explicit_grant=True,
                restrict_paths_to_workdir=True,   # ✅ CRITICAL: prevent arbitrary host mounts
                deny_in_replay=True,
                mutates=True,
            ),
        ),
        # --- code ---
        "grep_files": spec(
            "grep_files",
            [
                Field("pattern", True, "str"),
                Field("directory", True, "str"),
                Field("file_pattern", False, "str"),
                Field("max_results", False, "int"),
                Field("context_lines", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=20, max_results=100),
            permission=PermissionRule(restrict_paths_to_workdir=True),
        ),
        "apply_diff": spec(
            "apply_diff",
            [
                Field("file_path", True, "str"),
                Field("diff", True, "str"),
                Field("dry_run", False, "bool"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=10),
            permission=PermissionRule(
                restrict_paths_to_workdir=True, require_explicit_grant=True, deny_in_replay=True, mutates=True
            ),
        ),
        "get_symbols": spec(
            "get_symbols",
            [
                Field("file_path", True, "str"),
                Field("max_symbols", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=20, max_results=100),
            permission=PermissionRule(restrict_paths_to_workdir=True),
        ),
        # --- reasoning (no side effects) ---
        "think": spec(
            "think",
            [
                Field("thought", True, "str"),
                Field("category", False, "str"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=50),
            permission=PermissionRule(),
        ),
        "plan": spec(
            "plan",
            [
                Field("goal", True, "str"),
                Field("steps", True, "list"),
                Field("current_step", False, "int"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=10),
            permission=PermissionRule(),
        ),
        "ask_user": spec(
            "ask_user",
            [
                Field("question", True, "str"),
                Field("options", False, "list"),
                Field("context", False, "str"),
            ],
            risk=Risk.LOW,
            budget=Budget(calls_per_turn=5),
            permission=PermissionRule(),
        ),
    }

    # Host exec tools only in DEV_MODE
    if ALLOW_HOST_EXEC:
        tools["run_command"] = spec(
            "run_command",
            [
                Field("command", True, "str"),
                Field("cwd", False, "str"),
                Field("timeout", False, "int"),
                Field("max_output", False, "int"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=12, max_bytes=100_000),
            permission=PermissionRule(
                require_explicit_grant=True, restrict_paths_to_workdir=True, deny_in_replay=True, mutates=True
            ),
        )
        tools["run_python"] = spec(
            "run_python",
            [
                Field("code", True, "str"),
                Field("cwd", False, "str"),
                Field("timeout", False, "int"),
                Field("max_output", False, "int"),
            ],
            risk=Risk.HIGH,
            budget=Budget(calls_per_turn=6, max_bytes=100_000),
            permission=PermissionRule(
                require_explicit_grant=True, restrict_paths_to_workdir=True, deny_in_replay=True, mutates=True
            ),
        )

    return tools


def validate_arguments(spec: ToolSpec, arguments: Mapping[str, Any]) -> tuple[bool, str]:
    """Validate tool arguments against schema."""
    if not isinstance(arguments, dict):
        return False, "arguments must be an object"

    # Check required fields
    for f in spec.schema:
        if f.required and f.name not in arguments:
            return False, f"missing required arg '{f.name}'"

    # Check types
    for f in spec.schema:
        if f.name in arguments and not _is_kind(arguments.get(f.name), f.kind):
            return False, f"arg '{f.name}' wrong type (expected {f.kind})"

    # No extra fields allowed
    allowed = {f.name for f in spec.schema}
    extras = [k for k in arguments.keys() if k not in allowed]
    if extras:
        return False, f"unexpected args: {extras}"

    return True, ""


def enforce_path_scope(*, workdir: str, path: str) -> tuple[bool, str]:
    """Restrict file paths to within working_directory."""
    try:
        wd = Path(workdir).resolve()
        p = Path(path).expanduser().resolve()
        try:
            ok = p.is_relative_to(wd)
        except AttributeError:
            # Python < 3.9 fallback
            ok = str(p).startswith(str(wd))
        if not ok:
            return False, f"path escapes working_directory: {p} (wd={wd})"
        return True, ""
    except Exception as e:
        return False, f"path scope check failed: {e}"
