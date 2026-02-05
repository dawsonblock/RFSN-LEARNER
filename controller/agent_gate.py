"""
Extended gate for general agent actions.

Wraps the core gate with policy checks for tool_call, memory_write, etc.
"""
from __future__ import annotations

from typing import Any, Mapping


from rfsn.types import GateDecision, ProposedAction, WorldSnapshot, StateSnapshot
from rfsn.gate import gate as core_gate
from rfsn.policy import AgentPolicy, DEFAULT_POLICY


def check_tool_call_policy(
    action: ProposedAction,
    policy: AgentPolicy,
) -> tuple[bool, str, str | None]:
    """
    Check if a tool_call action is allowed by policy.
    
    Returns (allowed, reason, suggested_alternative).
    """
    payload = action.payload
    if not isinstance(payload, dict):
        return False, "tool_call payload must be a dict", None
    
    tool_name = payload.get("tool", "")
    arguments = payload.get("arguments", {})
    
    # Check tool allowlist
    if not policy.is_tool_allowed(tool_name):
        allowed_list = ", ".join(sorted(policy.allowed_tools)[:5])
        return False, f"Tool '{tool_name}' not in allowlist", f"Try one of: {allowed_list}"
    
    # Check path constraints for filesystem tools
    if tool_name in ("read_file", "write_file", "list_dir", "search_files"):
        path = arguments.get("path", arguments.get("directory", ""))
        if path:
            allowed, reason = policy.check_path(path)
            if not allowed:
                return False, reason, "Use a path in ./tmp/ or current directory"
    
    # Check domain constraints for network tools
    if tool_name in ("fetch_url",):
        url = arguments.get("url", "")
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.netloc:
                allowed, reason = policy.check_domain(parsed.netloc)
                if not allowed:
                    return False, reason, None
    
    # Check egress for content-sending operations
    if tool_name in ("write_file", "memory_store", "fetch_url"):
        content = str(arguments.get("content", arguments.get("value", "")))
        allowed, reason = policy.check_egress(content)
        if not allowed:
            return False, reason, "Remove sensitive data before sending"
    
    return True, "Tool call allowed", None


def check_memory_write_policy(
    action: ProposedAction,
    policy: AgentPolicy,
) -> tuple[bool, str, str | None]:
    """Check if a memory_write action is allowed."""
    payload = action.payload
    if not isinstance(payload, dict):
        return False, "memory_write payload must be a dict", None
    
    value = str(payload.get("value", ""))
    
    # Check egress patterns (no secrets in memory)
    allowed, reason = policy.check_egress(value)
    if not allowed:
        return False, f"Memory write blocked: {reason}", "Redact sensitive data"
    
    # Check size
    if len(value.encode("utf-8")) > policy.max_payload_bytes:
        return False, f"Value too large: > {policy.max_payload_bytes} bytes", None
    
    return True, "Memory write allowed", None


def check_permission_request(
    action: ProposedAction,
    policy: AgentPolicy,
) -> tuple[bool, str, str | None]:
    """Check if permission elevation is allowed."""
    if policy.elevation_requires_approval:
        return False, "Permission elevation requires user approval", "Ask user first"
    return True, "Permission request allowed", None


def agent_gate(
    state: WorldSnapshot | StateSnapshot,
    action: ProposedAction,
    *,
    policy: AgentPolicy | None = None,
) -> GateDecision:
    """
    Extended gate for general agent actions.
    
    Delegates to core gate for patch/command actions,
    applies policy checks for agent-specific actions.
    """
    if policy is None:
        policy = DEFAULT_POLICY
    
    # Basic justification check
    if not action.justification or len(action.justification) < 5:
        return GateDecision(False, "Missing/weak justification")
    
    # Route by action kind
    if action.kind in ("patch_plan", "patch", "command"):
        # Use core gate for SWE-bench actions
        if isinstance(state, StateSnapshot):
            return core_gate(state, action)
        else:
            # Convert WorldSnapshot to StateSnapshot for core gate
            temp_state = StateSnapshot(
                repo_id=state.session_id,
                fs_tree_hash=state.world_state_hash,
                toolchain="agent",
                tests_passed=state.system_clean,
                metadata=dict(state.metadata),
            )
            return core_gate(temp_state, action)
    
    elif action.kind == "tool_call":
        allowed, reason, alt = check_tool_call_policy(action, policy)
        return GateDecision(allowed, reason, action if allowed else None, alt)
    
    elif action.kind == "memory_write":
        allowed, reason, alt = check_memory_write_policy(action, policy)
        return GateDecision(allowed, reason, action if allowed else None, alt)
    
    elif action.kind == "message_send":
        # Messages are always allowed (checked for egress)
        payload = action.payload
        if isinstance(payload, dict):
            message = str(payload.get("message", ""))
            allowed, reason = policy.check_egress(message)
            if not allowed:
                return GateDecision(False, reason, None, "Remove sensitive data")
        return GateDecision(True, "Message allowed", action)
    
    elif action.kind == "permission_request":
        allowed, reason, alt = check_permission_request(action, policy)
        return GateDecision(allowed, reason, action if allowed else None, alt)
    
    else:
        return GateDecision(False, f"Unknown action kind: {action.kind}")
