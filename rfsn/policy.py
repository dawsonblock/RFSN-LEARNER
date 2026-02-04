"""
Structured policy rules for the gate.

This module defines configurable policies that the gate checks against.
Policies are data, not code - the gate remains a pure function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ToolPolicy:
    """Policy for a specific tool."""
    name: str
    enabled: bool = True
    # Path constraints (for filesystem tools)
    allowed_path_prefixes: tuple[str, ...] = ()
    blocked_path_patterns: tuple[str, ...] = ()
    # Domain constraints (for network tools)
    allowed_domains: frozenset[str] = frozenset()
    blocked_domains: frozenset[str] = frozenset()
    # Size constraints
    max_payload_bytes: int = 100_000
    max_output_bytes: int = 1_000_000
    # Rate limiting
    max_calls_per_minute: int = 60
    # Permission requirements
    requires_permission: str | None = None


@dataclass
class AgentPolicy:
    """
    Complete policy configuration for an agent session.
    
    The gate checks proposed actions against this policy.
    Policies are immutable during a session but can vary between sessions.
    """
    # Tool allowlist - only these tools can be called
    allowed_tools: frozenset[str] = frozenset({
        "read_file",
        "list_dir",
        "search_files",
        "memory_store",
        "memory_retrieve",
        "message_send",
    })
    
    # Per-tool policies
    tool_policies: Mapping[str, ToolPolicy] = field(default_factory=dict)
    
    # Global path constraints
    allowed_path_prefixes: tuple[str, ...] = (
        "/tmp/",
        "./",
    )
    blocked_path_patterns: tuple[str, ...] = (
        r".*\.env$",
        r".*\.ssh/.*",
        r".*\.aws/.*",
        r".*/\.git/.*",
        r".*secrets.*",
        r".*password.*",
    )
    
    # Network constraints
    allowed_domains: frozenset[str] = frozenset({
        "api.openai.com",
        "api.anthropic.com",
        "www.google.com",
        "github.com",
    })
    
    # Data egress patterns to block
    blocked_egress_patterns: tuple[str, ...] = (
        r"sk-[a-zA-Z0-9]{48}",        # OpenAI API keys
        r"AKIA[A-Z0-9]{16}",          # AWS access keys
        r"ghp_[a-zA-Z0-9]{36}",       # GitHub tokens
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # emails
    )
    
    # Global limits
    max_payload_bytes: int = 100_000
    max_actions_per_session: int = 1000
    
    # Permission elevation requires explicit approval
    elevation_requires_approval: bool = True
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is in the allowlist."""
        return tool_name in self.allowed_tools
    
    def get_tool_policy(self, tool_name: str) -> ToolPolicy | None:
        """Get the specific policy for a tool."""
        return self.tool_policies.get(tool_name)
    
    def check_path(self, path: str) -> tuple[bool, str]:
        """Check if a path is allowed by policy."""
        # Check blocked patterns first
        for pattern in self.blocked_path_patterns:
            if re.match(pattern, path, re.IGNORECASE):
                return False, f"Path matches blocked pattern: {pattern}"
        
        # Check allowed prefixes
        if self.allowed_path_prefixes:
            if not any(path.startswith(p) for p in self.allowed_path_prefixes):
                return False, f"Path not in allowed prefixes: {self.allowed_path_prefixes}"
        
        return True, "Path allowed"
    
    def check_domain(self, domain: str) -> tuple[bool, str]:
        """Check if a domain is allowed by policy."""
        domain = domain.lower()
        
        if self.allowed_domains and domain not in self.allowed_domains:
            return False, f"Domain not in allowlist: {domain}"
        
        return True, "Domain allowed"
    
    def check_egress(self, content: str) -> tuple[bool, str]:
        """Check content for blocked egress patterns (secrets, PII)."""
        for pattern in self.blocked_egress_patterns:
            if re.search(pattern, content):
                return False, f"Content matches blocked egress pattern"
        
        return True, "Content clean"


# Default restrictive policy
DEFAULT_POLICY = AgentPolicy()


# Permissive policy for development/testing
DEV_POLICY = AgentPolicy(
    allowed_tools=frozenset({
        "read_file", "write_file", "list_dir", "search_files",
        "memory_store", "memory_retrieve", "memory_search",
        "message_send",
        "shell_command",  # dangerous but allowed in dev
        "fetch_url",
    }),
    allowed_path_prefixes=("./", "/tmp/", "/Users/"),
    allowed_domains=frozenset(),  # empty = allow all
    elevation_requires_approval=False,
)
