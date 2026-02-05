# controller/run_task.py
"""
Deterministic batch runner for headless task execution.

Usage:
    python -m controller.run_task --task task.json --seed 42 --out ./results

This is the real execution path for SWE-bench-style evaluation:
- Deterministic seeding
- Full arm selection (not just strategy)
- Outcome recording with rich metadata
- Artifact output (ledger, result.json)
"""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rfsn.types import WorldSnapshot
from rfsn.policy import DEV_POLICY
from rfsn.ledger import AppendOnlyLedger

from .tool_router import ExecutionContext
from .reward.combine import combined_reward, PlanProgress, TestOutcome
from .planner.generator import generate_plan
from .planner.executor import execute_plan

from upstream_learner.outcome_db import OutcomeDB
from upstream_learner.bandit import thompson_select, ArmStats
from upstream_learner.arms import ARMS_BY_CATEGORY, Arm, ArmCategory


def load_task(path: str) -> dict[str, Any]:
    """Load task from JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def create_snapshot(task: dict[str, Any]) -> WorldSnapshot:
    """Create WorldSnapshot from task definition."""
    return WorldSnapshot(
        session_id=task.get("id", "task"),
        world_state_hash=task.get("state_hash", "unknown"),
        enabled_tools=tuple(sorted(DEV_POLICY.allowed_tools)),
        permissions=frozenset(),
        system_clean=True,
        metadata=task.get("metadata", {}),
    )


class MultiArmLearner:
    """
    Learner that selects arms across all categories.
    """
    
    def __init__(self, db_path: str, enabled: bool = True):
        self.db = OutcomeDB(db_path) if enabled else None
        self.enabled = enabled
    
    def select_arm(
        self,
        category: ArmCategory,
        context_key: str,
        seed: int = 0,
    ) -> Arm:
        """Select best arm for a category using Thompson sampling."""
        arms = ARMS_BY_CATEGORY.get(category, [])
        if not arms:
            raise ValueError(f"No arms for category: {category}")
        
        arm_keys = [a.key for a in arms]
        
        if self.db is None:
            # Random selection when disabled
            random.seed(seed)
            return random.choice(arms)
        
        # Get historical stats
        summary = self.db.summary(context_key=context_key)
        stats = [ArmStats(arm_key=a, n=n, mean=mu) for (a, n, mu) in summary]
        
        selected_key = thompson_select(arm_keys, stats, seed=seed)
        return next((a for a in arms if a.key == selected_key), arms[0])
    
    def select_all_arms(
        self,
        context_key: str,
        seed: int = 0,
    ) -> dict[ArmCategory, Arm]:
        """Select arms for all categories."""
        result: dict[ArmCategory, Arm] = {}
        for i, category in enumerate(ARMS_BY_CATEGORY.keys()):
            result[category] = self.select_arm(
                category=category,  # type: ignore
                context_key=f"{context_key}::{category}",
                seed=seed + i,
            )
        return result
    
    def record_outcome(
        self,
        context_key: str,
        arms: dict[ArmCategory, Arm],
        reward: float,
        meta: dict[str, Any],
    ) -> None:
        """Record outcome for all selected arms."""
        if self.db is None:
            return
        
        ts = datetime.now(timezone.utc).isoformat()
        
        for category, arm in arms.items():
            self.db.record(
                context_key=f"{context_key}::{category}",
                arm_key=arm.key,
                reward=float(reward),
                meta_json=json.dumps(meta, sort_keys=True, separators=(",", ":")),
                ts_utc=ts,
            )


def run_task(
    task: dict[str, Any],
    seed: int,
    out_dir: Path,
    db_path: str,
) -> dict[str, Any]:
    """
    Execute a single task deterministically.
    
    Returns result dict with:
        - success: bool
        - reward: float
        - arms: selected arm keys
        - timing: execution times
    """
    random.seed(seed)
    start_time = time.time()
    
    task_id = task.get("id", "unknown")
    goal = task.get("goal", "")
    context_key = f"task::{task_id}"
    
    # Initialize
    learner = MultiArmLearner(db_path=db_path, enabled=True)
    snapshot = create_snapshot(task)
    context = ExecutionContext(session_id=task_id)
    ledger = AppendOnlyLedger(str(out_dir / "ledger.jsonl"))
    
    # ---- Select arms ----
    arms = learner.select_all_arms(context_key=context_key, seed=seed)
    arm_keys = {cat: arm.key for cat, arm in arms.items()}
    
    # ---- Get strategy from plan arm ----
    plan_arm = arms.get("plan")
    strategy = plan_arm.key.split("::")[-1] if plan_arm else "direct"
    
    # ---- Generate plan ----
    plan = generate_plan(goal, snapshot, strategy=strategy)
    
    # ---- Execute plan ----
    result = execute_plan(plan, context, snapshot, policy=DEV_POLICY)
    
    # ---- Compute reward ----
    plan_progress = PlanProgress(
        total_steps=result.total_steps,
        completed_steps=result.completed_steps,
        failed_steps=len([s for s in plan.steps if s.status == "failed"]),
        success=result.success,
    )
    
    # Test result (from task if provided)
    test_result = None
    if "test_result" in task:
        tr = task["test_result"]
        test_result = TestOutcome(
            passed=tr.get("passed", 0),
            failed=tr.get("failed", 0),
            baseline_passed=tr.get("baseline_passed", 0),
            baseline_failed=tr.get("baseline_failed", 0),
        )
    
    reward = combined_reward(plan_progress=plan_progress, test_result=test_result)
    
    end_time = time.time()
    
    # ---- Record outcome ----
    meta = {
        "task_id": task_id,
        "seed": seed,
        "goal": goal[:100],
        "reward": reward,
        "success": result.success,
        "completed": result.completed_steps,
        "total": result.total_steps,
        "wall_time": end_time - start_time,
    }
    
    learner.record_outcome(
        context_key=context_key,
        arms=arms,
        reward=reward,
        meta=meta,
    )
    
    # ---- Build result ----
    output = {
        "task_id": task_id,
        "success": result.success,
        "reward": reward,
        "arms": arm_keys,
        "strategy": strategy,
        "completed_steps": result.completed_steps,
        "total_steps": result.total_steps,
        "wall_time": end_time - start_time,
        "seed": seed,
    }
    
    # ---- Save artifacts ----
    with open(out_dir / "result.json", "w") as f:
        json.dump(output, f, indent=2)
    
    return output


def main():
    parser = argparse.ArgumentParser(description="Run task deterministically")
    parser.add_argument("--task", required=True, help="Path to task JSON")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--out", default="./tmp/run", help="Output directory")
    parser.add_argument("--db", default="./tmp/outcomes.sqlite", help="Outcome DB path")
    args = parser.parse_args()
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    task = load_task(args.task)
    
    print(f"Running task: {task.get('id', 'unknown')}")
    print(f"Goal: {task.get('goal', '')[:80]}...")
    print(f"Seed: {args.seed}")
    print()
    
    result = run_task(
        task=task,
        seed=args.seed,
        out_dir=out_dir,
        db_path=args.db,
    )
    
    print("===== RESULT =====")
    print(f"Success: {result['success']}")
    print(f"Reward:  {result['reward']:.3f}")
    print(f"Arms:    {result['arms']}")
    print(f"Steps:   {result['completed_steps']}/{result['total_steps']}")
    print(f"Time:    {result['wall_time']:.2f}s")


if __name__ == "__main__":
    main()
