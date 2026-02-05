# tests/test_reward.py
"""
Tests for unified reward function.
"""

from __future__ import annotations

from controller.reward.combine import (
    PlanProgress,
    TestOutcome,
    combined_reward,
    reward_from_plan,
    reward_from_tests,
)


class TestPlanReward:
    """Plan progress reward tests."""

    def test_full_success(self):
        """Full success gets max reward."""
        progress = PlanProgress(
            total_steps=3,
            completed_steps=3,
            failed_steps=0,
            success=True,
        )
        r = reward_from_plan(progress)
        assert r == 1.0

    def test_partial_completion(self):
        """Partial completion gets partial reward."""
        progress = PlanProgress(
            total_steps=4,
            completed_steps=2,
            failed_steps=0,
            success=False,
        )
        r = reward_from_plan(progress)
        assert 0 < r < 1

    def test_failure_penalty(self):
        """Failed steps reduce reward."""
        progress = PlanProgress(
            total_steps=3,
            completed_steps=1,
            failed_steps=2,
            success=False,
        )
        r = reward_from_plan(progress)
        assert r < 0.5


class TestTestReward:
    """Test result reward tests."""

    def test_fixed_all_tests(self):
        """Fixing all failing tests gets high reward."""
        result = TestOutcome(
            passed=10,
            failed=0,
            baseline_passed=7,
            baseline_failed=3,
        )
        r = reward_from_tests(result)
        assert r == 1.0

    def test_broke_tests(self):
        """Breaking tests gets negative reward."""
        result = TestOutcome(
            passed=5,
            failed=5,
            baseline_passed=10,
            baseline_failed=0,
        )
        r = reward_from_tests(result)
        assert r < 0


class TestCombinedReward:
    """Combined reward tests."""

    def test_plan_only(self):
        """Works with plan only."""
        progress = PlanProgress(total_steps=2, completed_steps=2, success=True)
        r = combined_reward(plan_progress=progress)
        assert r == 1.0

    def test_blended(self):
        """Blends plan and test rewards."""
        progress = PlanProgress(total_steps=2, completed_steps=2, success=True)
        result = TestOutcome(passed=8, failed=2, baseline_passed=7, baseline_failed=3)

        r = combined_reward(plan_progress=progress, test_result=result)
        assert 0 < r < 1

    def test_clamped_to_range(self):
        """Result is always in [-1, 1]."""
        progress = PlanProgress(total_steps=10, completed_steps=10, success=True)
        result = TestOutcome(passed=100, failed=0, baseline_passed=50, baseline_failed=50)

        r = combined_reward(plan_progress=progress, test_result=result)
        assert -1 <= r <= 1
