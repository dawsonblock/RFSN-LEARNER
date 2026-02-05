# tests/test_arms.py
"""
Tests for arm registry and multi-arm selection.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from upstream_learner.arms import (
    ALL_ARMS,
    ARMS_BY_CATEGORY,
    get_arm,
    get_arms,
    Arm,
)
from upstream_learner.outcome_db import OutcomeDB
from controller.run_task import MultiArmLearner


class TestArmRegistry:
    """Arm registry tests."""

    def test_all_arms_populated(self):
        """Registry has arms."""
        assert len(ALL_ARMS) > 10

    def test_categories_populated(self):
        """Each category has arms."""
        for cat in ["plan", "prompt", "retrieval", "search", "test"]:
            arms = get_arms(cat)
            assert len(arms) >= 2, f"{cat} should have at least 2 arms"

    def test_get_arm_by_key(self):
        """Can look up arm by key."""
        arm = get_arm("plan::direct")
        assert arm is not None
        assert arm.category == "plan"

    def test_arm_has_description(self):
        """All arms have descriptions."""
        for arm in ALL_ARMS:
            assert arm.description, f"{arm.key} missing description"


class TestMultiArmLearner:
    """Multi-arm learner tests."""

    def test_selects_arm_per_category(self):
        """Learner selects one arm per category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.sqlite")
            learner = MultiArmLearner(db_path=db_path, enabled=True)

            arms = learner.select_all_arms(
                context_key="test",
                seed=42,
            )

            assert len(arms) == 5
            for cat in ["plan", "prompt", "retrieval", "search", "test"]:
                assert cat in arms
                assert isinstance(arms[cat], Arm)

    def test_deterministic_with_seed(self):
        """Same seed produces same selections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.sqlite")
            learner = MultiArmLearner(db_path=db_path, enabled=True)

            arms1 = learner.select_all_arms(context_key="test", seed=42)
            arms2 = learner.select_all_arms(context_key="test", seed=42)

            for cat in arms1:
                assert arms1[cat].key == arms2[cat].key

    def test_records_outcomes(self):
        """Outcomes are recorded for all arms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.sqlite")
            learner = MultiArmLearner(db_path=db_path, enabled=True)

            arms = learner.select_all_arms(context_key="test", seed=42)
            learner.record_outcome(
                context_key="test",
                arms=arms,
                reward=0.8,
                meta={"task": "demo"},
            )

            # Check DB has entries
            import sqlite3
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
            assert count == 5  # One per category
