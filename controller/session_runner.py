# controller/session_runner.py
"""
Headless session runner API for programmatic access.

Provides a clean API for running agent sessions without CLI interaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from rfsn.ledger import AppendOnlyLedger
from rfsn.policy import DEFAULT_POLICY, AgentPolicy

from .tool_registry import TOOL_REGISTRY
from .tool_router import ExecutionContext


@dataclass
class SessionConfig:
    """Configuration for a session."""

    policy: AgentPolicy = field(default_factory=lambda: DEFAULT_POLICY)
    working_directory: str = "./"
    memory_db_path: str = "agent_memory.db"
    ledger_path: str | None = None
    auto_grant_tools: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    """Result from a single session step."""

    reply: str | None
    tool_calls: list[dict[str, Any]]
    artifacts: list[str]
    errors: list[dict[str, Any]]
    ledger_tail: list[dict[str, Any]]


class Session:
    """
    Headless agent session for programmatic access.

    Usage:
        session = Session(config)
        result = session.step("What files are in the current directory?")
        print(result.reply)
    """

    def __init__(self, config: SessionConfig | None = None):
        self.config = config or SessionConfig()
        self.session_id = str(uuid.uuid4())[:8]

        # Initialize context
        self.context = ExecutionContext(
            session_id=self.session_id,
            working_directory=self.config.working_directory,
            memory_db_path=self.config.memory_db_path,
        )

        # Initialize ledger
        ledger_path = self.config.ledger_path or f"session_{self.session_id}.jsonl"
        self.ledger = AppendOnlyLedger(ledger_path)

        # Auto-grant specified tools
        for tool in self.config.auto_grant_tools:
            self.context.permissions.grant_tool(tool)

        # Track conversation
        self.history: list[dict[str, str]] = []
        self._step_count = 0

    def grant_tool(self, tool: str) -> None:
        """Grant permission for a tool."""
        self.context.permissions.grant_tool(tool)

    def revoke_tool(self, tool: str) -> None:
        """Revoke permission for a tool."""
        self.context.permissions.revoke_tool(tool)

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools with metadata."""
        tools = []
        for name, spec in TOOL_REGISTRY.items():
            tools.append(
                {
                    "name": name,
                    "risk": spec.risk.value,
                    "requires_grant": spec.permission.require_explicit_grant,
                    "granted": self.context.permissions.has_tool(name),
                }
            )
        return tools

    def step(self, user_input: str) -> StepResult:
        """
        Execute a single step of the agent loop.

        Args:
            user_input: User's message

        Returns:
            StepResult with reply, tool calls, artifacts, errors, and ledger tail
        """
        from rfsn.types import WorldSnapshot

        from .agent_loop import AgentConfig, run_agent_turn

        self._step_count += 1
        self.context.start_new_turn()

        # Add to history
        self.history.append({"role": "user", "content": user_input})

        # Convert history format for agent_loop
        chat_history = [(h["role"], h["content"]) for h in self.history[:-1]]

        # Create world snapshot
        world = WorldSnapshot(
            files_changed=[],
            tests_status={},
            git_status=None,
        )

        # Run agent turn
        try:
            agent_result = run_agent_turn(
                user_text=user_input,
                chat_history=chat_history,
                world=world,
                policy=self.config.policy,
                ledger=self.ledger,
                exec_ctx=self.context,
                cfg=AgentConfig(max_steps=6),
            )

            result = StepResult(
                reply=agent_result.message,
                tool_calls=[],  # Would need to track from agent
                artifacts=[],
                errors=[],
                ledger_tail=self._read_ledger_tail(5),
            )

        except Exception as e:
            result = StepResult(
                reply=f"Error executing agent: {e}",
                tool_calls=[],
                artifacts=[],
                errors=[{"code": "agent:internal_error", "message": str(e)}],
                ledger_tail=[],
            )

        self.history.append({"role": "assistant", "content": result.reply or ""})

        return result

    def _read_ledger_tail(self, n: int) -> list[dict[str, Any]]:
        """Read last n entries from ledger."""
        try:
            entries = self.ledger.read_tail(n)
            return [e for e in entries]
        except Exception:
            return []

    def reset(self) -> None:
        """Reset session state."""
        self.context.start_new_turn()
        self.history.clear()
        self._step_count = 0

    def get_state(self) -> dict[str, Any]:
        """Get current session state."""
        return {
            "session_id": self.session_id,
            "step_count": self._step_count,
            "history_length": len(self.history),
            "granted_tools": self.context.permissions.list_grants(),
            "working_directory": self.context.working_directory,
        }


def run_session_step(
    user_text: str,
    session: Session | None = None,
) -> tuple[StepResult, Session]:
    """
    Run a single session step.

    Creates a new session if none provided.
    Returns both the result and the session for continued use.

    Usage:
        result, session = run_session_step("Hello")
        result2, session = run_session_step("What's in ./src?", session)
    """
    if session is None:
        session = Session()

    result = session.step(user_text)
    return result, session
