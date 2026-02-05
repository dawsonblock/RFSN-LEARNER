# upstream_learner/__init__.py
"""
Upstream Learner - Multi-armed bandit learning for agent strategies.

This module provides:
- Multi-dimensional Thompson sampling over configurable arms
- Outcome recording and learning curve analysis
- Support for multiple bandit algorithms (Thompson, UCB1, epsilon-greedy)

Quick Start:
    from upstream_learner import MultiArmLearner, OutcomeDB

    db = OutcomeDB("outcomes.sqlite")
    learner = MultiArmLearner(db)

    # Select arms for a task
    selection = learner.select(context_key="task::001", seed=42)

    # Use selected configurations...

    # Record outcome
    learner.record(selection=selection, reward=0.8)
"""

from __future__ import annotations

from .analytics import (
    ArmPerformance,
    ExperimentSummary,
    LearningAnalytics,
    LearningCurve,
)
from .arm_registry import (
    MultiArmLearner,
    MultiArmSelection,
)
from .arms import (
    ALL_ARMS,
    ARMS_BY_CATEGORY,
    ARMS_BY_KEY,
    Arm,
    ArmCategory,
    get_arm,
    get_arms_for_category,
    list_categories,
)
from .bandit import (
    ArmStats,
    BanditAlgorithm,
    epsilon_greedy_select,
    estimate_regret,
    select_arm,
    thompson_select,
    ucb_select,
)
from .outcome_db import (
    Outcome,
    OutcomeDB,
    RichOutcome,
)
from .propose import (
    ALL_STRATEGIES,
    Candidate,
    PlanStrategy,
    context_key_from_goal,
    context_key_from_task,
    record_outcome,
    record_strategy_outcome,
    select_candidate,
    select_strategy,
)

__all__ = [
    # Arms
    "Arm",
    "ArmCategory",
    "ALL_ARMS",
    "ARMS_BY_CATEGORY",
    "ARMS_BY_KEY",
    "get_arm",
    "get_arms_for_category",
    "list_categories",
    # Learner
    "MultiArmLearner",
    "MultiArmSelection",
    # Bandit
    "ArmStats",
    "BanditAlgorithm",
    "select_arm",
    "thompson_select",
    "ucb_select",
    "epsilon_greedy_select",
    "estimate_regret",
    # Storage
    "OutcomeDB",
    "Outcome",
    "RichOutcome",
    # Analytics
    "LearningAnalytics",
    "LearningCurve",
    "ArmPerformance",
    "ExperimentSummary",
    # Propose
    "Candidate",
    "select_candidate",
    "select_strategy",
    "record_outcome",
    "record_strategy_outcome",
    "context_key_from_task",
    "context_key_from_goal",
    "PlanStrategy",
    "ALL_STRATEGIES",
]
