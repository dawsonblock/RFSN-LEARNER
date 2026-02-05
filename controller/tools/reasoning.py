# controller/tools/reasoning.py
"""
Reasoning tools - structured thinking with no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: Any
    error: str | None = None


def think(
    thought: str,
    *,
    category: str = "reasoning",
) -> ToolResult:
    """
    Record a structured reasoning step. No side effects.

    This tool allows the LLM to think through a problem
    step by step, making reasoning transparent and auditable.

    Args:
        thought: The reasoning content
        category: Type of thought (reasoning, planning, observation, etc.)

    Returns:
        ToolResult confirming thought was recorded
    """
    return ToolResult(
        success=True,
        output={
            "category": category,
            "thought": thought,
            "recorded": True,
        },
    )


def plan(
    goal: str,
    steps: list[str],
    *,
    current_step: int = 0,
) -> ToolResult:
    """
    Create or update a task plan. No side effects.

    Args:
        goal: The high-level goal
        steps: List of steps to accomplish the goal
        current_step: Index of current step (0-based)

    Returns:
        ToolResult with the plan
    """
    return ToolResult(
        success=True,
        output={
            "goal": goal,
            "steps": [
                {"index": i, "step": s, "status": "done" if i < current_step else ("current" if i == current_step else "pending")}
                for i, s in enumerate(steps)
            ],
            "current_step": current_step,
            "total_steps": len(steps),
        },
    )


def ask_user(
    question: str,
    *,
    options: list[str] | None = None,
    context: str | None = None,
) -> ToolResult:
    """
    Request clarification from the user.

    This tool signals that the agent needs user input.
    The actual interaction is handled by the chat layer.

    Args:
        question: The question to ask
        options: Optional list of suggested responses
        context: Optional context for why this is being asked

    Returns:
        ToolResult indicating a question was raised
    """
    return ToolResult(
        success=True,
        output={
            "type": "user_question",
            "question": question,
            "options": options,
            "context": context,
            "awaiting_response": True,
        },
    )


# Tool registry
REASONING_TOOLS = {
    "think": think,
    "plan": plan,
    "ask_user": ask_user,
}
