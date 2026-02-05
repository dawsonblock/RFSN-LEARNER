# controller/permissions.py
"""
Permission state for tool authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PermissionState:
    """
    Minimal permission store. Grant/revoke tools via UI or commands.
    """

    granted_tools: set[str] = field(default_factory=set)

    def grant_tool(self, tool: str) -> None:
        """Grant permission to use a tool."""
        self.granted_tools.add(tool)

    def revoke_tool(self, tool: str) -> None:
        """Revoke permission for a tool."""
        self.granted_tools.discard(tool)

    def has_tool(self, tool: str) -> bool:
        """Check if tool is granted."""
        return tool in self.granted_tools

    def list_grants(self) -> list[str]:
        """List all granted tools."""
        return sorted(self.granted_tools)
