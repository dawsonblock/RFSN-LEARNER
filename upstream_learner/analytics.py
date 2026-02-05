# upstream_learner/analytics.py
"""
Learning analytics and visualization data.

Provides:
- Learning curves
- Arm performance rankings
- Convergence detection
- Experiment summaries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bandit import ArmStats, estimate_regret
from .outcome_db import OutcomeDB


@dataclass
class ArmPerformance:
    """Performance metrics for a single arm."""

    arm_key: str
    count: int
    mean_reward: float
    min_reward: float
    max_reward: float
    std_dev: float
    last_used: str = ""

    @property
    def confidence_interval(self) -> tuple[float, float]:
        """95% confidence interval for mean."""
        import math

        if self.count < 2:
            return (self.mean_reward, self.mean_reward)
        margin = 1.96 * self.std_dev / math.sqrt(self.count)
        return (self.mean_reward - margin, self.mean_reward + margin)


@dataclass
class LearningCurve:
    """Learning curve for an experiment."""

    arm_key: str | None
    points: list[tuple[int, float, float]]  # (index, window_mean, cumulative_mean)
    total_rewards: float
    total_count: int

    @property
    def final_mean(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.total_rewards / self.total_count

    def is_converged(self, threshold: float = 0.05, window: int = 20) -> bool:
        """Check if learning has converged (variance < threshold in recent window)."""
        if len(self.points) < window:
            return False

        recent = [p[2] for p in self.points[-window:]]
        if not recent:
            return False

        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        return variance < threshold


@dataclass
class ExperimentSummary:
    """Summary of a learning experiment."""

    total_trials: int
    unique_arms: int
    best_arm: str
    best_mean: float
    worst_arm: str
    worst_mean: float
    estimated_regret: float
    arms: list[ArmPerformance]


class LearningAnalytics:
    """Analytics engine for learning experiments."""

    def __init__(self, db: OutcomeDB):
        self.db = db

    def arm_rankings(
        self,
        context_pattern: str | None = None,
        limit: int = 50,
    ) -> list[ArmPerformance]:
        """
        Get arm performance rankings.

        Args:
            context_pattern: Optional SQL LIKE pattern to filter contexts
            limit: Maximum number of arms to return

        Returns:
            List of ArmPerformance sorted by mean reward (descending)
        """
        perf = self.db.arm_performance()

        results = []
        for arm_key, stats in perf.items():
            results.append(
                ArmPerformance(
                    arm_key=arm_key,
                    count=stats["count"],
                    mean_reward=stats["mean"],
                    min_reward=stats["min"],
                    max_reward=stats["max"],
                    std_dev=0.0,  # Could compute from raw data
                )
            )

        results.sort(key=lambda x: x.mean_reward, reverse=True)
        return results[:limit]

    def learning_curve(
        self,
        arm_key: str | None = None,
        task_id: str | None = None,
        window: int = 10,
    ) -> LearningCurve:
        """
        Get learning curve for an arm or task.

        Args:
            arm_key: Filter by arm (optional)
            task_id: Filter by task (optional)
            window: Window size for rolling mean

        Returns:
            LearningCurve with (index, window_mean, cumulative_mean) points
        """
        points = self.db.learning_curve(
            arm_key=arm_key,
            task_id=task_id,
            window=window,
        )

        total = sum(p[2] for p in points) if points else 0.0

        return LearningCurve(
            arm_key=arm_key,
            points=points,
            total_rewards=total,
            total_count=len(points),
        )

    def experiment_summary(self, context_key: str | None = None) -> ExperimentSummary:
        """
        Get summary of learning experiment.

        Args:
            context_key: Specific context to analyze (or all if None)

        Returns:
            ExperimentSummary with aggregate statistics
        """
        rankings = self.arm_rankings()

        if not rankings:
            return ExperimentSummary(
                total_trials=0,
                unique_arms=0,
                best_arm="",
                best_mean=0.0,
                worst_arm="",
                worst_mean=0.0,
                estimated_regret=0.0,
                arms=[],
            )

        total_trials = sum(a.count for a in rankings)

        # Compute regret
        stats = [ArmStats(arm_key=a.arm_key, n=a.count, mean=a.mean_reward) for a in rankings]
        regret = estimate_regret(stats, total_trials)

        return ExperimentSummary(
            total_trials=total_trials,
            unique_arms=len(rankings),
            best_arm=rankings[0].arm_key,
            best_mean=rankings[0].mean_reward,
            worst_arm=rankings[-1].arm_key,
            worst_mean=rankings[-1].mean_reward,
            estimated_regret=regret,
            arms=rankings,
        )

    def compare_arms(
        self,
        arm_keys: list[str],
        metric: str = "mean",
    ) -> dict[str, float]:
        """
        Compare specific arms on a metric.

        Args:
            arm_keys: Arms to compare
            metric: "mean", "count", "max", "min"

        Returns:
            Dict mapping arm_key to metric value
        """
        perf = self.db.arm_performance()

        result = {}
        for key in arm_keys:
            if key in perf:
                result[key] = perf[key].get(metric, 0.0)
            else:
                result[key] = 0.0

        return result

    def export_data(self, limit: int = 1000) -> dict[str, Any]:
        """
        Export learning data for external analysis.

        Returns:
            Dict with outcomes, rankings, curves
        """
        recent = self.db.recent_outcomes(limit=limit)
        rankings = self.arm_rankings()
        summary = self.experiment_summary()

        return {
            "summary": {
                "total_trials": summary.total_trials,
                "unique_arms": summary.unique_arms,
                "best_arm": summary.best_arm,
                "best_mean": summary.best_mean,
                "estimated_regret": summary.estimated_regret,
            },
            "rankings": [
                {
                    "arm_key": a.arm_key,
                    "count": a.count,
                    "mean": a.mean_reward,
                    "min": a.min_reward,
                    "max": a.max_reward,
                }
                for a in rankings
            ],
            "outcomes": [
                {
                    "arm_key": o.arm_key,
                    "reward": o.reward,
                    "task_id": o.task_id,
                    "ts": o.ts_utc,
                }
                for o in recent
            ],
        }
