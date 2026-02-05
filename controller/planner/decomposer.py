"""
Task decomposition - break goals into subtasks.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from rfsn.types import ProposedAction

from .types import PlanStep

# Common decomposition patterns (rule-based)
PATTERNS = {
    r"(list|show|find).*(and|then).*(read|summarize|analyze)": [
        ("list_files", "List the relevant files"),
        ("read_content", "Read the file contents"),
        ("summarize", "Summarize the findings"),
    ],
    r"(create|write).*(and|then).*(test|verify)": [
        ("create", "Create the requested content"),
        ("verify", "Verify the result"),
    ],
    r"(search|find).*(and|then).*(update|modify|change)": [
        ("search", "Search for the target"),
        ("modify", "Apply the changes"),
    ],
    r"(read|analyze).*(and|then).*(store|save|remember)": [
        ("read", "Read and analyze the content"),
        ("store", "Store the results in memory"),
    ],
}


def match_pattern(goal: str) -> list[tuple[str, str]] | None:
    """Match goal against known patterns."""
    goal_lower = goal.lower()
    for pattern, steps in PATTERNS.items():
        if re.search(pattern, goal_lower):
            return steps
    return None


def decompose_goal(
    goal: str,
    context: Mapping[str, Any] | None = None,
) -> list[PlanStep]:
    """
    Decompose a high-level goal into executable steps.

    Uses rule-based patterns for common goals.
    Falls back to single direct action for unknown patterns.
    """
    # Try pattern matching
    matched = match_pattern(goal)
    if matched:
        return _create_steps_from_pattern(goal, matched)

    # Fallback: single direct action
    return [_create_direct_step(goal)]


def _create_steps_from_pattern(
    goal: str,
    pattern_steps: list[tuple[str, str]],
) -> list[PlanStep]:
    """Create PlanStep objects from matched pattern."""
    steps = []
    prev_id = None

    for step_type, description in pattern_steps:
        action = _create_action_for_step(step_type, goal)
        step = PlanStep.create(
            description=description,
            action=action,
            depends_on=[prev_id] if prev_id else [],
        )
        steps.append(step)
        prev_id = step.step_id

    return steps


def _create_direct_step(goal: str) -> PlanStep:
    """Create a single direct execution step."""
    # Infer action type from goal
    goal_lower = goal.lower()

    if any(w in goal_lower for w in ["list", "show", "find files"]):
        action = ProposedAction(
            kind="tool_call",
            payload={"tool": "list_dir", "arguments": {"path": "./"}},
            justification=goal,
        )
    elif any(w in goal_lower for w in ["read", "open", "view"]):
        action = ProposedAction(
            kind="tool_call",
            payload={"tool": "read_file", "arguments": {"path": "./README.md"}},
            justification=goal,
        )
    elif any(w in goal_lower for w in ["search", "find"]):
        action = ProposedAction(
            kind="tool_call",
            payload={"tool": "search_files", "arguments": {"directory": "./", "pattern": "*"}},
            justification=goal,
        )
    elif any(w in goal_lower for w in ["remember", "store", "save"]):
        action = ProposedAction(
            kind="tool_call",
            payload={"tool": "memory_store", "arguments": {"key": "note", "value": goal}},
            justification=goal,
        )
    else:
        # Default: message back to user asking for clarification
        action = ProposedAction(
            kind="message_send",
            payload={"message": f"I need more specific instructions to: {goal}"},
            justification="Goal requires clarification",
        )

    return PlanStep.create(
        description=f"Execute: {goal}",
        action=action,
    )


def _create_action_for_step(step_type: str, goal: str) -> ProposedAction:
    """Create appropriate action for a step type."""
    if step_type == "list_files":
        return ProposedAction(
            kind="tool_call",
            payload={"tool": "list_dir", "arguments": {"path": "./"}},
            justification=f"Step in plan: {goal}",
        )
    elif step_type == "read_content":
        return ProposedAction(
            kind="tool_call",
            payload={"tool": "read_file", "arguments": {"path": "./README.md"}},
            justification=f"Step in plan: {goal}",
        )
    elif step_type in ("summarize", "analyze"):
        return ProposedAction(
            kind="message_send",
            payload={"message": "Summarizing findings..."},
            justification=f"Step in plan: {goal}",
        )
    elif step_type in ("create", "modify"):
        return ProposedAction(
            kind="tool_call",
            payload={"tool": "write_file", "arguments": {"path": "./output.txt", "content": ""}},
            justification=f"Step in plan: {goal}",
        )
    elif step_type == "verify":
        return ProposedAction(
            kind="message_send",
            payload={"message": "Verifying results..."},
            justification=f"Step in plan: {goal}",
        )
    elif step_type == "search":
        return ProposedAction(
            kind="tool_call",
            payload={"tool": "search_files", "arguments": {"directory": "./", "pattern": "*"}},
            justification=f"Step in plan: {goal}",
        )
    elif step_type == "store":
        return ProposedAction(
            kind="tool_call",
            payload={"tool": "memory_store", "arguments": {"key": "result", "value": ""}},
            justification=f"Step in plan: {goal}",
        )
    else:
        return ProposedAction(
            kind="message_send",
            payload={"message": f"Unknown step type: {step_type}"},
            justification="Fallback",
        )
