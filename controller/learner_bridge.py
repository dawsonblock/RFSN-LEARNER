# controller/learner_bridge.py
"""
Thin integration layer that wires Thompson sampling into the plan execution loop.

This is the missing "glue" that:
  - chooses a planning strategy via learned selection (not heuristics)
  - selects arms across all categories via MultiArmLearner
  - records outcome reward after execution
  - feeds the bandit so it actually learns
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from controller.planner.reward import reward_from_plan_result
from controller.planner.types import Plan, PlanResult
from upstream_learner.arm_registry import MultiArmLearner, MultiArmSelection
from upstream_learner.outcome_db import OutcomeDB
from upstream_learner.propose import (
    ALL_STRATEGIES,
    PlanStrategy,
    record_strategy_outcome,
    select_strategy,
)


@dataclass
class LearnerConfig:
    db_path: str = "./tmp/outcomes.sqlite"
    enabled: bool = True


class LearnerBridge:
    """
    Thin integration layer:
      - chooses a planning strategy via Thompson sampling
      - selects arms across all categories
      - records outcome reward after execution

    This closes the loop: selection → execution → reward → record
    """

    def __init__(self, cfg: LearnerConfig):
        self.cfg = cfg
        if self.cfg.enabled:
            Path(self.cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.db = OutcomeDB(self.cfg.db_path)
            self.multi_arm_learner = MultiArmLearner(self.db)
        else:
            self.db = None
            self.multi_arm_learner = None

    def choose_plan_strategy(self, *, goal: str, seed: int = 0) -> PlanStrategy:
        """
        Use Thompson sampling to pick the best strategy for this goal type.

        Falls back to 'direct' if learner is disabled.
        """
        if not self.cfg.enabled or self.db is None:
            return "direct"

        return select_strategy(
            db=self.db,
            goal=goal,
            strategies=ALL_STRATEGIES,
            seed=seed,
        )

    def select_arms(
        self,
        *,
        context_key: str,
        seed: int = 0,
    ) -> MultiArmSelection | None:
        """
        Select arms across all categories using Thompson sampling.

        Returns None if learner is disabled.
        """
        if not self.multi_arm_learner:
            return None
        return self.multi_arm_learner.select(context_key=context_key, seed=seed)

    def record_plan_outcome(
        self,
        *,
        goal: str,
        strategy: PlanStrategy,
        plan: Plan,
        result: PlanResult,
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Record the outcome of executing a plan with a given strategy.

        This is what feeds the Thompson sampling algorithm so it learns
        which strategies work best for which goal types.
        """
        if not self.cfg.enabled or self.db is None:
            return

        reward = reward_from_plan_result(plan=plan, result=result)

        payload: dict[str, Any] = {
            "goal": goal,
            "strategy": strategy,
            "plan_id": plan.plan_id,
            "total_steps": result.total_steps,
            "completed_steps": result.completed_steps,
            "failed_steps": result.failed_steps,
            "success": result.success,
            "reward": reward,
        }
        if meta:
            payload["meta"] = dict(meta)

        # Use the proper record function from propose.py
        record_strategy_outcome(
            db=self.db,
            goal=goal,
            strategy=strategy,
            reward=float(reward),
            meta=payload,
            ts_utc=datetime.now(timezone.utc).isoformat(),
        )

    def record_rich_outcome(
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
        Record rich outcome with full metrics for multi-arm selection.

        Use this when recording outcomes from run_task or SWE-bench runs.
        """
        if not self.multi_arm_learner:
            return

        self.multi_arm_learner.record_rich(
            selection=selection,
            reward=reward,
            task_id=task_id,
            run_id=run_id,
            wall_time_ms=wall_time_ms,
            tool_calls=tool_calls,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            patch_size=patch_size,
            meta=meta,
        )
