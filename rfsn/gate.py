from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .types import GateDecision, ProposedAction, StateSnapshot

DEFAULT_BLOCKED_COMMAND_PREFIXES: tuple[str, ...] = (
    "rm ",
    "sudo ",
    "curl ",
    "wget ",
    "powershell",
    "invoke-",
)


def _contains_blocked_command(cmd: str, blocked_prefixes: Iterable[str]) -> bool:
    s = cmd.strip().lower()
    return any(s.startswith(p) for p in blocked_prefixes)


def gate(
    state: StateSnapshot,
    action: ProposedAction,
    *,
    allow_commands: bool = False,
    blocked_command_prefixes: Iterable[str] = DEFAULT_BLOCKED_COMMAND_PREFIXES,
    require_clean_tests_for_patch: bool = True,
    max_patch_bytes: int = 500_000,
) -> GateDecision:
    """
    Pure function. No IO. No network. No learning.
    """

    if not action.justification or len(action.justification) < 8:
        return GateDecision(False, "Missing/weak justification")

    if action.kind == "command":
        if not allow_commands:
            return GateDecision(False, "Commands forbidden by policy")
        if not isinstance(action.payload, str):
            return GateDecision(False, "Command payload must be a string")
        if _contains_blocked_command(action.payload, blocked_command_prefixes):
            return GateDecision(False, "Command blocked by prefix policy")
        return GateDecision(True, "Command allowed", normalized_action=action)

    if action.kind == "patch":
        if require_clean_tests_for_patch and not state.tests_passed:
            return GateDecision(False, "Refusing patch: state not clean (tests failing)")
        if not isinstance(action.payload, str):
            return GateDecision(False, "Patch payload must be unified diff string")
        if len(action.payload.encode("utf-8")) > max_patch_bytes:
            return GateDecision(False, "Patch too large")
        norm = "\n".join(line.rstrip() for line in action.payload.splitlines()) + "\n"
        return GateDecision(True, "Patch allowed", normalized_action=replace(action, payload=norm))

    if action.kind == "patch_plan":
        return GateDecision(True, "Plan allowed", normalized_action=action)

    return GateDecision(False, f"Unknown action kind: {action.kind}")
