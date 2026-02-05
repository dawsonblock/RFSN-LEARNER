from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PermissionState:
    granted_tools: set[str] = field(default_factory=set)
    python_execution_enabled: bool = False

    def has_tool(self, tool_name: str) -> bool:
        if tool_name == "run_python" and not self.python_execution_enabled:
            return False
        return tool_name in self.granted_tools

    def grant_tool(self, tool_name: str) -> None:
        self.granted_tools.add(tool_name)

    def revoke_tool(self, tool_name: str) -> None:
        self.granted_tools.discard(tool_name)

    def enable_python(self) -> None:
        self.python_execution_enabled = True

    def disable_python(self) -> None:
        self.python_execution_enabled = False
