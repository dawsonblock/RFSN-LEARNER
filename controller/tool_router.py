"""
Tool router - central dispatcher for tool execution.

Routes ProposedAction payloads to the appropriate tool implementation.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .tools.filesystem import FILESYSTEM_TOOLS, ToolResult
from .tools.memory import MEMORY_TOOLS
from .tools.browser import BROWSER_TOOLS


# Unified tool registry
TOOL_REGISTRY: dict[str, Callable[..., ToolResult]] = {}
TOOL_REGISTRY.update(FILESYSTEM_TOOLS)
TOOL_REGISTRY.update(MEMORY_TOOLS)
TOOL_REGISTRY.update(BROWSER_TOOLS)


@dataclass
class ExecutionContext:
    """Context for tool execution."""
    session_id: str
    user_id: str = "default"
    working_directory: str = "./"
    memory_db_path: str = "agent_memory.db"
    rate_limits: dict[str, list[float]] = field(default_factory=dict)  # tool -> timestamps
    
    def compute_world_hash(self) -> str:
        """Compute hash of current world state."""
        state = {
            "session_id": self.session_id,
            "cwd": self.working_directory,
            "enabled_tools": sorted(TOOL_REGISTRY.keys()),
            "timestamp": int(time.time()),
        }
        return hashlib.sha256(
            json.dumps(state, sort_keys=True).encode()
        ).hexdigest()


def route_tool_call(
    tool_name: str,
    arguments: Mapping[str, Any],
    context: ExecutionContext,
) -> ToolResult:
    """
    Route a tool call to its implementation.
    
    This is called AFTER the gate has approved the action.
    """
    if tool_name not in TOOL_REGISTRY:
        return ToolResult(
            success=False,
            output=None,
            error=f"Unknown tool: {tool_name}. Available: {list(TOOL_REGISTRY.keys())}",
        )
    
    tool_fn = TOOL_REGISTRY[tool_name]
    
    try:
        # Call the tool with its arguments
        result = tool_fn(**arguments)
        return result
    except TypeError as e:
        return ToolResult(
            success=False,
            output=None,
            error=f"Invalid arguments for {tool_name}: {e}",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output=None,
            error=f"Tool execution failed: {e}",
        )


def route_action(
    action_payload: Mapping[str, Any],
    context: ExecutionContext,
) -> ToolResult:
    """
    Route a ProposedAction payload (tool_call type) to execution.
    
    Expected payload format:
    {
        "tool": "tool_name",
        "arguments": {"arg1": "value1", ...}
    }
    """
    tool_name = action_payload.get("tool")
    if not tool_name:
        return ToolResult(
            success=False,
            output=None,
            error="Missing 'tool' in payload",
        )
    
    arguments = action_payload.get("arguments", {})
    if not isinstance(arguments, dict):
        return ToolResult(
            success=False,
            output=None,
            error="'arguments' must be a dict",
        )
    
    return route_tool_call(tool_name, arguments, context)


def list_available_tools() -> list[dict[str, str]]:
    """List all available tools with their signatures."""
    tools = []
    for name, fn in TOOL_REGISTRY.items():
        doc = fn.__doc__ or "No description"
        tools.append({
            "name": name,
            "description": doc.strip().split("\n")[0],
        })
    return tools
