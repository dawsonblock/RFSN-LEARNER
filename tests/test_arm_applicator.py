# tests/test_arm_applicator.py
"""
Tests for arm applicator module.
"""
from __future__ import annotations

import pytest

from controller.arm_applicator import (
    AppliedConfig,
    TestConfig,
    SearchConfig,
    RetrievalConfig,
    PromptConfig,
    ModelConfig,
    apply_arms,
    default_config,
)


class TestDefaultConfig:
    """Test default configuration."""

    def test_default_config_returns_applied_config(self):
        cfg = default_config()
        assert isinstance(cfg, AppliedConfig)

    def test_default_test_scope(self):
        cfg = default_config()
        assert cfg.test.scope == "affected"
        assert cfg.test.max_tests == 10

    def test_default_search_depth(self):
        cfg = default_config()
        assert cfg.search.depth == 1
        assert cfg.search.beam == 1

    def test_default_retrieval_strategy(self):
        cfg = default_config()
        assert cfg.retrieval.strategy == "file_list"

    def test_default_prompt_style(self):
        cfg = default_config()
        assert cfg.prompt.style == "concise"

    def test_default_model(self):
        cfg = default_config()
        assert cfg.model.provider == "openai"
        assert cfg.model.model == "gpt-4o-mini"


class TestToDict:
    """Test serialization."""

    def test_to_dict_has_all_keys(self):
        cfg = default_config()
        d = cfg.to_dict()
        assert "test" in d
        assert "search" in d
        assert "retrieval" in d
        assert "prompt" in d
        assert "model" in d

    def test_to_dict_test_section(self):
        cfg = default_config()
        d = cfg.to_dict()
        assert d["test"]["scope"] == "affected"
        assert d["test"]["max_tests"] == 10
        assert d["test"]["timeout"] == 300

    def test_to_dict_search_section(self):
        cfg = default_config()
        d = cfg.to_dict()
        assert d["search"]["depth"] == 1
        assert d["search"]["beam"] == 1


class TestApplyArms:
    """Test arm application with mock selection."""

    def test_apply_arms_with_mock_selection(self):
        # Create a mock selection-like object
        class MockArm:
            def __init__(self, cfg):
                self.config = cfg

        class MockSelection:
            @property
            def config(self):
                return {
                    "test": {"scope": "full", "max_tests": 50, "timeout": 600},
                    "search": {"depth": 5, "beam": 3},
                    "retrieval": {"strategy": "semantic", "embeddings": True},
                    "prompt": {"style": "cot", "think_first": True},
                    "model": {"provider": "anthropic", "model": "claude-sonnet"},
                }

        selection = MockSelection()
        cfg = apply_arms(selection)

        assert cfg.test.scope == "full"
        assert cfg.test.max_tests == 50
        assert cfg.search.depth == 5
        assert cfg.search.beam == 3
        assert cfg.retrieval.strategy == "semantic"
        assert cfg.retrieval.use_embeddings is True
        assert cfg.prompt.style == "cot"
        assert cfg.prompt.think_first is True
        assert cfg.model.provider == "anthropic"


class TestConfigDataclasses:
    """Test individual config dataclasses."""

    def test_test_config_defaults(self):
        cfg = TestConfig()
        assert cfg.scope == "affected"
        assert cfg.max_tests == 10
        assert cfg.timeout == 300

    def test_search_config_defaults(self):
        cfg = SearchConfig()
        assert cfg.depth == 1
        assert cfg.beam == 1

    def test_retrieval_config_defaults(self):
        cfg = RetrievalConfig()
        assert cfg.strategy == "file_list"
        assert cfg.max_files == 10

    def test_prompt_config_defaults(self):
        cfg = PromptConfig()
        assert cfg.style == "concise"
        assert cfg.include_examples is False

    def test_model_config_defaults(self):
        cfg = ModelConfig()
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o-mini"
