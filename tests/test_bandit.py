# tests/test_bandit.py
"""
Tests for bandit algorithms.
"""

from __future__ import annotations

from upstream_learner.bandit import (
    ArmStats,
    BanditAlgorithm,
    epsilon_greedy_select,
    estimate_regret,
    select_arm,
    thompson_select,
    ucb_select,
)


class TestThompsonSampling:
    """Thompson sampling tests."""

    def test_selects_from_candidates(self):
        """Returns a valid candidate."""
        candidates = ["a", "b", "c"]
        result = thompson_select(candidates, [], seed=42)
        assert result in candidates

    def test_deterministic_with_seed(self):
        """Same seed gives same result."""
        candidates = ["a", "b", "c"]
        r1 = thompson_select(candidates, [], seed=123)
        r2 = thompson_select(candidates, [], seed=123)
        assert r1 == r2

    def test_exploits_high_mean(self):
        """After many observations, exploits high mean arm."""
        stats = [
            ArmStats("good", 100, 0.9),
            ArmStats("ok", 100, 0.5),
            ArmStats("bad", 100, 0.1),
        ]
        # With high n, should usually pick good
        results = [thompson_select(["good", "ok", "bad"], stats, seed=i) for i in range(20)]
        assert results.count("good") > 10


class TestUCB:
    """UCB1 tests."""

    def test_explores_unvisited(self):
        """UCB explores unvisited arms first."""
        stats = [ArmStats("visited", 10, 0.5)]
        result = ucb_select(["visited", "new"], stats)
        assert result == "new"

    def test_balances_exploration(self):
        """UCB balances exploration and exploitation."""
        stats = [
            ArmStats("high", 100, 0.8),
            ArmStats("low", 100, 0.2),
        ]
        result = ucb_select(["high", "low"], stats, total_pulls=200)
        # With equal pulls, should pick higher mean
        assert result == "high"


class TestEpsilonGreedy:
    """Epsilon-greedy tests."""

    def test_mostly_exploits(self):
        """Low epsilon mostly exploits."""
        stats = [
            ArmStats("best", 50, 0.9),
            ArmStats("worst", 50, 0.1),
        ]
        # With epsilon=0, should always exploit
        results = [
            epsilon_greedy_select(["best", "worst"], stats, epsilon=0.0, seed=i) for i in range(20)
        ]
        assert all(r == "best" for r in results)

    def test_explores_with_high_epsilon(self):
        """High epsilon explores."""
        stats = [ArmStats("only", 100, 0.5)]
        results = [
            epsilon_greedy_select(["only", "other"], stats, epsilon=1.0, seed=i) for i in range(20)
        ]
        # With epsilon=1, should be random
        assert "other" in results


class TestUnifiedSelect:
    """Unified select_arm tests."""

    def test_thompson_algorithm(self):
        """Works with Thompson algorithm."""
        result = select_arm(
            ["a", "b"],
            [],
            algorithm=BanditAlgorithm.THOMPSON,
            seed=42,
        )
        assert result in ["a", "b"]

    def test_ucb_algorithm(self):
        """Works with UCB algorithm."""
        result = select_arm(
            ["a", "b"],
            [],
            algorithm=BanditAlgorithm.UCB1,
        )
        assert result in ["a", "b"]


class TestRegret:
    """Regret estimation tests."""

    def test_zero_regret_optimal(self):
        """Optimal selection has zero regret."""
        stats = [
            ArmStats("best", 100, 0.9),
        ]
        regret = estimate_regret(stats)
        assert regret == 0.0

    def test_positive_regret_suboptimal(self):
        """Suboptimal selection has positive regret."""
        stats = [
            ArmStats("best", 10, 0.9),
            ArmStats("worst", 90, 0.1),
        ]
        regret = estimate_regret(stats)
        # Regret = (0.9 - 0.1) * 90 = 72.0
        assert regret > 0
