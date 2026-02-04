from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence, Union


# Extended action kinds for general-purpose agents
ActionKind = Literal[
    # Original SWE-bench actions
    "patch_plan",
    "patch",
    "command",
    # General agent actions
    "tool_call",           # generic tool invocation
    "message_send",        # send message to user
    "memory_write",        # write to agent memory
    "permission_request",  # request elevated permissions
]


@dataclass(frozen=True)
class StateSnapshot:
    """
    Kernel input for repo-based workflows (SWE-bench).
    Must be constructed by an outer controller.
    The kernel never reaches into the filesystem or executes tools.
    """
    repo_id: str                 # stable identifier (e.g., "owner/name@sha" or path hash)
    fs_tree_hash: str            # hash of working tree (controller-computed)
    toolchain: str               # e.g., "python3.12"
    tests_passed: bool
    metadata: Mapping[str, Any]  # controller-supplied (task id, env, etc.)


@dataclass(frozen=True)
class WorldSnapshot:
    """
    Kernel input for general agent workflows.
    Represents the controllable world state, not a specific repo.
    """
    session_id: str              # conversation/workspace identifier
    world_state_hash: str        # hash of controllable state
    enabled_tools: tuple[str, ...]  # tools available in this session
    permissions: frozenset[str]  # granted permission set
    system_clean: bool           # no pending unsafe ops, rate limits ok
    metadata: Mapping[str, Any]  # session context (user id, env, etc.)


# Union type for gate input
Snapshot = Union[StateSnapshot, WorldSnapshot]


@dataclass(frozen=True)
class ProposedAction:
    """
    Planner/learner output. Untrusted.
    """
    kind: ActionKind
    payload: Any                 # e.g., unified diff text, plan steps, tool call dict
    justification: str
    risk_tags: Sequence[str] = ()  # e.g., ("touches_build_system", "deletes_files")


@dataclass(frozen=True)
class GateDecision:
    allow: bool
    reason: str
    normalized_action: ProposedAction | None = None
    suggested_alternative: str | None = None  # hint for denied actions


@dataclass(frozen=True)
class LedgerEntry:
    idx: int
    ts_utc: str
    state_hash: str
    action_hash: str
    decision: str
    prev_entry_hash: str
    entry_hash: str
    payload: Mapping[str, Any]

