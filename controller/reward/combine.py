# controller/reward/combine.py
"""
Combined reward function for learning.

Merges plan-level reward with test-result reward into a single scalar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass
class TestOutcome:
    """Test execution result (named to avoid pytest collection)."""

    passed: int = 0
    failed: int = 0
    error: int = 0
    skipped: int = 0
    total_time: float = 0.0
    baseline_passed: int = 0  # Before patch
    baseline_failed: int = 0


@dataclass
class PlanProgress:
    """Plan execution progress."""

    total_steps: int = 1
    completed_steps: int = 0
    failed_steps: int = 0
    success: bool = False


def reward_from_plan(progress: PlanProgress) -> float:
    """
    Reward from plan execution.

    Returns:
        float in [-1, 1]
    """
    if progress.total_steps == 0:
        return 0.0

    completion_rate = progress.completed_steps / progress.total_steps
    failure_penalty = min(1.0, 0.2 * progress.failed_steps)

    base = 1.0 if progress.success else 0.0

    r = base * 0.5 + completion_rate * 0.5 - failure_penalty
    return max(-1.0, min(1.0, r))


def reward_from_tests(result: TestOutcome) -> float:
    """
    Reward from test results.

    Measures improvement from baseline.

    Returns:
        float in [-1, 1]
    """
    if result.baseline_failed == 0:
        # No failing tests to fix
        if result.failed == 0:
            return 0.3  # Neutral, didn't break anything
        else:
            return -0.5  # Broke tests

    # How many failing tests did we fix?
    fixed = result.baseline_failed - result.failed
    fix_rate = fixed / result.baseline_failed

    # Did we break previously passing tests?
    broken = max(0, result.baseline_passed - result.passed)
    break_penalty = min(1.0, 0.3 * broken)

    r = fix_rate - break_penalty
    return max(-1.0, min(1.0, r))


def combined_reward(
    plan_progress: PlanProgress | None = None,
    test_result: TestOutcome | None = None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """
    Combine plan and test rewards.

    Args:
        plan_progress: Plan execution result
        test_result: Test execution result
        weights: Optional weight overrides {"plan": 0.4, "test": 0.6}

    Returns:
        float in [-1, 1]
    """
    w = {"plan": 0.4, "test": 0.6}
    if weights:
        w.update(weights)

    r_plan = 0.0
    r_test = 0.0
    total_weight = 0.0

    if plan_progress is not None:
        r_plan = reward_from_plan(plan_progress)
        total_weight += w["plan"]

    if test_result is not None:
        r_test = reward_from_tests(test_result)
        total_weight += w["test"]

    if total_weight == 0:
        return 0.0

    combined = (r_plan * w["plan"] + r_test * w["test"]) / total_weight
    return max(-1.0, min(1.0, combined))
