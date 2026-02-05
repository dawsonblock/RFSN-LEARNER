# upstream_learner/arm_registry.py
"""
Candidate arm registry for Thompson sampling over multiple dimensions.

Arms represent choices that can be learned:
- Prompt templates
- Retrieval strategies
- Search depth / beam size
- Test scope
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence

from .bandit import ArmStats, thompson_select
from .outcome_db import OutcomeDB


ArmType = Literal["prompt", "retrieval", "search_depth", "test_scope", "model"]


@dataclass
class Arm:
    """A single learnable choice."""
    arm_key: str
    arm_type: ArmType
    config: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""


# Default arm sets for different dimensions
DEFAULT_PROMPT_ARMS = [
    Arm("prompt::concise", "prompt", {"style": "concise"}, "Concise, direct prompts"),
    Arm("prompt::detailed", "prompt", {"style": "detailed"}, "Detailed with examples"),
    Arm("prompt::cot", "prompt", {"style": "chain_of_thought"}, "Chain-of-thought reasoning"),
]

DEFAULT_RETRIEVAL_ARMS = [
    Arm("retrieval::none", "retrieval", {"strategy": "none"}, "No context retrieval"),
    Arm("retrieval::file_list", "retrieval", {"strategy": "file_list"}, "List relevant files"),
    Arm("retrieval::full_context", "retrieval", {"strategy": "full_context"}, "Full file contents"),
]

DEFAULT_SEARCH_ARMS = [
    Arm("search::shallow", "search_depth", {"depth": 1, "beam": 1}, "Single attempt"),
    Arm("search::medium", "search_depth", {"depth": 3, "beam": 2}, "3 attempts, beam 2"),
    Arm("search::deep", "search_depth", {"depth": 5, "beam": 3}, "5 attempts, beam 3"),
]

DEFAULT_MODEL_ARMS = [
    Arm("model::gpt4o_mini", "model", {"provider": "openai", "model": "gpt-4o-mini"}, "GPT-4o-mini"),
    Arm("model::gpt4o", "model", {"provider": "openai", "model": "gpt-4o"}, "GPT-4o"),
    Arm("model::claude_sonnet", "model", {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}, "Claude Sonnet"),
    Arm("model::deepseek", "model", {"provider": "deepseek", "model": "deepseek-chat"}, "DeepSeek Chat"),
]


@dataclass
class ArmRegistry:
    """
    Registry of learnable arms with Thompson sampling selection.
    """
    db: OutcomeDB
    prompt_arms: list[Arm] = field(default_factory=lambda: list(DEFAULT_PROMPT_ARMS))
    retrieval_arms: list[Arm] = field(default_factory=lambda: list(DEFAULT_RETRIEVAL_ARMS))
    search_arms: list[Arm] = field(default_factory=lambda: list(DEFAULT_SEARCH_ARMS))
    model_arms: list[Arm] = field(default_factory=lambda: list(DEFAULT_MODEL_ARMS))
    
    def select_arm(
        self,
        *,
        arm_type: ArmType,
        context_key: str,
        seed: int = 0,
    ) -> Arm:
        """
        Select the best arm for a given type using Thompson sampling.
        """
        arms = self._get_arms_for_type(arm_type)
        if not arms:
            raise ValueError(f"No arms registered for type: {arm_type}")
        
        # Get historical stats
        summary = self.db.summary(context_key=context_key)
        stats = [ArmStats(arm_key=a, n=n, mean=mu) for (a, n, mu) in summary]
        
        # Thompson sampling
        arm_keys = [a.arm_key for a in arms]
        selected_key = thompson_select(arm_keys, stats, seed=seed)
        
        return next(a for a in arms if a.arm_key == selected_key)
    
    def select_all(
        self,
        *,
        context_key: str,
        seed: int = 0,
    ) -> dict[ArmType, Arm]:
        """
        Select best arm for each type.
        """
        result: dict[ArmType, Arm] = {}
        for i, arm_type in enumerate(["prompt", "retrieval", "search_depth", "model"]):
            result[arm_type] = self.select_arm(  # type: ignore
                arm_type=arm_type,  # type: ignore
                context_key=context_key,
                seed=seed + i,
            )
        return result
    
    def record_outcome(
        self,
        *,
        context_key: str,
        arm: Arm,
        reward: float,
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Record the outcome of using an arm.
        """
        payload = {
            "arm_type": arm.arm_type,
            "config": dict(arm.config),
        }
        if meta:
            payload["meta"] = dict(meta)
        
        self.db.record(
            context_key=context_key,
            arm_key=arm.arm_key,
            reward=float(reward),
            meta_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ts_utc=datetime.now(timezone.utc).isoformat(),
        )
    
    def _get_arms_for_type(self, arm_type: ArmType) -> list[Arm]:
        if arm_type == "prompt":
            return self.prompt_arms
        elif arm_type == "retrieval":
            return self.retrieval_arms
        elif arm_type == "search_depth":
            return self.search_arms
        elif arm_type == "model":
            return self.model_arms
        else:
            return []
    
    def add_arm(self, arm: Arm) -> None:
        """Register a new arm."""
        arms = self._get_arms_for_type(arm.arm_type)
        if not any(a.arm_key == arm.arm_key for a in arms):
            arms.append(arm)
