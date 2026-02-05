# upstream_learner/arms.py
"""
Arm definitions for multi-dimensional Thompson sampling.

These are the real knobs the learner can optimize:
- Planning strategy
- Prompt template
- Retrieval policy
- Search depth
- Test scope
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


ArmCategory = Literal["plan", "prompt", "retrieval", "search", "test"]


@dataclass(frozen=True)
class Arm:
    """A single learnable choice."""
    key: str
    category: ArmCategory
    description: str
    config: Mapping[str, Any] = None  # type: ignore

    def __post_init__(self):
        if self.config is None:
            object.__setattr__(self, "config", {})


# ============================================================
# Planning Strategy Arms
# ============================================================
PLAN_ARMS = [
    Arm("plan::direct", "plan", "Single-pass direct execution"),
    Arm("plan::decompose", "plan", "Break goal into sub-steps"),
    Arm("plan::search_first", "plan", "Explore search space before acting"),
    Arm("plan::ask_user", "plan", "Ask clarification when uncertain"),
]

# ============================================================
# Prompt Template Arms
# ============================================================
PROMPT_ARMS = [
    Arm(
        "prompt::minimal", "prompt",
        "Short patch prompt - minimal context",
        {"style": "minimal", "max_tokens": 500},
    ),
    Arm(
        "prompt::detailed", "prompt",
        "Verbose structured prompt with examples",
        {"style": "detailed", "max_tokens": 2000},
    ),
    Arm(
        "prompt::chain", "prompt",
        "Chain-of-thought: reason then act",
        {"style": "chain_of_thought", "max_tokens": 1500},
    ),
    Arm(
        "prompt::few_shot", "prompt",
        "Few-shot examples from similar tasks",
        {"style": "few_shot", "max_tokens": 2500},
    ),
]

# ============================================================
# Retrieval Policy Arms
# ============================================================
RETRIEVAL_ARMS = [
    Arm(
        "retrieval::none", "retrieval",
        "No file context - goal only",
        {"strategy": "none", "files": 0},
    ),
    Arm(
        "retrieval::top2", "retrieval",
        "Top 2 most relevant files",
        {"strategy": "top_k", "files": 2},
    ),
    Arm(
        "retrieval::top5", "retrieval",
        "Top 5 most relevant files",
        {"strategy": "top_k", "files": 5},
    ),
    Arm(
        "retrieval::focused", "retrieval",
        "Focused: only files mentioned in error",
        {"strategy": "focused", "files": -1},
    ),
    Arm(
        "retrieval::full", "retrieval",
        "Full context: all related files",
        {"strategy": "full", "files": 10},
    ),
]

# ============================================================
# Search Depth Arms
# ============================================================
SEARCH_ARMS = [
    Arm(
        "search::greedy", "search",
        "Greedy: single attempt",
        {"beam": 1, "depth": 1, "samples": 1},
    ),
    Arm(
        "search::beam3", "search",
        "Small beam search",
        {"beam": 3, "depth": 3, "samples": 3},
    ),
    Arm(
        "search::beam5", "search",
        "Wide beam search",
        {"beam": 5, "depth": 5, "samples": 5},
    ),
    Arm(
        "search::iterative", "search",
        "Iterative refinement",
        {"beam": 1, "depth": 5, "samples": 1, "refine": True},
    ),
]

# ============================================================
# Test Scope Arms
# ============================================================
TEST_ARMS = [
    Arm(
        "test::targeted", "test",
        "Run only failing tests first",
        {"scope": "targeted", "timeout": 60},
    ),
    Arm(
        "test::related", "test",
        "Run tests related to changed files",
        {"scope": "related", "timeout": 120},
    ),
    Arm(
        "test::full", "test",
        "Run full test suite",
        {"scope": "full", "timeout": 300},
    ),
]

# ============================================================
# Registry
# ============================================================
ALL_ARMS = PLAN_ARMS + PROMPT_ARMS + RETRIEVAL_ARMS + SEARCH_ARMS + TEST_ARMS

ARMS_BY_CATEGORY: dict[ArmCategory, list[Arm]] = {
    "plan": PLAN_ARMS,
    "prompt": PROMPT_ARMS,
    "retrieval": RETRIEVAL_ARMS,
    "search": SEARCH_ARMS,
    "test": TEST_ARMS,
}


def get_arms(category: ArmCategory) -> list[Arm]:
    """Get all arms for a category."""
    return ARMS_BY_CATEGORY.get(category, [])


def get_arm(key: str) -> Arm | None:
    """Look up an arm by key."""
    for arm in ALL_ARMS:
        if arm.key == key:
            return arm
    return None
