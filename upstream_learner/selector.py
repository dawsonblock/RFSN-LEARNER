# upstream_learner/selector.py
"""
Learner-driven tool selection bias.

Provides lightweight bandit-style routing influence based on
historical tool success rates from the outcome database.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from controller.tool_router import ExecutionContext

from upstream_learner.outcome_db import OutcomeDB


def get_tool_success_rate(tool_name: str, db_path: str = "outcomes.db") -> float | None:
    """
    Query historical success rate for a tool.

    Returns success rate between 0.0 and 1.0, or None if no data.
    """
    try:
        db = OutcomeDB(db_path)
        outcomes = db.get_arm_outcomes(tool_name, limit=100)
        if not outcomes:
            return None
        successes = sum(1 for o in outcomes if o.reward > 0.5)
        return successes / len(outcomes)
    except Exception:
        return None


def select_tool_bias(
    tool_name: str,
    context: ExecutionContext | None = None,
    *,
    exploration_prob: float = 0.1,
) -> str:
    """
    Apply learner bias to tool selection.

    If the tool has low historical success rate, occasionally
    explore alternatives. For now, returns the same tool
    (integration point for future bandit-style selection).

    Args:
        tool_name: Proposed tool name
        context: Execution context (for session-specific learning)
        exploration_prob: Probability of exploration

    Returns:
        Tool name to use (may be modified by learner)
    """
    rate = get_tool_success_rate(tool_name)

    if rate is None:
        # No data, use proposed tool
        return tool_name

    # Exploration: with some probability, stick with the proposed tool
    # even if success rate is low (to gather more data)
    if random.random() < exploration_prob:
        return tool_name

    # Exploitation: if success rate is very low, could suggest alternatives
    # For now, just return the tool (future: map to alternatives)
    return tool_name
