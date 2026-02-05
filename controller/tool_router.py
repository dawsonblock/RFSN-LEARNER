# controller/tool_router.py
"""
Tool router - central dispatcher for tool execution with enforcement.

Routes tool_call payloads to implementations WITH:
- Tool registry (single source of truth)
- Schema validation
- Budgets (per-turn)
- Path scope enforcement
- Permission checks
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .tools.filesystem import ToolResult
from .tool_registry import (
    build_tool_registry,
    validate_arguments,
    enforce_path_scope,
)
from .budget_enforcer import BudgetEnforcer
from .permissions import PermissionState


TOOL_REGISTRY = build_tool_registry()


@dataclass
class ExecutionContext:
    """Context for tool execution."""
    session_id: str
    user_id: str = "default"
    working_directory: str = "./"
    memory_db_path: str = "agent_memory.db"

    # Enforcement state (per user turn)
    budgets: BudgetEnforcer = field(default_factory=BudgetEnforcer)
    permissions: PermissionState = field(default_factory=PermissionState)

    def start_new_turn(self) -> None:
        """Reset per-turn budgets."""
        self.budgets.reset_turn()

    def compute_world_hash(self) -> str:
        """Compute a hash of the current world state."""
        state = {
            "session_id": self.session_id,
            "cwd": self.working_directory,
            "enabled_tools": sorted(TOOL_REGISTRY.keys()),
            "timestamp": int(time.time()),
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def _estimate_bytes(tool: str, arguments: Mapping[str, Any]) -> int:
    """Estimate bytes for budget charging."""
    if tool in ("read_file", "fetch_url"):
        mb = arguments.get("max_bytes")
        return int(mb) if isinstance(mb, int) else 0
    if tool == "write_file":
        content = arguments.get("content")
        if isinstance(content, str):
            return len(content.encode("utf-8", errors="ignore"))
    return 0


def route_tool_call(
    tool_name: str,
    arguments: Mapping[str, Any],
    context: ExecutionContext,
) -> ToolResult:
    """
    Route a tool call with full enforcement:
    1. Registry check
    2. Schema validation
    3. Permission check
    4. Path scope check
    5. Budget check
    6. Execute
    """
    if tool_name not in TOOL_REGISTRY:
        return ToolResult(False, None, f"Unknown tool: {tool_name}. Available: {sorted(TOOL_REGISTRY.keys())}")

    spec = TOOL_REGISTRY[tool_name]

    # 1) Schema validation
    ok, err = validate_arguments(spec, dict(arguments))
    if not ok:
        return ToolResult(False, None, f"Invalid arguments for {tool_name}: {err}")

    # 2) Permission gating for tools marked require_explicit_grant
    if spec.permission.require_explicit_grant and not context.permissions.has_tool(tool_name):
        return ToolResult(False, None, f"Permission required for tool: {tool_name}")

    # 3) Path scoping for filesystem-like tools
    if spec.permission.restrict_paths_to_workdir:
        if tool_name in ("read_file", "write_file", "list_dir", "get_symbols", "apply_diff"):
            p = str(arguments.get("path", arguments.get("file_path", "")))
            ok2, err2 = enforce_path_scope(workdir=context.working_directory, path=p)
            if not ok2:
                return ToolResult(False, None, err2)
        if tool_name in ("search_files", "grep_files"):
            d = str(arguments.get("directory", ""))
            ok2, err2 = enforce_path_scope(workdir=context.working_directory, path=d)
            if not ok2:
                return ToolResult(False, None, err2)

    # 4) Budgeting (per-turn)
    est = _estimate_bytes(tool_name, arguments)
    ok3, err3 = context.budgets.check_and_charge(tool=tool_name, budget=spec.budget, estimated_bytes=est)
    if not ok3:
        return ToolResult(False, None, f"Budget denied for {tool_name}: {err3}")

    # 5) Inject db_path for memory tools unless caller provided it
    call_args = dict(arguments)
    if tool_name.startswith("memory_") and "db_path" not in call_args:
        call_args["db_path"] = context.memory_db_path

    # 6) Execute
    try:
        result = spec.handler(**call_args)
        # Normalize ToolResult-ish objects
        if hasattr(result, "success") and hasattr(result, "output"):
            return ToolResult(bool(result.success), result.output, getattr(result, "error", None))
        return ToolResult(True, result, None)
    except TypeError as e:
        return ToolResult(False, None, f"Invalid arguments for {tool_name}: {e}")
    except Exception as e:
        return ToolResult(False, None, f"Tool execution failed: {e}")


def route_action(
    action_payload: Mapping[str, Any],
    context: ExecutionContext,
) -> ToolResult:
    """
    Route a tool_call payload to execution.

    Expected payload format:
    {
        "tool": "tool_name",
        "arguments": {"arg1": "value1", ...}
    }
    """
    tool_name = action_payload.get("tool")
    if not isinstance(tool_name, str) or not tool_name:
        return ToolResult(False, None, "Missing 'tool' in payload")

    arguments = action_payload.get("arguments", {})
    if not isinstance(arguments, dict):
        return ToolResult(False, None, "'arguments' must be a dict")

    return route_tool_call(tool_name, arguments, context)


def list_available_tools() -> list[dict[str, str]]:
    """List all available tools with metadata."""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "risk": str(spec.risk.value),
            "description": (spec.handler.__doc__ or "No description").strip().split("\n")[0],
        })
    return tools


def get_tool_names() -> list[str]:
    """Get list of tool names."""
    return sorted(TOOL_REGISTRY.keys())
