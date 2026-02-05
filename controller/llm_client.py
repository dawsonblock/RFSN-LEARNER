# controller/llm_client.py
"""
LLM client with multi-provider support (OpenAI, Anthropic, DeepSeek).

This is the "reasoning plane" - generates proposals that go through the gate.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal

# Provider support (lazy imports to avoid hard dependencies)
Provider = Literal["openai", "anthropic", "deepseek", "mock"]


@dataclass
class LLMConfig:
    provider: Provider = "openai"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 30.0
    
    def __post_init__(self):
        if self.api_key is None:
            # Try environment variables
            if self.provider == "openai":
                self.api_key = os.getenv("OPENAI_API_KEY")
            elif self.provider == "anthropic":
                self.api_key = os.getenv("ANTHROPIC_API_KEY")
            elif self.provider == "deepseek":
                self.api_key = os.getenv("DEEPSEEK_API_KEY")


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: Provider
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMClient:
    """
    Unified LLM client supporting multiple providers.
    
    All outputs go through the gate - this is untrusted reasoning.
    """
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Lazy initialize the provider client."""
        if self._client is not None:
            return self._client
        
        if self.config.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        elif self.config.provider == "anthropic":
            from anthropic import Anthropic
            self._client = Anthropic(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        elif self.config.provider == "deepseek":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url="https://api.deepseek.com",
                timeout=self.config.timeout,
            )
        elif self.config.provider == "mock":
            self._client = "mock"
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
        
        return self._client
    
    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.
        
        Returns structured response that should be parsed and gated.
        """
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        
        if self.config.provider == "mock":
            return self._mock_complete(system, user)
        
        client = self._get_client()
        
        if self.config.provider in ("openai", "deepseek"):
            return self._openai_complete(client, system, user, temp, tokens)
        elif self.config.provider == "anthropic":
            return self._anthropic_complete(client, system, user, temp, tokens)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
    
    def _openai_complete(
        self,
        client: Any,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            provider=self.config.provider,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            raw=response,
        )
    
    def _anthropic_complete(
        self,
        client: Any,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = client.messages.create(
            model=self.config.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        content = ""
        if response.content and len(response.content) > 0:
            content = response.content[0].text
        
        return LLMResponse(
            content=content,
            model=response.model,
            provider=self.config.provider,
            usage={
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
            },
            raw=response,
        )
    
    def _mock_complete(self, system: str, user: str) -> LLMResponse:
        """Mock response for testing without API calls."""
        # Parse user message to generate appropriate mock response
        user_lower = user.lower()
        
        if "list" in user_lower and "file" in user_lower:
            content = json.dumps({
                "action": "tool_call",
                "tool": "list_dir",
                "arguments": {"path": "./"},
                "justification": "List files as requested",
            })
        elif "read" in user_lower:
            content = json.dumps({
                "action": "tool_call",
                "tool": "read_file",
                "arguments": {"path": "./README.md"},
                "justification": "Read the requested file",
            })
        else:
            content = json.dumps({
                "action": "message_send",
                "message": f"I understand you want to: {user[:100]}",
                "justification": "Acknowledge request",
            })
        
        return LLMResponse(
            content=content,
            model="mock",
            provider="mock",
            usage={"prompt_tokens": len(system) + len(user), "completion_tokens": len(content)},
        )


# Prompt templates
SYSTEM_PROMPT_TOOL_CALL = """You are an AI assistant that helps users by calling tools.

Available tools: {tools}

Respond with a JSON object containing:
- "action": "tool_call"
- "tool": the tool name
- "arguments": tool arguments as an object
- "justification": brief explanation

Only output valid JSON. No markdown, no code fences."""

SYSTEM_PROMPT_PLANNER = """You are a planning assistant that breaks down goals into steps.

Available tools: {tools}

For the given goal, output a JSON array of steps:
[
  {{"step": 1, "description": "...", "tool": "...", "arguments": {{...}}}},
  ...
]

Keep plans simple (1-5 steps). Only output valid JSON."""

USER_PROMPT_TOOL_CALL = """Goal: {goal}

What tool should I call to accomplish this?"""

USER_PROMPT_PLAN = """Goal: {goal}

Break this down into steps using the available tools."""
