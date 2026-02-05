# tests/test_learner.py
"""
Learner integration tests.

Tests for Thompson sampling, outcome recording, and arm selection.
"""

import tempfile
from pathlib import Path

from upstream_learner.bandit import ArmStats, thompson_select
from upstream_learner.outcome_db import OutcomeDB
from upstream_learner.propose import (
    ALL_STRATEGIES,
    context_key_from_goal,
    record_strategy_outcome,
    select_strategy,
)


class TestOutcomeDB:
    """OutcomeDB persistence tests."""

    def test_creates_database(self):
        """DB file is created on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.sqlite"
            db = OutcomeDB(str(path))
            assert path.exists()

    def test_records_outcome(self):
        """Outcomes are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.sqlite"
            db = OutcomeDB(str(path))

            db.record(
                context_key="test::ctx",
                arm_key="arm1",
                reward=0.8,
                meta_json="{}",
                ts_utc="2026-01-01T00:00:00Z",
            )

            summary = db.summary(context_key="test::ctx")
            assert len(summary) == 1
            assert summary[0][0] == "arm1"
            assert summary[0][1] == 1  # count
            assert summary[0][2] == 0.8  # mean

    def test_aggregates_multiple_outcomes(self):
        """Multiple outcomes are aggregated correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.sqlite"
            db = OutcomeDB(str(path))

            for reward in [0.6, 0.8, 1.0]:
                db.record(
                    context_key="test::ctx",
                    arm_key="arm1",
                    reward=reward,
                    meta_json="{}",
                    ts_utc="2026-01-01T00:00:00Z",
                )

            summary = db.summary(context_key="test::ctx")
            assert summary[0][1] == 3  # count
            assert abs(summary[0][2] - 0.8) < 0.01  # mean


class TestThompsonSampling:
    """Thompson sampling algorithm tests."""

    def test_selects_from_arms(self):
        """Thompson select returns one of the arms."""
        arms = ["a", "b", "c"]
        stats = []

        selected = thompson_select(arms, stats, seed=42)
        assert selected in arms

    def test_deterministic_with_seed(self):
        """Same seed produces same selection."""
        arms = ["a", "b", "c"]
        stats = [
            ArmStats("a", 10, 0.5),
            ArmStats("b", 10, 0.7),
            ArmStats("c", 10, 0.3),
        ]

        result1 = thompson_select(arms, stats, seed=42)
        result2 = thompson_select(arms, stats, seed=42)
        assert result1 == result2

    def test_exploits_high_mean(self):
        """With enough data, prefers higher mean arms."""
        arms = ["low", "high"]
        stats = [
            ArmStats("low", 100, 0.1),
            ArmStats("high", 100, 0.9),
        ]

        # Run multiple times with different seeds
        selections = [thompson_select(arms, stats, seed=i) for i in range(100)]
        high_count = selections.count("high")

        # Should select "high" most of the time
        assert high_count > 70


class TestStrategySelection:
    """Strategy selection integration tests."""

    def test_context_key_extraction(self):
        """Context keys are extracted from goals."""
        key = context_key_from_goal("list files in directory")
        assert key.startswith("goal::")

    def test_selects_valid_strategy(self):
        """Selects a valid strategy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.sqlite"
            db = OutcomeDB(str(path))

            strategy = select_strategy(
                db=db,
                goal="list files",
                strategies=ALL_STRATEGIES,
                seed=42,
            )

            assert strategy in ALL_STRATEGIES

    def test_records_strategy_outcome(self):
        """Strategy outcomes are recorded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.sqlite"
            db = OutcomeDB(str(path))

            record_strategy_outcome(
                db=db,
                goal="list files",
                strategy="direct",
                reward=0.9,
                meta={"test": True},
                ts_utc="2026-01-01T00:00:00Z",
            )

            ctx = context_key_from_goal("list files")
            summary = db.summary(context_key=ctx)
            assert len(summary) == 1
