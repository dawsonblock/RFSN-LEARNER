# upstream_learner/arm_registry.py
"""
Multi-arm learner for Thompson sampling across categories.

Provides:
- Multi-dimensional arm selection
- Outcome recording
- Persistence via OutcomeDB
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .arms import Arm, ArmCategory, get_arms_for_category
from .bandit import ArmStats, BanditAlgorithm, select_arm
from .outcome_db import OutcomeDB, RichOutcome


@dataclass
class MultiArmSelection:
    """Selection of one arm per category."""

    arms: dict[ArmCategory, Arm]
    context_key: str
    seed: int

    def get(self, category: ArmCategory) -> Arm | None:
        """Get selected arm for category."""
        return self.arms.get(category)

    def to_dict(self) -> dict[str, str]:
        """Convert to dict of category -> arm_key."""
        return {cat: arm.arm_key for cat, arm in self.arms.items()}

    @property
    def config(self) -> dict[str, Mapping[str, Any]]:
        """Get combined config from all selected arms."""
        return {cat: dict(arm.config) for cat, arm in self.arms.items()}


class MultiArmLearner:
    """
    Multi-dimensional Thompson sampling learner.

    Selects best arm for each category independently,
    then records outcomes to learn over time.
    """

    def __init__(
        self,
        db: OutcomeDB,
        algorithm: BanditAlgorithm = BanditAlgorithm.THOMPSON,
        categories: list[ArmCategory] | None = None,
    ):
        self.db = db
        self.algorithm = algorithm
        self.categories = categories or ["plan", "prompt", "retrieval", "search", "test", "model"]

    def select(
        self,
        *,
        context_key: str,
        seed: int = 0,
        categories: list[ArmCategory] | None = None,
    ) -> MultiArmSelection:
        """
        Select best arm for each category.

        Args:
            context_key: Context identifier for learning
            seed: Random seed for reproducibility
            categories: Override default categories

        Returns:
            MultiArmSelection with one arm per category
        """
        cats = categories or self.categories
        result: dict[ArmCategory, Arm] = {}

        for i, cat in enumerate(cats):
            arms = get_arms_for_category(cat)
            if not arms:
                continue

            # Get stats for this category's arms in this context
            summary = self.db.summary(context_key=context_key)
            arm_keys = {arm.arm_key for arm in arms}
            stats = [ArmStats(arm_key=a, n=n, mean=mu) for (a, n, mu) in summary if a in arm_keys]

            # Select using bandit algorithm
            candidates = [arm.arm_key for arm in arms]
            selected_key = select_arm(
                candidates,
                stats,
                algorithm=self.algorithm,
                seed=seed + i,
            )

            result[cat] = next(arm for arm in arms if arm.arm_key == selected_key)

        return MultiArmSelection(
            arms=result,
            context_key=context_key,
            seed=seed,
        )

    def record(
        self,
        *,
        selection: MultiArmSelection,
        reward: float,
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Record outcome for all selected arms.

        Args:
            selection: The multi-arm selection
            reward: Reward value (0.0 to 1.0)
            meta: Optional metadata
        """
        ts = datetime.now(timezone.utc).isoformat()

        for cat, arm in selection.arms.items():
            payload = {
                "category": cat,
                "config": dict(arm.config),
            }
            if meta:
                payload["meta"] = dict(meta)

            self.db.record(
                context_key=selection.context_key,
                arm_key=arm.arm_key,
                reward=reward,
                meta_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ts_utc=ts,
            )

    def record_rich(
        self,
        *,
        selection: MultiArmSelection,
        reward: float,
        task_id: str = "",
        run_id: str = "",
        wall_time_ms: float = 0.0,
        tool_calls: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        patch_size: int = 0,
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Record rich outcome with full metrics.

        Args:
            selection: The multi-arm selection
            reward: Reward value
            task_id: Task identifier
            run_id: Run identifier
            wall_time_ms: Execution time
            tool_calls: Number of tool calls
            tests_passed: Tests passed
            tests_failed: Tests failed
            patch_size: Size of generated patch
            meta: Additional metadata
        """
        for cat, arm in selection.arms.items():
            self.db.record_rich(
                RichOutcome(
                    context_key=selection.context_key,
                    arm_key=arm.arm_key,
                    reward=reward,
                    task_id=task_id,
                    run_id=run_id,
                    seed=selection.seed,
                    wall_time_ms=wall_time_ms,
                    tool_calls=tool_calls,
                    gate_denials=0,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    tests_baseline_passed=0,
                    tests_baseline_failed=0,
                    patch_size_bytes=patch_size,
                    files_changed=0,
                    meta=dict(meta) if meta else {},
                )
            )

    def get_stats(self, context_key: str) -> dict[ArmCategory, list[ArmStats]]:
        """
        Get arm statistics per category.

        Returns:
            Dict mapping category to list of ArmStats
        """
        summary = self.db.summary(context_key=context_key)
        by_key = {a: (n, mu) for (a, n, mu) in summary}

        result: dict[ArmCategory, list[ArmStats]] = {}

        for cat in self.categories:
            arms = get_arms_for_category(cat)
            stats = []
            for arm in arms:
                if arm.arm_key in by_key:
                    n, mu = by_key[arm.arm_key]
                    stats.append(ArmStats(arm_key=arm.arm_key, n=n, mean=mu))
                else:
                    stats.append(ArmStats(arm_key=arm.arm_key, n=0, mean=0.0))
            result[cat] = stats

        return result
