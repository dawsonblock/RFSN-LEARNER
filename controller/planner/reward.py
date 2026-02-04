# controller/planner/reward.py
"""
Reward computation for plan execution outcomes.

This is critical - Thompson sampling is only as good as the scalar you feed it.
"""
from __future__ import annotations

from .types import Plan, PlanResult


def reward_from_plan_result(*, plan: Plan, result: PlanResult) -> float:
    """
    Compute scalar reward in [-1, +1] from plan execution result.

    Reward design:
      - Success matters most (+1 base for full success)
      - Partial completion still counts (completion rate weighting)
      - Failed steps penalize (bounded penalty)
      - Maps to [-1, 1] for stable bandit updates
    """
    # Base: success gives +1, failure gives 0 baseline
    base = 1.0 if result.success else 0.0

    # Partial credit: completion rate in [0, 1]
    partial = float(result.completion_rate)

    # Penalty for failed steps (bounded to prevent extreme negatives)
    penalty = min(1.0, 0.15 * float(result.failed_steps))

    # Combine: success weighted 70%, partial 60%, minus penalty
    r = base * 0.7 + partial * 0.6 - penalty

    # Clamp to [-1, 1]
    return max(-1.0, min(1.0, r))


def reward_from_step_outcomes(
    *,
    completed: int,
    failed: int,
    denied: int,
    total: int,
) -> float:
    """
    Alternative reward computation from raw step counts.
    
    Useful when you don't have a PlanResult object.
    """
    if total == 0:
        return 0.0
    
    completion_rate = completed / total
    failure_rate = failed / total
    denial_rate = denied / total
    
    # Completions are good, failures are bad, denials are slightly bad
    # (denials waste a proposal but aren't as bad as execution failures)
    r = completion_rate - 0.5 * failure_rate - 0.1 * denial_rate
    
    return max(-1.0, min(1.0, r))
