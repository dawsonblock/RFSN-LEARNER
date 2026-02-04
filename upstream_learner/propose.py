from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from .bandit import ArmStats, thompson_select
from .outcome_db import OutcomeDB
from rfsn.types import ProposedAction


# Planning strategies that can be learned over
PlanStrategy = Literal["direct", "decompose", "search_first", "ask_user"]
ALL_STRATEGIES: list[PlanStrategy] = ["direct", "decompose", "search_first", "ask_user"]


@dataclass(frozen=True)
class Candidate:
    arm_key: str
    action: ProposedAction


def context_key_from_task(task: Mapping[str, Any]) -> str:
    return f"{task.get('benchmark','unknown')}::{task.get('task_id','unknown')}"


def context_key_from_goal(goal: str) -> str:
    """Create context key for strategy learning."""
    # Normalize goal to category
    goal_lower = goal.lower()
    if any(w in goal_lower for w in ["list", "show", "find"]):
        return "goal::list_find"
    elif any(w in goal_lower for w in ["read", "analyze", "summarize"]):
        return "goal::read_analyze"
    elif any(w in goal_lower for w in ["create", "write", "make"]):
        return "goal::create_write"
    elif any(w in goal_lower for w in ["search", "look for"]):
        return "goal::search"
    else:
        return "goal::general"


def select_candidate(
    *,
    db: OutcomeDB,
    task: Mapping[str, Any],
    candidates: Sequence[Candidate],
    seed: int = 0,
) -> ProposedAction:
    ctx = context_key_from_task(task)
    summary = db.summary(context_key=ctx)
    stats = [ArmStats(arm_key=a, n=n, mean=mu) for (a, n, mu) in summary]

    arm = thompson_select([c.arm_key for c in candidates], stats, seed=seed)
    chosen = next(c for c in candidates if c.arm_key == arm)
    return chosen.action


def select_strategy(
    *,
    db: OutcomeDB,
    goal: str,
    strategies: Sequence[PlanStrategy] | None = None,
    seed: int = 0,
) -> PlanStrategy:
    """
    Select the best planning strategy for a goal using Thompson sampling.
    
    Learns from past outcomes which strategy works best for different goal types.
    """
    if strategies is None:
        strategies = ALL_STRATEGIES
    
    ctx = context_key_from_goal(goal)
    summary = db.summary(context_key=ctx)
    stats = [ArmStats(arm_key=a, n=n, mean=mu) for (a, n, mu) in summary]
    
    selected = thompson_select(list(strategies), stats, seed=seed)
    return selected  # type: ignore


def record_outcome(
    *,
    db: OutcomeDB,
    task: Mapping[str, Any],
    arm_key: str,
    reward: float,
    meta: Mapping[str, Any],
    ts_utc: str,
) -> None:
    ctx = context_key_from_task(task)
    db.record(
        context_key=ctx,
        arm_key=arm_key,
        reward=reward,
        meta_json=json.dumps(meta, sort_keys=True, separators=(",", ":")),
        ts_utc=ts_utc,
    )


def record_strategy_outcome(
    *,
    db: OutcomeDB,
    goal: str,
    strategy: PlanStrategy,
    reward: float,
    meta: Mapping[str, Any],
    ts_utc: str,
) -> None:
    """
    Record the outcome of using a planning strategy.
    
    This feeds the Thompson sampling algorithm for strategy selection.
    """
    ctx = context_key_from_goal(goal)
    db.record(
        context_key=ctx,
        arm_key=strategy,
        reward=reward,
        meta_json=json.dumps(meta, sort_keys=True, separators=(",", ":")),
        ts_utc=ts_utc,
    )

