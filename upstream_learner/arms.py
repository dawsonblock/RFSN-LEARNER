# upstream_learner/arms.py
"""
Unified arm definitions for multi-dimensional Thompson sampling.

Categories:
- plan: How to break down tasks
- prompt: LLM prompting strategies
- retrieval: Context retrieval methods
- search: Search depth / beam width
- test: Test execution scope
- model: Which LLM to use
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

ArmCategory = Literal["plan", "prompt", "retrieval", "search", "test", "model"]


@dataclass
class Arm:
    """A single learnable choice."""

    key: str
    category: ArmCategory
    config: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def arm_key(self) -> str:
        """Full arm key including category prefix."""
        if "::" in self.key:
            return self.key
        return f"{self.category}::{self.key}"


# =============================================================================
# PLAN ARMS - How to break down tasks
# =============================================================================
PLAN_ARMS = [
    Arm("direct", "plan", {"strategy": "direct"}, "Execute directly without decomposition"),
    Arm(
        "decompose",
        "plan",
        {"strategy": "decompose", "max_steps": 5},
        "Decompose into subtasks first",
    ),
    Arm("search_first", "plan", {"strategy": "search_first"}, "Search codebase before acting"),
    Arm(
        "iterative",
        "plan",
        {"strategy": "iterative", "max_rounds": 3},
        "Iterative refinement approach",
    ),
]

# =============================================================================
# PROMPT ARMS - LLM prompting strategies
# =============================================================================
PROMPT_ARMS = [
    Arm("concise", "prompt", {"style": "concise", "max_tokens": 200}, "Short, direct instructions"),
    Arm(
        "detailed",
        "prompt",
        {"style": "detailed", "include_examples": True},
        "Detailed with examples",
    ),
    Arm(
        "cot",
        "prompt",
        {"style": "chain_of_thought", "think_first": True},
        "Chain-of-thought reasoning",
    ),
    Arm(
        "structured",
        "prompt",
        {"style": "structured", "format": "json"},
        "Structured output format",
    ),
]

# =============================================================================
# RETRIEVAL ARMS - Context retrieval methods
# =============================================================================
RETRIEVAL_ARMS = [
    Arm("none", "retrieval", {"strategy": "none"}, "No context retrieval"),
    Arm(
        "file_list",
        "retrieval",
        {"strategy": "file_list", "max_files": 10},
        "List relevant files only",
    ),
    Arm("snippets", "retrieval", {"strategy": "snippets", "max_lines": 200}, "Key code snippets"),
    Arm(
        "full_context",
        "retrieval",
        {"strategy": "full_context", "max_files": 5},
        "Full file contents",
    ),
    Arm(
        "semantic",
        "retrieval",
        {"strategy": "semantic", "embeddings": True},
        "Semantic similarity search",
    ),
]

# =============================================================================
# SEARCH ARMS - Search depth / beam width
# =============================================================================
SEARCH_ARMS = [
    Arm("shallow", "search", {"depth": 1, "beam": 1}, "Single attempt"),
    Arm("medium", "search", {"depth": 3, "beam": 2}, "3 attempts, beam 2"),
    Arm("deep", "search", {"depth": 5, "beam": 3}, "5 attempts, beam 3"),
    Arm("exhaustive", "search", {"depth": 10, "beam": 5}, "Exhaustive search"),
]

# =============================================================================
# TEST ARMS - Test execution scope
# =============================================================================
TEST_ARMS = [
    Arm("minimal", "test", {"scope": "affected", "max_tests": 5}, "Only directly affected tests"),
    Arm("related", "test", {"scope": "related", "max_tests": 20}, "Related test files"),
    Arm("full", "test", {"scope": "full", "timeout": 300}, "Full test suite"),
]

# =============================================================================
# MODEL ARMS - Which LLM to use
# =============================================================================
MODEL_ARMS = [
    Arm(
        "gpt4o_mini",
        "model",
        {"provider": "openai", "model": "gpt-4o-mini"},
        "GPT-4o-mini (fast, cheap)",
    ),
    Arm("gpt4o", "model", {"provider": "openai", "model": "gpt-4o"}, "GPT-4o (balanced)"),
    Arm(
        "claude_sonnet",
        "model",
        {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        "Claude Sonnet (precise)",
    ),
    Arm(
        "deepseek",
        "model",
        {"provider": "deepseek", "model": "deepseek-chat"},
        "DeepSeek Chat (cost-effective)",
    ),
]

# =============================================================================
# UNIFIED REGISTRY
# =============================================================================
ALL_ARMS: list[Arm] = (
    PLAN_ARMS + PROMPT_ARMS + RETRIEVAL_ARMS + SEARCH_ARMS + TEST_ARMS + MODEL_ARMS
)

ARMS_BY_CATEGORY: dict[ArmCategory, list[Arm]] = {
    "plan": PLAN_ARMS,
    "prompt": PROMPT_ARMS,
    "retrieval": RETRIEVAL_ARMS,
    "search": SEARCH_ARMS,
    "test": TEST_ARMS,
    "model": MODEL_ARMS,
}

ARMS_BY_KEY: dict[str, Arm] = {arm.arm_key: arm for arm in ALL_ARMS}


def get_arm(key: str) -> Arm | None:
    """Get arm by key."""
    return ARMS_BY_KEY.get(key)


def get_arms_for_category(category: ArmCategory) -> list[Arm]:
    """Get all arms in a category."""
    return ARMS_BY_CATEGORY.get(category, [])


def list_categories() -> list[ArmCategory]:
    """List all arm categories."""
    return list(ARMS_BY_CATEGORY.keys())
