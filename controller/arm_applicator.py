# controller/arm_applicator.py
"""
Apply arm configurations to agent behavior.

Maps arm selections to concrete behavior changes:
- test: Affects test scope (max_tests, scope)
- search: Affects candidate breadth (depth, beam)
- retrieval: Affects context building
- prompt: Affects LLM prompting style
- plan: Affects decomposition strategy
- model: Affects LLM selection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from upstream_learner.arm_registry import MultiArmSelection


@dataclass
class TestConfig:
    """Test execution configuration from test arm."""

    scope: str = "affected"
    max_tests: int = 10
    timeout: int = 300


@dataclass
class SearchConfig:
    """Search configuration from search arm."""

    depth: int = 1
    beam: int = 1


@dataclass
class RetrievalConfig:
    """Context retrieval configuration from retrieval arm."""

    strategy: str = "file_list"
    max_files: int = 10
    max_lines: int = 200
    use_embeddings: bool = False


@dataclass
class PromptConfig:
    """Prompt configuration from prompt arm."""

    style: str = "concise"
    max_tokens: int = 500
    include_examples: bool = False
    think_first: bool = False


@dataclass
class ModelConfig:
    """Model configuration from model arm."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"


@dataclass
class AppliedConfig:
    """Combined configuration from all arms."""

    test: TestConfig
    search: SearchConfig
    retrieval: RetrievalConfig
    prompt: PromptConfig
    model: ModelConfig

    @classmethod
    def from_selection(cls, selection: MultiArmSelection) -> "AppliedConfig":
        """Create config from multi-arm selection."""
        return apply_arms(selection)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test": {
                "scope": self.test.scope,
                "max_tests": self.test.max_tests,
                "timeout": self.test.timeout,
            },
            "search": {
                "depth": self.search.depth,
                "beam": self.search.beam,
            },
            "retrieval": {
                "strategy": self.retrieval.strategy,
                "max_files": self.retrieval.max_files,
                "max_lines": self.retrieval.max_lines,
            },
            "prompt": {
                "style": self.prompt.style,
                "max_tokens": self.prompt.max_tokens,
            },
            "model": {
                "provider": self.model.provider,
                "model": self.model.model,
            },
        }


def _apply_test_arm(config: Mapping[str, Any]) -> TestConfig:
    """Apply test arm configuration."""
    return TestConfig(
        scope=str(config.get("scope", "affected")),
        max_tests=int(config.get("max_tests", 10)),
        timeout=int(config.get("timeout", 300)),
    )


def _apply_search_arm(config: Mapping[str, Any]) -> SearchConfig:
    """Apply search arm configuration."""
    return SearchConfig(
        depth=int(config.get("depth", 1)),
        beam=int(config.get("beam", 1)),
    )


def _apply_retrieval_arm(config: Mapping[str, Any]) -> RetrievalConfig:
    """Apply retrieval arm configuration."""
    return RetrievalConfig(
        strategy=str(config.get("strategy", "file_list")),
        max_files=int(config.get("max_files", 10)),
        max_lines=int(config.get("max_lines", 200)),
        use_embeddings=bool(config.get("embeddings", False)),
    )


def _apply_prompt_arm(config: Mapping[str, Any]) -> PromptConfig:
    """Apply prompt arm configuration."""
    return PromptConfig(
        style=str(config.get("style", "concise")),
        max_tokens=int(config.get("max_tokens", 500)),
        include_examples=bool(config.get("include_examples", False)),
        think_first=bool(config.get("think_first", False)),
    )


def _apply_model_arm(config: Mapping[str, Any]) -> ModelConfig:
    """Apply model arm configuration."""
    return ModelConfig(
        provider=str(config.get("provider", "openai")),
        model=str(config.get("model", "gpt-4o-mini")),
    )


def apply_arms(selection: MultiArmSelection) -> AppliedConfig:
    """
    Apply a multi-arm selection to produce concrete configuration.

    Args:
        selection: Multi-arm selection from learner

    Returns:
        AppliedConfig with concrete settings for each category
    """
    configs = selection.config

    return AppliedConfig(
        test=_apply_test_arm(configs.get("test", {})),
        search=_apply_search_arm(configs.get("search", {})),
        retrieval=_apply_retrieval_arm(configs.get("retrieval", {})),
        prompt=_apply_prompt_arm(configs.get("prompt", {})),
        model=_apply_model_arm(configs.get("model", {})),
    )


def default_config() -> AppliedConfig:
    """Get default configuration (no arm selection)."""
    return AppliedConfig(
        test=TestConfig(),
        search=SearchConfig(),
        retrieval=RetrievalConfig(),
        prompt=PromptConfig(),
        model=ModelConfig(),
    )
